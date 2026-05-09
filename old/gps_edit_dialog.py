"""
GPS坐标编辑对话框
用于在地图上可视化编辑设备坐标
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QCheckBox, QMessageBox, QSplitter
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSignal, QObject, pyqtSlot, QUrl
import json
import os


class GPSEditHandler(QObject):
    """处理JavaScript与Python的通信"""
    
    map_ready = pyqtSignal()
    device_moved = pyqtSignal(str)  # 设备被移动
    save_changes = pyqtSignal(str)  # 保存修改
    
    @pyqtSlot(str)
    def onDeviceMoved(self, device_info):
        """设备被拖动修改位置"""
        self.device_moved.emit(device_info)
    
    @pyqtSlot(str)
    def onSaveChanges(self, changes_json):
        """保存所有修改"""
        self.save_changes.emit(changes_json)
    
    @pyqtSlot()
    def onMapReady(self):
        """地图加载完成"""
        self.map_ready.emit()


class GPSEditDialog(QDialog):
    """GPS坐标编辑对话框"""
    
    coordinates_updated = pyqtSignal(list)  # 坐标更新信号，传递修改的设备列表
    
    def __init__(self, parent=None, db_pool=None, device_model=None, 
                 area_list=None, device_cols_index=None):
        super().__init__(parent)
        
        self.db_pool = db_pool
        self.device_model = device_model
        self.area_list = area_list or []
        self.device_cols_index = device_cols_index or {}
        self.changed_devices = {}  # 记录修改的设备
        
        self.setWindowTitle("GPS坐标编辑")
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        
        self.init_ui()
        self.load_map()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建WebEngineView
        self.web_view = QWebEngineView()
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        # 性能优化设置
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        
        # 创建WebChannel
        self.gps_handler = GPSEditHandler()
        self.gps_handler.map_ready.connect(self.on_map_ready)
        self.gps_handler.device_moved.connect(self.on_device_moved)
        self.gps_handler.save_changes.connect(self.on_save_changes)
        
        self.channel = QWebChannel()
        self.channel.registerObject('gpsEditHandler', self.gps_handler)
        self.web_view.page().setWebChannel(self.channel)
        
        layout.addWidget(self.web_view)
        
    def load_map(self):
        """加载GPS编辑地图页面（使用配置替换后的URL）"""
        from map_class import get_html_url
        from app_config import app_config
        html_file = os.path.join(os.path.dirname(__file__), "gps_edit.html")
        self.web_view.load(get_html_url(html_file, app_config))
        
    def on_map_ready(self):
        """地图加载完成，传递数据"""
        self.load_area_data()
        self.load_device_data()
        
    def load_area_data(self):
        """加载区域数据到地图"""
        try:
            # 准备区域数据
            area_data = self.prepare_area_data(self.area_list)
            js_code = f"loadAreaData({json.dumps(area_data)});"
            self.web_view.page().runJavaScript(js_code)
        except Exception as e:
            print(f"加载区域数据失败: {e}")
            
    def prepare_area_data(self, area_list):
        """准备区域数据"""
        result = []
        for area in area_list:
            node = {
                'name': area.get('name', ''),
                '_key': area.get('_key', ''),
                'children': self.prepare_area_data(area.get('children', []))
            }
            result.append(node)
        return result
        
    def load_device_data(self):
        """加载设备数据到地图"""
        try:
            devices = []
            for row in range(self.device_model.rowCount()):
                device_id_item = self.device_model.item(row, self.device_cols_index.get("设备号", -1))
                device_name_item = self.device_model.item(row, self.device_cols_index.get("设备名称", -1))
                lng_item = self.device_model.item(row, self.device_cols_index.get("经度", -1))
                lat_item = self.device_model.item(row, self.device_cols_index.get("纬度", -1))
                area1_item = self.device_model.item(row, self.device_cols_index.get("区域1", -1))
                area2_item = self.device_model.item(row, self.device_cols_index.get("区域2", -1))
                area3_item = self.device_model.item(row, self.device_cols_index.get("区域3", -1))
                
                if device_id_item:
                    device_id = device_id_item.text()
                    device_name = device_name_item.text() if device_name_item else ""
                    lng = lng_item.text() if lng_item else ""
                    lat = lat_item.text() if lat_item else ""
                    area1 = area1_item.text() if area1_item else ""
                    area2 = area2_item.text() if area2_item else ""
                    area3 = area3_item.text() if area3_item else ""
                    
                    area_parts = [a for a in [area1, area2, area3] if a]
                    area_str = "-".join(area_parts) if area_parts else ""
                    
                    devices.append({
                        "deviceId": device_id,
                        "deviceName": device_name,
                        "lng": lng,
                        "lat": lat,
                        "area": area_str,
                        "areaPath": area_parts
                    })
                    
            js_code = f"loadDeviceData({json.dumps(devices)});"
            self.web_view.page().runJavaScript(js_code)
            print(f"已加载 {len(devices)} 个设备到GPS编辑地图")
            
        except Exception as e:
            print(f"加载设备数据失败: {e}")
            
    def on_device_moved(self, device_info_json):
        """设备被移动"""
        try:
            device_info = json.loads(device_info_json)
            device_id = device_info.get('deviceId')
            if device_id:
                self.changed_devices[device_id] = device_info
                print(f"设备 {device_id} 位置已修改")
        except Exception as e:
            print(f"处理设备移动事件失败: {e}")
            
    def on_save_changes(self, changes_json):
        """保存所有修改到数据库"""
        try:
            changes = json.loads(changes_json)
            success_count = 0
            failed_devices = []
            
            for device_id, change_info in changes.items():
                if self.update_device_coordinates(
                    device_id,
                    change_info.get('newLng'),
                    change_info.get('newLat'),
                    change_info.get('newAddress', '')
                ):
                    success_count += 1
                    # 更新数据模型
                    self.update_device_model(
                        device_id, 
                        change_info.get('newLng'), 
                        change_info.get('newLat'),
                        change_info.get('newAddress', '')
                    )
                else:
                    failed_devices.append(device_id)
                    
            # 通知JavaScript保存结果
            if len(failed_devices) == 0:
                self.web_view.page().runJavaScript("onSaveSuccess();")
                self.coordinates_updated.emit(list(changes.values()))
                self.changed_devices.clear()
            else:
                error_msg = f"以下设备保存失败: {', '.join(failed_devices)}"
                self.web_view.page().runJavaScript(f"onSaveFailed('{error_msg}');")
                
            print(f"保存完成: 成功 {success_count}/{len(changes)}")
            
        except Exception as e:
            print(f"保存修改失败: {e}")
            self.web_view.page().runJavaScript(f"onSaveFailed('{str(e)}');")
            
    def update_device_coordinates(self, device_id, lng, lat, address=''):
        """更新数据库中的设备坐标和地址"""
        try:
            if not self.db_pool:
                return False
            
            # 同时更新坐标和地址
            if address:
                order = "UPDATE device_info SET 经度 = %s, 纬度 = %s, 地址 = %s WHERE 设备号 = %s"
                params = (lng, lat, address, device_id)
            else:
                order = "UPDATE device_info SET 经度 = %s, 纬度 = %s WHERE 设备号 = %s"
                params = (lng, lat, device_id)
            
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(order, params)
                    conn.commit()
                    return cursor.rowcount > 0
                    
        except Exception as e:
            print(f"更新设备 {device_id} 坐标失败: {e}")
            return False
            
    def update_device_model(self, device_id, lng, lat, address=''):
        """更新数据模型中的设备坐标和地址"""
        try:
            for row in range(self.device_model.rowCount()):
                device_id_item = self.device_model.item(row, self.device_cols_index.get("设备号", -1))
                if device_id_item and device_id_item.text() == device_id:
                    # 更新经度
                    lng_col = self.device_cols_index.get("经度", -1)
                    if lng_col >= 0:
                        self.device_model.setItem(row, lng_col, self._create_item(lng))
                    # 更新纬度
                    lat_col = self.device_cols_index.get("纬度", -1)
                    if lat_col >= 0:
                        self.device_model.setItem(row, lat_col, self._create_item(lat))
                    # 更新地址
                    if address:
                        addr_col = self.device_cols_index.get("地址", -1)
                        if addr_col >= 0:
                            self.device_model.setItem(row, addr_col, self._create_item(address))
                    # 触发数据变化信号
                    self.device_model.dataChanged.emit(
                        self.device_model.index(row, 0),
                        self.device_model.index(row, self.device_model.columnCount() - 1)
                    )
                    break
        except Exception as e:
            print(f"更新数据模型失败: {e}")
            
    def _create_item(self, text):
        """创建表格项"""
        from PyQt6.QtGui import QStandardItem
        item = QStandardItem(str(text))
        item.setEditable(False)
        return item
