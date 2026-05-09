"""
区域展示界面 - HTML版本嵌入PyQt的Widget
用于替代原有的AreaMapTab，使用HTML5 Canvas实现相同功能
"""
import os
import json
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QObject, pyqtSlot
from PyQt6.QtGui import QFont
from log_save import Logger

# 导入QtWebEngine相关类（必须在QApplication创建前在main.py中导入）
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
except ImportError:
    # 如果已经通过main.py导入，则从sys.modules获取
    import sys
    QWebEngineView = sys.modules.get('PyQt6.QtWebEngineWidgets', {}).get('QWebEngineView')
    QWebChannel = sys.modules.get('PyQt6.QtWebChannel', {}).get('QWebChannel')

_log = Logger(True).logger


class AreaDisplayBridge(QObject):
    """JS和Python通信的桥梁"""
    signal_device_clicked = pyqtSignal(str)
    signal_area_clicked = pyqtSignal(str, int, int)
    signal_map_area_changed = pyqtSignal(str)
    signal_chart_filter_changed = pyqtSignal(int, str)  # chart_index, area_value
    
    @pyqtSlot(str)
    def onDeviceClicked(self, device_id):
        """设备被点击时的回调"""
        self.signal_device_clicked.emit(device_id)
    
    @pyqtSlot(str, int, int)
    def onAreaClicked(self, area_name, x, y):
        """区域被点击时的回调"""
        self.signal_area_clicked.emit(area_name, x, y)
    
    @pyqtSlot(str)
    def onMapAreaChanged(self, area_name):
        """地图区域切换时的回调"""
        self.signal_map_area_changed.emit(area_name)
    
    @pyqtSlot(int, str)
    def onChartFilterChanged(self, chart_index, area_value):
        """图表区域筛选改变时的回调"""
        _log.debug(f"图表筛选改变: chart_index={chart_index}, area_value={area_value}")
        self.signal_chart_filter_changed.emit(chart_index, area_value)
    
    @pyqtSlot(str)
    def jsLog(self, message):
        """接收JavaScript日志"""
        _log.info(f"[JS] {message}")
    
    @pyqtSlot(str)
    def jsError(self, message):
        """接收JavaScript错误"""
        _log.error(f"[JS Error] {message}")


class AreaDisplayWidget(QWidget):
    """区域展示界面Widget - 使用HTML5 Canvas实现"""
    signal_device_clicked = pyqtSignal(str)
    signal_area_control = pyqtSignal(dict)
    
    def __init__(self, parent=None, level1_area=None, image_path=None, 
                 db_pool=None, device_model=None, device_cols_index=None):
        super().__init__(parent)
        
        self.level1_area = level1_area
        self.image_path = image_path
        self.db_pool = db_pool
        self.device_model = device_model
        self.device_cols_index = device_cols_index
        self.sub_areas = []
        self.filtered_areas = []
        
        # 通信桥梁
        self.bridge = AreaDisplayBridge()
        self.bridge.signal_device_clicked.connect(self.on_device_clicked)
        self.bridge.signal_area_clicked.connect(self.on_area_clicked)
        self.bridge.signal_map_area_changed.connect(self.on_map_area_changed)
        
        # 定时刷新
        self.refresh_timer = None
        
        self.init_ui()
        self.load_data()
        self.start_auto_refresh()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建WebEngineView
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        # 设置WebChannel
        self.channel = QWebChannel()
        self.channel.registerObject('bridge', self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        # 加载HTML文件
        html_path = os.path.join(os.path.dirname(__file__), 'static', 'area_display.html')
        if os.path.exists(html_path):
            # 添加URL参数
            url = QUrl.fromLocalFile(html_path)
            if self.image_path:
                url.setQuery(f"image={self.image_path}&area={self.level1_area}")
            self.web_view.setUrl(url)
        else:
            _log.error(f"HTML文件不存在: {html_path}")
            self.web_view.setHtml("<h1>错误: 找不到展示界面文件</h1>")
    
    def set_sub_areas(self, areas):
        """设置子区域数据（用于图表筛选和地图显示）"""
        self.sub_areas = areas
        self.filtered_areas = areas.copy()
        # 延迟更新HTML，确保页面已加载
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self.update_sub_areas_in_html)
    
    def set_full_area_hierarchy(self, area_list):
        """设置完整的区域层次结构（包含所有1级、2级、3级区域）
        
        Args:
            area_list: 完整的区域列表，每个元素包含level, name, area, children
        """
        self.full_area_list = area_list
        # 同时更新sub_areas为第一个1级区域的子区域（用于设备筛选）
        if area_list:
            first_level1 = area_list[0]
            self.sub_areas = first_level1.get('children', [])
            self.filtered_areas = self.sub_areas.copy()
            self.level1_area = first_level1.get('name', '')
        # 延迟更新HTML，确保页面已加载
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self.update_full_area_hierarchy_in_html)
        # 同时更新地图筛选树（当前选中的1级区域）
        QTimer.singleShot(600, self.update_map_area_hierarchy_in_html)
        # 注意：不在这里调用update_map_areas_in_html，因为set_map_areas已经调用了
    
    def update_map_area_hierarchy_in_html(self):
        """更新HTML中的地图区域筛选树（只包含当前地图标签页对应的2级和3级区域，不显示1级）"""
        # 获取当前地图区域（当前选中的1级区域）
        current_level1_name = getattr(self, 'current_map_area', None) or self.level1_area or '全部区域'
        
        # 找到当前1级区域的数据
        current_level1_data = None
        if hasattr(self, 'full_area_list') and self.full_area_list:
            for area in self.full_area_list:
                if area.get('name') == current_level1_name:
                    current_level1_data = area
                    break
        
        # 如果没找到，使用第一个
        if not current_level1_data and hasattr(self, 'full_area_list') and self.full_area_list:
            current_level1_data = self.full_area_list[0]
        
        if not current_level1_data:
            return
        
        # 构建2级和3级区域的列表（不包含1级）
        formatted_areas = []
        
        # 处理2级区域
        for level2_area in current_level1_data.get('children', []):
            if isinstance(level2_area, dict):
                level2_data = level2_area.get('area', {})
                formatted_level2 = {
                    'name': level2_area.get('name', ''),
                    'level': 2,
                    'coords': level2_data.get('coords', []),
                    'children': []
                }
                
                # 处理3级区域
                for level3_area in level2_area.get('children', []):
                    if isinstance(level3_area, dict):
                        level3_data = level3_area.get('area', {})
                        formatted_level2['children'].append({
                            'name': level3_area.get('name', ''),
                            'level': 3,
                            'coords': level3_data.get('coords', [])
                        })
                
                formatted_areas.append(formatted_level2)
        
        # 更新HTML地图区域筛选树
        map_area_json = json.dumps(formatted_areas, ensure_ascii=False)
        level1_name = current_level1_data.get('name', '') if current_level1_data else ''
        _log.debug(f"更新HTML地图区域筛选树: {map_area_json}, 1级区域: {level1_name}")
        js_code = f"""
            if (typeof setMapAreaHierarchy === 'function') {{
                setMapAreaHierarchy({map_area_json}, '{level1_name}');
            }}
        """
        self.web_view.page().runJavaScript(js_code)

    def update_sub_areas_in_html(self):
        """更新HTML中的子区域数据（用于图表筛选和地图显示）
        
        包含完整的1级、2级和3级区域层次结构
        """
        # 转换区域数据格式，包含完整的3级层次结构
        # 1级区域作为根节点
        formatted_areas = []
        
        # 添加1级区域作为根
        level1_area = {
            'name': self.level1_area or '全部区域',
            'level': 1,
            'coords': [],
            'children': []
        }
        
        # 处理2级和3级区域
        for area in self.sub_areas:
            if isinstance(area, dict):
                area_data = area.get('area', {})
                # 这是2级区域
                formatted_area = {
                    'name': area.get('name', ''),
                    'level': 2,
                    'coords': area_data.get('coords', []),
                    'children': []
                }
                # 处理3级区域
                for child in area.get('children', []):
                    child_area_data = child.get('area', {})
                    formatted_area['children'].append({
                        'name': child.get('name', ''),
                        'level': 3,
                        'coords': child_area_data.get('coords', [])
                    })
                level1_area['children'].append(formatted_area)
        
        formatted_areas.append(level1_area)
        
        # 更新HTML区域层次结构（包含1级、2级和3级）
        chart_areas_json = json.dumps(formatted_areas, ensure_ascii=False)
        _log.debug(f"更新HTML子区域层次结构: {chart_areas_json}")
        js_code = f"""
            if (typeof setSubAreaHierarchy === 'function') {{
                setSubAreaHierarchy({chart_areas_json});
            }}
        """
        self.web_view.page().runJavaScript(js_code)
    
    def update_full_area_hierarchy_in_html(self):
        """更新HTML中的完整区域层次结构（包含所有1级、2级、3级区域）"""
        if not hasattr(self, 'full_area_list') or not self.full_area_list:
            return
        
        # 转换完整的区域层次结构
        formatted_areas = []
        
        for level1_area in self.full_area_list:
            if isinstance(level1_area, dict):
                area_data = level1_area.get('area', {})
                formatted_level1 = {
                    'name': level1_area.get('name', ''),
                    'level': 1,
                    'coords': area_data.get('coords', []),
                    'children': []
                }
                
                # 处理2级区域
                for level2_area in level1_area.get('children', []):
                    if isinstance(level2_area, dict):
                        level2_data = level2_area.get('area', {})
                        formatted_level2 = {
                            'name': level2_area.get('name', ''),
                            'level': 2,
                            'coords': level2_data.get('coords', []),
                            'children': []
                        }
                        
                        # 处理3级区域
                        for level3_area in level2_area.get('children', []):
                            if isinstance(level3_area, dict):
                                level3_data = level3_area.get('area', {})
                                formatted_level2['children'].append({
                                    'name': level3_area.get('name', ''),
                                    'level': 3,
                                    'coords': level3_data.get('coords', [])
                                })
                        
                        formatted_level1['children'].append(formatted_level2)
                
                formatted_areas.append(formatted_level1)
        
        # 更新HTML区域层次结构（包含所有1级、2级和3级）
        chart_areas_json = json.dumps(formatted_areas, ensure_ascii=False)
        _log.info(f"更新HTML完整区域层次结构: 区域数量={len(formatted_areas)}, 数据={chart_areas_json}")
        
        # 使用延迟确保页面已加载
        def do_update():
            js_code = f"""
                (function() {{
                    if (typeof setSubAreaHierarchy === 'function') {{
                        try {{
                            setSubAreaHierarchy({chart_areas_json});
                            return 'success';
                        }} catch(e) {{
                            return 'error: ' + e.message;
                        }}
                    }} else {{
                        return 'setSubAreaHierarchy not defined';
                    }}
                }})()
            """
            self.web_view.page().runJavaScript(js_code, lambda result: _log.info(f"JS执行结果: {result}"))
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, do_update)

    def set_map_areas(self, areas, current_area):
        """设置地图区域数据（一级区域列表）"""
        self.map_areas = areas
        self.current_map_area = current_area
        # 延迟更新HTML，确保页面已加载
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self.update_map_areas_in_html)

    def update_map_areas_in_html(self):
        """更新HTML中的地图区域数据"""
        areas_json = json.dumps(self.map_areas, ensure_ascii=False)
        _log.debug(f"更新HTML地图区域数据: {areas_json}")
        js_code = f"""
            if (typeof updateAreaList === 'function') {{
                updateAreaList({areas_json});
                // 切换到当前区域
                if (typeof switchMapArea === 'function') {{
                    switchMapArea('{self.current_map_area}');
                }}
            }}
        """
        self.web_view.page().runJavaScript(js_code)
    
    def update_areas_in_html(self):
        """更新HTML中的区域数据"""
        # 转换区域数据格式，适配HTML期望的格式
        formatted_areas = []
        for area in self.sub_areas:
            if isinstance(area, dict):
                # 获取图片路径并转换为本地文件URL
                image_path = area.get('area', {}).get('image_path', '')
                if image_path:
                    # 构建完整的本地文件路径
                    full_path = os.path.join(self.picture_dir, image_path)
                    if os.path.exists(full_path):
                        # 转换为file:// URL
                        image_url = QUrl.fromLocalFile(full_path).toString()
                    else:
                        image_url = ''
                else:
                    image_url = ''
                
                formatted_area = {
                    'name': area.get('name', ''),
                    'image_path': image_url
                }
                formatted_areas.append(formatted_area)
        
        areas_json = json.dumps(formatted_areas, ensure_ascii=False)
        _log.debug(f"更新HTML区域数据: {areas_json}")
        js_code = f"""
            if (typeof updateAreaList === 'function') {{
                updateAreaList({areas_json});
                // 切换到当前区域以刷新显示
                if (typeof switchMapArea === 'function' && '{self.level1_area}') {{
                    switchMapArea('{self.level1_area}');
                }}
            }}
        """
        self.web_view.page().runJavaScript(js_code)
    
    def refresh_devices(self):
        """刷新设备显示和图表数据"""
        devices = self._get_devices_data()
        devices_json = json.dumps(devices, ensure_ascii=False)
        js_code = f"""
            if (typeof updateDevices === 'function') {{
                updateDevices({devices_json});
            }}
        """
        self.web_view.page().runJavaScript(js_code)
        
        # 同时更新图表数据
        self._update_charts_data()
    
    def _update_charts_data(self):
        """更新图表数据（只更新设备位置，不覆盖图表数据）"""
        # 注意：图表数据由主线程的 _update_realtime_pie_by_area 等方法更新
        # 这里只更新设备位置信息，不覆盖图表数据
        # 但如果图表数据为空（初始化时），则更新图表数据
        try:
            js_code = """
                (function() {
                    if (chartData.chart1.online === 0 && chartData.chart1.offline === 0) {
                        return 'empty';
                    } else {
                        return 'has_data';
                    }
                })()
            """
            self.web_view.page().runJavaScript(js_code, self._on_check_chart_data)
        except Exception as e:
            _log.error(f"检查图表数据失败: {e}")
    
    def _on_check_chart_data(self, result):
        """检查图表数据回调"""
        try:
            if result == 'empty':
                # 图表数据为空，更新图表数据
                _log.info("图表数据为空，初始化图表数据")
                chart_data = self._get_chart_data()
                self.update_chart_data(chart_data)
            else:
                pass
                # _log.debug("图表数据已存在，跳过初始化")
        except Exception as e:
            _log.error(f"初始化图表数据失败: {e}")
    
    def _get_chart_data(self):
        """获取图表数据 - 直接从device_model获取所有设备，不依赖位置信息"""
        # 直接从device_model获取设备数据，不依赖位置信息
        online_count = 0
        offline_count = 0
        
        if self.device_model:
            online_status_col = self.device_cols_index.get("在线状态", -1)
            for row in range(self.device_model.rowCount()):
                if online_status_col != -1:
                    status_item = self.device_model.item(row, online_status_col)
                    if status_item and status_item.text() == "在线":
                        online_count += 1
                    else:
                        offline_count += 1
                else:
                    offline_count += 1
        
        _log.info(f"_get_chart_data: 在线={online_count}, 离线={offline_count}")
        
        # 7天数据
        dates = []
        online_rates = []
        electricity_values = []
        
        for i in range(6, -1, -1):
            date = datetime.now() - timedelta(days=i)
            dates.append(date.strftime("%m/%d"))
            
            # 从数据库获取实际数据
            daily_online_rate = self._get_daily_online_rate(date.strftime("%Y-%m-%d"))
            daily_electricity = self._get_daily_electricity(date.strftime("%Y-%m-%d"))
            
            online_rates.append(daily_online_rate)
            electricity_values.append(daily_electricity)
        
        # 24小时功率数据
        power_times = []
        power_values = []
        for i in range(23, -1, -1):
            time_point = datetime.now() - timedelta(hours=i)
            power_times.append(time_point.strftime("%H:%M"))
            power_value = self._get_hourly_power(time_point)
            power_values.append(power_value)
        
        return {
            'chart1': {
                'online': online_count,
                'offline': offline_count
            },
            'chart2': {
                'dates': dates,
                'values': online_rates
            },
            'chart3': {
                'dates': dates,
                'values': electricity_values
            },
            'chart4': {
                'times': power_times,
                'values': power_values
            }
        }
    
    def update_chart_data(self, chart_data):
        """更新图表数据（供外部调用）
        
        Args:
            chart_data: 图表数据字典，格式如下：
            {
                'chart1': {'online': int, 'offline': int},
                'chart2': {'dates': list, 'values': list},
                'chart3': {'dates': list, 'values': list},
                'chart4': {'times': list, 'values': list}
            }
        """
        try:
            import json
            chart_data_json = json.dumps(chart_data, ensure_ascii=False)
            _log.info(f"update_chart_data 被调用，数据: {chart_data_json}")
            js_code = f"""
                (function() {{
                    if (typeof updateChartData === 'function') {{
                        updateChartData({chart_data_json});
                        return 'success';
                    }} else {{
                        return 'updateChartData function not found';
                    }}
                }})()
            """
            self.web_view.page().runJavaScript(js_code, lambda result: _log.info(f"JS执行结果: {result}"))
            _log.debug("图表数据已更新到HTML")
        except Exception as e:
            _log.error(f"更新图表数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_all_device_ids(self):
        """获取所有设备ID - 直接从device_model获取"""
        device_ids = []
        if self.device_model:
            device_id_col = self.device_cols_index.get("设备号", -1)
            for row in range(self.device_model.rowCount()):
                device_id_item = self.device_model.item(row, device_id_col)
                if device_id_item:
                    device_ids.append(device_id_item.text())
        return device_ids
    
    def _get_daily_online_rate(self, date_str, devices=None):
        """获取指定日期的在线率（考虑add_datetime筛选）"""
        if not self.db_pool:
            return 0
        
        # 获取设备列表和添加时间
        device_info_list = self._get_all_device_info()  # [(device_id, add_datetime), ...]
        if not device_info_list:
            return 0
        
        try:
            from generalfunction import get_parsed_all_data
            from datetime import datetime
            
            total_count = 0
            online_count = 0
            is_today = (date_str == datetime.now().strftime("%Y-%m-%d"))
            day_end = datetime.strptime(date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            
            for device_id, add_datetime in device_info_list:
                if not device_id:
                    continue
                
                # 只统计添加日期在当天之前的设备
                if add_datetime and add_datetime > day_end:
                    continue
                
                total_count += 1
                is_online, _, _, _, _ = get_parsed_all_data(
                    self.db_pool, device_id, date_str, 300, is_today=is_today
                )
                if is_online:
                    online_count += 1
            
            return round((online_count / total_count * 100), 2) if total_count > 0 else 0
        except Exception as e:
            _log.error(f"获取 {date_str} 在线率失败: {e}")
            return 0
    
    def _get_all_device_info(self):
        """获取所有设备ID和添加时间"""
        device_info_list = []
        if self.device_model:
            device_id_col = self.device_cols_index.get("设备号", -1)
            add_date_col = self.device_cols_index.get("添加日期", -1)
            for row in range(self.device_model.rowCount()):
                device_id_item = self.device_model.item(row, device_id_col)
                add_date_item = self.device_model.item(row, add_date_col) if add_date_col != -1 else None
                if device_id_item:
                    device_id = device_id_item.text()
                    add_datetime = None
                    if add_date_item and add_date_item.text():
                        try:
                            from datetime import datetime
                            add_datetime = datetime.strptime(add_date_item.text(), "%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                    device_info_list.append((device_id, add_datetime))
        return device_info_list
    
    def _get_daily_electricity(self, date_str, devices=None):
        """获取指定日期的用电量（考虑add_datetime筛选）"""
        if not self.db_pool:
            return 0
        
        # 获取设备列表和添加时间
        device_info_list = self._get_all_device_info()
        if not device_info_list:
            return 0
        
        try:
            from generalfunction import get_parsed_all_data
            from datetime import datetime
            
            total_electricity = 0
            is_today = (date_str == datetime.now().strftime("%Y-%m-%d"))
            day_end = datetime.strptime(date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            
            for device_id, add_datetime in device_info_list:
                if not device_id:
                    continue
                
                # 只统计添加日期在当天之前的设备
                if add_datetime and add_datetime > day_end:
                    continue
                
                _, electricity, _, _, _ = get_parsed_all_data(
                    self.db_pool, device_id, date_str, 300, is_today=is_today
                )
                total_electricity += electricity
            
            return round(total_electricity, 2)
        except Exception as e:
            _log.error(f"获取 {date_str} 用电量失败: {e}")
            return 0
    
    def _get_hourly_power(self, time_point, devices=None):
        """获取指定时间点的功率"""
        if not self.db_pool:
            return 0
        
        # 获取设备列表
        device_ids = self._get_all_device_ids()
        if not device_ids:
            return 0
        
        try:
            total_power = 0
            time_str = time_point.strftime("%H:%M")
            date_str = time_point.strftime("%Y-%m-%d")
            
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    for device_id in device_ids:
                        if not device_id:
                            continue
                        
                        try:
                            power_table = f"{device_id}_power"
                            cursor.execute(
                                f"SELECT `功率` FROM `{power_table}` WHERE `时间点` = %s LIMIT 1",
                                (time_str,)
                            )
                            result = cursor.fetchone()
                            if result and result.get('功率'):
                                total_power += result['功率']
                        except Exception:
                            pass
            
            return round(total_power, 2)
        except Exception as e:
            _log.error(f"获取 {time_point} 功率失败: {e}")
            return 0
    
    def _get_devices_data(self):
        """获取设备数据 - 返回当前一级区域下的所有设备"""
        devices = []
        
        # 只处理当前一级区域的设备
        current_level1_area = self.level1_area
        
        _log.info(f"_get_devices_data: 当前一级区域: {current_level1_area}")
        
        # 遍历设备模型
        total_rows = 0
        matched_area_rows = 0
        has_position_rows = 0
        
        if self.device_model:
            total_rows = self.device_model.rowCount()
            for row in range(total_rows):
                area1_item = self.device_model.item(row, self.device_cols_index.get("区域1", -1))
                if not area1_item:
                    continue
                
                dev_area1 = area1_item.text()
                # 只处理当前一级区域的设备
                if dev_area1 != current_level1_area:
                    continue
                
                matched_area_rows += 1
                
                area2_item = self.device_model.item(row, self.device_cols_index.get("区域2", -1))
                area3_item = self.device_model.item(row, self.device_cols_index.get("区域3", -1))
                
                dev_area2 = area2_item.text() if area2_item else ""
                dev_area3 = area3_item.text() if area3_item else ""
                
                device_id_item = self.device_model.item(row, self.device_cols_index.get("设备号", -1))
                device_name_item = self.device_model.item(row, self.device_cols_index.get("设备名称", -1))
                online_item = self.device_model.item(row, self.device_cols_index.get("在线状态", -1))
                
                device_id = device_id_item.text() if device_id_item else ""
                device_name = device_name_item.text() if device_name_item else ""
                _log.info(f"处理设备: {device_id} ({device_name}), 区域: {dev_area1}/{dev_area2}/{dev_area3}")
                x, y = self._get_device_position(device_id)
                
                # 获取设备状态
                is_online = online_item.text() == "在线" if online_item else False
                
                # 获取开关状态和告警状态（如果有这些列）
                status_item = self.device_model.item(row, self.device_cols_index.get("状态", -1))
                alarm_item = self.device_model.item(row, self.device_cols_index.get("告警", -1))
                
                is_on = status_item.text() == "开" if status_item else False
                is_alarm = alarm_item.text() == "告警" if alarm_item else False
                
                if x is not None and y is not None:
                    has_position_rows += 1
                    devices.append({
                        'id': device_id,
                        'name': device_name_item.text() if device_name_item else device_id,
                        'x': x,
                        'y': y,
                        'is_online': is_online,
                        'is_on': is_on,
                        'is_alarm': is_alarm,
                        'area': dev_area2,  # 二级区域
                        'sub_area': dev_area3,  # 三级区域
                        'parent_area': dev_area1  # 一级区域（使用设备实际所属区域）
                    })
        
        _log.info(f"_get_devices_data: 总行数={total_rows}, 匹配区域={matched_area_rows}, 有位置={has_position_rows}, 返回设备数={len(devices)}")
        
        return devices
    
    def _get_device_position(self, device_id):
        """获取设备位置"""
        try:
            if self.db_pool:
                with self.db_pool.connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT `相对X`, `相对Y` FROM device_info WHERE 设备号 = %s",
                            (device_id,)
                        )
                        result = cursor.fetchone()
                        _log.info(f"设备 {device_id} 位置查询结果: {result}")
                        if result and result['相对X'] is not None and result['相对Y'] is not None:
                            x = int(float(result['相对X']))
                            y = int(float(result['相对Y']))
                            _log.info(f"设备 {device_id} 位置: ({x}, {y})")
                            return x, y
                        else:
                            _log.warning(f"设备 {device_id} 没有位置信息")
            else:
                _log.warning(f"设备 {device_id} 无法获取位置: db_pool 未设置")
        except Exception as e:
            _log.error(f"获取设备 {device_id} 位置失败: {e}")
            import traceback
            traceback.print_exc()
        
        return None, None
    
    def start_auto_refresh(self):
        """启动自动刷新定时器"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(5000)  # 每5秒刷新一次
        _log.debug(f"AreaDisplayWidget {self.level1_area}: 启动自动刷新定时器")
    
    def stop_auto_refresh(self):
        """停止自动刷新定时器"""
        if self.refresh_timer:
            self.refresh_timer.stop()
            _log.debug(f"AreaDisplayWidget {self.level1_area}: 停止自动刷新定时器")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.stop_auto_refresh()
        super().closeEvent(event)
    
    def on_device_clicked(self, device_id):
        """设备被点击"""
        self.signal_device_clicked.emit(device_id)
    
    def on_area_clicked(self, area_name, x, y):
        """区域被点击"""
        pass
    
    def on_map_area_changed(self, area_name):
        """地图区域切换时的回调"""
        _log.info(f"地图区域切换到: {area_name}")
        self.current_map_area = area_name
        self.level1_area = area_name
        
        # 从full_area_list中找到对应的子区域，更新filtered_areas
        if hasattr(self, 'full_area_list') and self.full_area_list:
            for area in self.full_area_list:
                if area.get('name') == area_name:
                    self.sub_areas = area.get('children', [])
                    self.filtered_areas = self.sub_areas.copy()
                    _log.info(f"更新筛选区域: {area_name} 的子区域: {[a.get('name') for a in self.filtered_areas]}")
                    break
        
        # 更新地图筛选树
        self.update_map_area_hierarchy_in_html()
    
    def load_data(self):
        """加载数据"""
        pass


# ==================== 使用示例 ====================
if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # 创建展示界面
    widget = AreaDisplayWidget(
        level1_area="锅炉房",
        image_path="D:/WokeSpace/SVN/MSTGD/12 工具集合/02 老化系统/device_management_system/pythonProject_NEW/picture/test.png"
    )
    
    # 设置模拟区域数据
    widget.set_sub_areas([
        {
            'name': '区域A',
            'coords': [[100, 100], [300, 100], [300, 200], [100, 200]],
            'children': [
                {'name': '区域A1', 'coords': [[110, 110], [190, 110], [190, 190], [110, 190]]}
            ]
        }
    ])
    
    widget.setWindowTitle("区域展示界面 - HTML版本")
    widget.resize(1000, 800)
    widget.show()
    
    sys.exit(app.exec())
