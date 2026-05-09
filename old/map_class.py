from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QTimer, QUrl, QObject, pyqtSlot,pyqtSignal, Qt
import sys
import json
import os


def load_html_with_config(html_file_path, app_config):
    """
    加载HTML文件并替换配置占位符

    Args:
        html_file_path: HTML文件路径
        app_config: 应用程序配置对象

    Returns:
        str: 处理后的HTML内容
    """
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 替换占位符
        html_content = html_content.replace('{{MAP_KEY}}', app_config.map_key)
        html_content = html_content.replace('{{MAP_SECURITY_KEY}}', app_config.map_security_key)

        return html_content
    except Exception as e:
        print(f"加载HTML文件失败: {e}")
        return None


_html_cache = {}  # HTML内容缓存，避免重复读取文件

def get_html_url(html_file_path, app_config):
    """
    获取处理后的HTML文件URL（使用临时文件方式）

    Args:
        html_file_path: HTML文件路径
        app_config: 应用程序配置对象

    Returns:
        QUrl: 处理后的HTML URL
    """
    import hashlib
    import tempfile

    html_content = load_html_with_config(html_file_path, app_config)
    if not html_content:
        # 如果处理失败，返回原始文件URL
        from PyQt6.QtCore import QUrl
        return QUrl.fromLocalFile(html_file_path)

    # 生成缓存文件名（基于原始文件名和配置内容的哈希）
    config_str = f"{app_config.map_key}_{app_config.map_security_key}"
    file_hash = hashlib.md5(f"{html_file_path}_{config_str}".encode()).hexdigest()[:8]
    cache_filename = f"map_cached_{file_hash}.html"
    cache_dir = tempfile.gettempdir()
    cache_path = os.path.join(cache_dir, cache_filename)

    # 检查缓存是否有效
    if html_file_path in _html_cache:
        cached_content, cached_path = _html_cache[html_file_path]
        if cached_content == html_content and os.path.exists(cached_path):
            from PyQt6.QtCore import QUrl
            return QUrl.fromLocalFile(cached_path)

    # 写入临时文件
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        _html_cache[html_file_path] = (html_content, cache_path)
        from PyQt6.QtCore import QUrl
        return QUrl.fromLocalFile(cache_path)
    except Exception as e:
        print(f"写入缓存文件失败: {e}")
        from PyQt6.QtCore import QUrl
        return QUrl.fromLocalFile(html_file_path)

class MapHandler(QObject):
    # 信号：区域控制命令（新格式，包含完整指令对象）
    signal_area_control = pyqtSignal(dict)  # control_data 包含 command, area, deviceIds, order/orders
    # 信号：请求设备数据
    signal_request_device_data = pyqtSignal(str)  # device_id
    # 信号：发送设备数据到JS
    signal_send_device_data = pyqtSignal(str)  # device_data_json

    @pyqtSlot(str)
    def onAreaClicked(self, areaInfo):
        """处理区域点击事件"""
        # 区域点击不再打印后台日志
        pass

    @pyqtSlot(str)
    def onDeviceClicked(self, deviceInfo):
        """处理设备点击事件"""
        try:
            device_info = json.loads(deviceInfo)
            device_id = device_info.get('deviceId', '未知设备')
            device_name = device_info.get('deviceName', '未命名设备')
            lng = device_info.get('lng', '-')
            lat = device_info.get('lat', '-')
            area = device_info.get('area', '-')

            # 在Python后台打印设备信息
            print(f"点击了设备: {device_name}")
            print(f"设备号: {device_id}")
            print(f"经度: {lng}")
            print(f"纬度: {lat}")
            print(f"所属区域: {area}")
            print("-----------------------------------")
        except json.JSONDecodeError:
            print(f"解析设备点击信息失败: {deviceInfo}")

    @pyqtSlot(str)
    def onAreaControl(self, controlData):
        """处理区域设备控制命令

        Args:
            controlData: JSON字符串，包含:
                - command: 'on'/'off'/'dimming'/'read'
                - area: 区域名称
                - deviceCount: 设备数量
                - deviceIds: 设备ID列表
                - order: 单个指令对象（设备详情弹窗使用）
                - orders: 指令对象列表（区域控制使用）
        """
        try:
            data = json.loads(controlData)
            command = data.get('command', '')
            area_name = data.get('area', '未知区域')
            device_count = data.get('deviceCount', 0)
            device_ids = data.get('deviceIds', [])
            order = data.get('order')  # 单个设备指令
            orders = data.get('orders')  # 多个设备指令列表

            print(f"=" * 50)
            print(f"区域设备控制命令")
            print(f"区域: {area_name}")
            print(f"命令: {command}")
            print(f"设备数量: {device_count}")
            print(f"设备列表: {device_ids}")
            if order:
                print(f"单个指令: {order}")
            if orders:
                print(f"指令数量: {len(orders)}")
            print(f"=" * 50)

            # 发射信号到main.py处理（传递完整数据）
            self.signal_area_control.emit(data)

        except json.JSONDecodeError as e:
            print(f"解析区域控制命令失败: {controlData}, 错误: {e}")
        except Exception as e:
            print(f"处理区域控制命令失败: {e}")

    @pyqtSlot(str)
    def requestDeviceData(self, deviceId):
        """请求设备实时数据

        Args:
            deviceId: 设备ID
        """
        print(f"请求设备数据: {deviceId}")
        # 发射信号到main.py获取数据
        self.signal_request_device_data.emit(deviceId)

    def sendDeviceDataToJS(self, device_data):
        """发送设备数据到JavaScript

        Args:
            device_data: 设备数据字典
        """
        try:
            import json
            data_json = json.dumps(device_data, ensure_ascii=False)
            self.signal_send_device_data.emit(data_json)
            print(f"发送设备数据到JS: {deviceId}")
        except Exception as e:
            print(f"发送设备数据到JS失败: {e}")

class DrawHandler(QObject):
    signal_draw_complete = pyqtSignal() # 绘制完成信号
    """处理绘制对话框的回调"""
    def __init__(self, dialog=None):
        super().__init__()
        self.dialog = dialog
        self.drawn_data = None
    
    @pyqtSlot(str)
    def onDrawComplete(self, data):
        """接收绘制完成的数据"""
        if data == 'CLOSE_DIALOG':
            if self.dialog:
                self.dialog.accept()
        else:
            try:
                self.drawn_data = json.loads(data)
                drawn_data = self.dialog.get_drawn_data()
                area_data = self.dialog.item.data(Qt.ItemDataRole.UserRole) or {}
                if drawn_data:
                    area_data["coords"] = drawn_data["coords"]
                    area_data["type"] = drawn_data["type"]
                    # print(f"=" * 50)
                    # print(f": 绘制数据{drawn_data}")
                    # print(f"=" * 50)

                    # print(f"====更新区域数据: {area_data}")
                    self.dialog.item.setData(area_data,Qt.ItemDataRole.UserRole)
                else:
                    area_data["coords"] = []
                    area_data["type"] = "未知"
                    self.dialog.item.setData(area_data, Qt.ItemDataRole.UserRole)
                    # print(f"绘制数据为空")
                self.signal_draw_complete.emit()
                
                print(f"绘制完成，区域数据: {data}")
            except json.JSONDecodeError:
                print(f"解析绘制数据失败: {data}")


class DrawDialog(QDialog):
    
    def __init__(self, parent=None, item=None, area_name="", existing_area_data=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"绘制区域 - {area_name}")
        self.setGeometry(100, 100, 1000, 800)
        
        # 保存选择的区域名称
        self.area_name = area_name
        self.existing_area_data = existing_area_data  # 已存在的区域数据
        self.drawn_data = None
        self._existing_area_loaded = False
        
        # 创建布局
        layout = QVBoxLayout(self)
        
        # 创建WebEngineView
        self.web_view = QWebEngineView()
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        # 性能优化设置
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        
        # 创建 QWebChannel
        self.draw_handler = DrawHandler(self)
        self.channel = QWebChannel()
        self.channel.registerObject('drawHandler', self.draw_handler)
        self.web_view.page().setWebChannel(self.channel)
        self.web_view.loadFinished.connect(self.on_draw_map_loaded)
        
        # 加载绘制地图
        self.load_draw_map()
        
        layout.addWidget(self.web_view)
    
    def on_draw_map_loaded(self, ok):
        """地图页面加载完成后，再检查 JS 地图实例是否真正可用"""
        if not ok:
            print("绘制地图页面加载失败")
            return

        if self.existing_area_data:
            QTimer.singleShot(100, self.loadExistingArea)
    
    def loadExistingArea(self, retry_count=0):
        """加载已存在的区域到地图"""
        if self._existing_area_loaded:
            return

        coords = self.existing_area_data.get('coords', [])
        area_type = self.existing_area_data.get('type', '')
        if coords and len(coords) > 0:
            js_code = f'''
                (function() {{
                    if (typeof window.isDrawMapReady === 'function' &&
                        window.isDrawMapReady() &&
                        typeof loadExistingArea === 'function') {{
                        loadExistingArea({json.dumps(coords)}, {json.dumps(area_type)});
                        console.log('已加载现有区域');
                        return 'loaded';
                    }}
                    return 'not_ready';
                }})()
            '''
            def handle_result(result):
                if result == 'loaded':
                    self._existing_area_loaded = True
                elif retry_count < 20:
                    QTimer.singleShot(200, lambda: self.loadExistingArea(retry_count + 1))
                else:
                    print("加载现有区域超时，地图仍未就绪")

            self.web_view.page().runJavaScript(js_code, handle_result)
    
    def get_drawn_data(self):
        """获取绘制的数据"""
        return self.draw_handler.drawn_data
    
    def load_draw_map(self):
        # 加载本地HTML文件（使用配置替换后的URL）
        from app_config import app_config
        html_file = os.path.join(os.path.dirname(__file__), "map_draw_new.html")
        self.web_view.load(get_html_url(html_file, app_config))


class LocationHandler(QObject):
    """处理地图定位对话框的回调"""
    signal_location_confirmed = pyqtSignal(dict)  # 位置确认信号
    signal_location_cancelled = pyqtSignal()  # 位置取消信号

    def __init__(self, dialog=None):
        super().__init__()
        self.dialog = dialog
        self.location_data = None

    @pyqtSlot(str)
    def onLocationConfirm(self, data):
        """接收位置确认数据"""
        if data == 'CLOSE_DIALOG':
            # 关闭对话框请求
            if self.dialog:
                self.dialog.reject()  # 使用reject关闭对话框，exec()会返回
            return

        try:
            self.location_data = json.loads(data)
            print(f"位置确认: {self.location_data}")
            self.signal_location_confirmed.emit(self.location_data)
            # 发送数据后关闭对话框
            if self.dialog:
                self.dialog.reject()
        except json.JSONDecodeError:
            print(f"解析位置数据失败: {data}")

    @pyqtSlot(str)
    def onLocationCancel(self, data=''):
        """接收位置取消事件"""
        if data == 'CLOSE_DIALOG':
            # 关闭对话框请求
            print("位置选择取消，关闭对话框")
            if self.dialog:
                self.dialog.reject()  # 使用reject关闭对话框，exec()会返回
        else:
            print("位置选择取消")
            self.signal_location_confirmed.emit({})  # 发送空数据表示取消


class LocationDialog(QDialog):
    """地图定位对话框"""

    def __init__(self, parent=None, initial_lng=None, initial_lat=None, initial_address=""):
        try:
            super().__init__(parent)
            self.setWindowTitle("地图定位")
            self.setGeometry(100, 100, 900, 700)
            
            # 设置为模态对话框，并置顶显示
            self.setModal(True)
            self.setWindowFlags(
                Qt.WindowType.Dialog |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.WindowTitleHint |
                Qt.WindowType.WindowSystemMenuHint |
                Qt.WindowType.WindowCloseButtonHint
            )

            # 保存初始位置 121.415034,31.025875
            self.initial_lng = initial_lng or 121.415034  # 默认扬州
            self.initial_lat = initial_lat or 31.025875
            self.initial_address = initial_address
            self.location_data = None

            # 创建布局
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # 创建WebEngineView
            self.web_view = QWebEngineView()
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            # 性能优化设置
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)

            # 创建 QWebChannel
            self.location_handler = LocationHandler(self)
            self.channel = QWebChannel()
            self.channel.registerObject('locationHandler', self.location_handler)
            self.web_view.page().setWebChannel(self.channel)
            self.web_view.loadFinished.connect(self.on_map_loaded)

            # 加载定位地图（使用配置替换后的URL）
            self.load_location_map()

            layout.addWidget(self.web_view)
        except Exception as e:
            print(f"LocationDialog初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def on_map_loaded(self, ok):
        """地图页面加载完成后，设置初始位置"""
        if not ok:
            print("定位地图页面加载失败")
            return

        # 延迟设置初始位置，确保地图完全加载
        QTimer.singleShot(500, self.set_initial_position)

    def set_initial_position(self):
        """设置初始位置到地图"""
        js_code = f'''
            (function() {{
                if (typeof setInitialPosition === 'function') {{
                    setInitialPosition({self.initial_lng}, {self.initial_lat}, {json.dumps(self.initial_address)});
                    return 'success';
                }}
                return 'not_ready';
            }})()
        '''

        def handle_result(result):
            if result == 'not_ready':
                print("地图尚未就绪，稍后重试")
                QTimer.singleShot(500, self.set_initial_position)
            else:
                print(f"初始位置已设置: ({self.initial_lng}, {self.initial_lat})")

        self.web_view.page().runJavaScript(js_code, handle_result)

    def get_location_data(self):
        """获取选中的位置数据"""
        return self.location_handler.location_data

    def load_location_map(self):
        """加载定位地图HTML文件（使用配置替换后的URL）"""
        from app_config import app_config
        html_file = os.path.join(os.path.dirname(__file__), "map_location.html")
        self.web_view.load(get_html_url(html_file, app_config))
