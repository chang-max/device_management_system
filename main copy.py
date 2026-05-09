"""
    智控平台客户端
    v0.0.2 2026-4 图片区域版本
"""

# 必须在QApplication创建前导入QtWebEngineWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

# win32console以获取更准确的控制台窗口句柄
try:
    import win32console
    HAS_WIN32CONSOLE = True
except ImportError:
    HAS_WIN32CONSOLE = False
import os
from re import T
import sys
import json
import traceback
import platform
from datetime import datetime
from win32gui import GetForegroundWindow, ShowWindow
from win32con import SW_HIDE, SW_SHOW
from dbutils.pooled_db import PooledDB
import pymysql
from pymysql import OperationalError
from pymysql.cursors import DictCursor
from threading import Thread
from datetime import timedelta
from time import sleep
import time
from random import randint
from functools import partial
import requests
import redis
from redis import Redis
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

from PyQt6.QtWidgets import (QMainWindow, QApplication, QTableView, QAbstractItemView, QVBoxLayout, QTableWidgetItem,
    QMessageBox, QTabWidget, QWidget, QHBoxLayout, QLabel, QPushButton, QDialog, QFileDialog, QSplitter,
    QTreeView, QInputDialog, QComboBox, QLineEdit, QSlider, QGroupBox, QGridLayout, QSpacerItem, QSizePolicy,
    QScrollArea, QFrame)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QPainter, QPen, QBrush, QColor, QFont, QImage
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QObject, pyqtSlot, QRect, QPoint, QSize

from log_in import LogIn
from UI.MainWindow_ui import Ui_MainWindow
from single_add import SingleAddDialog
from more_add import MoreAddDialog
from history import History
from mqtt_link_Callback import MqttThread
from messbox import Messbox
from device_data_processor import DeviceDataProcessor
from device_online_checker import DeviceOnlineChecker
from app_config import app_config

from log_save import Logger
_log = Logger(True).logger

from generalfunction import (get_area_dict, is_in_item, get_device_data_count, get_real_time_online_flg,
                               get_col_apply, add_device_default_row, get_device_Ec_value, list_before_deadline,
                               get_err_config, get_time, get_parsed_all_data, get_total_power_within_minutes)
from MyWidget import ConfigurableSortProxy, CheckBoxDelegate, OptimizedButtonDelegate, BrokenLineCanvas, PieCanvas, Power24hCanvas, AreaTreeView
from chart_area_filter import ChartAreaFilter


class DatabaseConnectionManager:
    """数据库连接管理器 - 处理连接失败、弹窗报错、自动重连"""
    
    def __init__(self, parent=None):
        self.parent = parent
        self.db_pool = None
        self.is_connected = False
        self.is_showing_error = False
        self.reconnect_timer = None
        self.connection_error_count = 0
        self.max_error_count = 3
        
    def init_pool(self, host, port, user, password, database):
        """初始化连接池"""
        try:
            pool = PooledDB(
                creator=pymysql,
                maxconnections=10,
                mincached=2,
                maxcached=3,
                blocking=True,
                maxusage=None,
                setsession=[],
                ping=1,
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
                cursorclass=DictCursor,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10
            )
            self.db_pool = pool
            self.is_connected = True
            self.connection_error_count = 0
            _log.info("数据库连接池初始化成功")
            return True
        except Exception as e:
            _log.error(f"连接池初始化失败: {e}")
            self.handle_connection_error(f"连接池初始化失败: {e}")
            return False
    
    def get_connection(self):
        """获取数据库连接，带错误处理"""
        if not self.db_pool:
            _log.error("数据库连接池未初始化")
            self.handle_connection_error("数据库连接池未初始化")
            return None
            
        try:
            conn = self.db_pool.connection()
            self.is_connected = True
            self.connection_error_count = 0
            return conn
        except Exception as e:
            _log.error(f"获取数据库连接失败: {e}")
            self.connection_error_count += 1
            
            if self.connection_error_count >= self.max_error_count:
                self.handle_connection_error(f"无法连接到数据库服务器: {e}")
            
            return None
    
    def handle_connection_error(self, error_msg):
        """处理连接错误 - 弹窗报错并启动重连"""
        if self.is_showing_error:
            return
            
        self.is_showing_error = True
        self.is_connected = False
        
        if self.parent:
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self.parent, 
                'show_db_error_dialog',
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, error_msg)
            )
        
        self.start_reconnect_timer()
    
    def start_reconnect_timer(self):
        """启动自动重连定时器"""
        if self.reconnect_timer is None and self.parent:
            self.reconnect_timer = QTimer(self.parent)
            self.reconnect_timer.timeout.connect(self.try_reconnect)
            self.reconnect_timer.start(10000)
            _log.info("启动数据库自动重连定时器")
    
    def stop_reconnect_timer(self):
        """停止自动重连定时器"""
        if self.reconnect_timer:
            self.reconnect_timer.stop()
            self.reconnect_timer = None
            _log.info("停止数据库自动重连定时器")
    
    def try_reconnect(self):
        """尝试重新连接数据库"""
        _log.info("尝试重新连接数据库...")
        try:
            if self.db_pool:
                conn = self.db_pool.connection()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                
                self.is_connected = True
                self.connection_error_count = 0
                self.is_showing_error = False
                self.stop_reconnect_timer()
                
                _log.info("数据库重连成功")
                
                if self.parent:
                    from PyQt6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(
                        self.parent,
                        'on_db_reconnect_success',
                        Qt.ConnectionType.QueuedConnection
                    )
            else:
                _log.error("连接池不存在，无法重连")
        except Exception as e:
            _log.warning(f"数据库重连失败: {e}")
    
    def close(self):
        """关闭连接管理器"""
        self.stop_reconnect_timer()
        if self.db_pool:
            try:
                self.db_pool.close()
            except:
                pass
            self.db_pool = None
        self.is_connected = False


class AreaImageLabel(QLabel):
    """显示区域图片的自定义Label，支持绘制区域和设备"""
    signal_area_clicked = pyqtSignal(str, int, int)  # 区域名称, x, y
    signal_device_clicked = pyqtSignal(str)  # 设备ID
    signal_device_moved = pyqtSignal(str, int, int)  # 设备ID, x, y - 设备被拖动到新位置
    
    def __init__(self, parent=None, editable=False):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        
        self.pixmap_original = None
        self.pixmap_scaled = None
        self.areas = []  # 区域列表
        self.devices = []  # 设备列表
        self.selected_area = None  # 当前选中的区域
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        
        # 拖动相关
        self.editable = editable  # 是否可编辑（拖动设备）
        self.dragging_device = None  # 当前拖动的设备
        self.drag_start_pos = None  # 拖动开始位置
        
        # 缩放相关
        self.zoom_factor = 1.0  # 缩放因子
        self.min_zoom = 0.5  # 最小缩放
        self.max_zoom = 5.0  # 最大缩放
        self.pan_x = 0  # 平移X
        self.pan_y = 0  # 平移Y
        self.is_panning = False  # 是否正在平移
        self.last_mouse_pos = None  # 上次鼠标位置
        
    def set_image(self, image_path):
        """设置背景图片"""
        _log.debug(f"AreaImageLabel.set_image: 尝试加载图片: {image_path}")
        if image_path and os.path.exists(image_path):
            self.pixmap_original = QPixmap(image_path)
            if self.pixmap_original.isNull():
                _log.error(f"AreaImageLabel.set_image: 图片加载失败(无效图片): {image_path}")
                self.pixmap_original = None
                self.setText(f"图片无效: {os.path.basename(image_path)}")
            else:
                _log.debug(f"AreaImageLabel.set_image: 图片加载成功: {image_path}, 尺寸: {self.pixmap_original.width()}x{self.pixmap_original.height()}")
                self.update_display()
        else:
            _log.warning(f"AreaImageLabel.set_image: 图片不存在: {image_path}")
            self.pixmap_original = None
            self.setText("未绑定图片")
            
    def update_display(self):
        """更新显示 - 支持缩放和平移"""
        if not self.pixmap_original:
            return
            
        # 获取当前尺寸
        current_width = max(self.width(), 400)
        current_height = max(self.height(), 300)
        
        _log.debug(f"AreaImageLabel.update_display: 当前尺寸 {self.width()}x{self.height()}, 缩放因子 {self.zoom_factor}")
        
        # 计算基础缩放（适应窗口）
        base_scale = min(current_width / self.pixmap_original.width(), 
                        current_height / self.pixmap_original.height())
        
        # 应用用户缩放
        self.scale_factor = base_scale * self.zoom_factor
        
        # 计算图片显示尺寸
        display_width = int(self.pixmap_original.width() * self.scale_factor)
        display_height = int(self.pixmap_original.height() * self.scale_factor)
        
        # 计算偏移（居中 + 平移）
        self.offset_x = int((current_width - display_width) // 2 + self.pan_x)
        self.offset_y = int((current_height - display_height) // 2 + self.pan_y)
        
        # 创建空白画布
        display_pixmap = QPixmap(current_width, current_height)
        display_pixmap.fill(QColor(240, 240, 240))  # 填充背景色
        
        painter = QPainter(display_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 绘制图片（只绘制可见部分）
        visible_x = int(max(0, -self.offset_x))
        visible_y = int(max(0, -self.offset_y))
        visible_width = int(min(display_width, current_width - self.offset_x) - max(0, -self.offset_x))
        visible_height = int(min(display_height, current_height - self.offset_y) - max(0, -self.offset_y))
        
        if visible_width > 0 and visible_height > 0:
            source_rect = QRect(
                int(visible_x / self.scale_factor),
                int(visible_y / self.scale_factor),
                int(visible_width / self.scale_factor),
                int(visible_height / self.scale_factor)
            )
            target_rect = QRect(
                self.offset_x + visible_x,
                self.offset_y + visible_y,
                visible_width,
                visible_height
            )
            painter.drawPixmap(target_rect, self.pixmap_original, source_rect)
        
        # 绘制区域
        self._draw_areas(painter)
        
        # 绘制设备
        self._draw_devices(painter)
        
        # 绘制缩放信息
        painter.setPen(QColor(0, 0, 0))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(10, 20, f"缩放: {self.zoom_factor*100:.0f}% | 滚轮缩放 | 中键平移")
        
        painter.end()
        self.setPixmap(display_pixmap)
            
    def _draw_areas(self, painter):
        """绘制区域 - 使用与绘制界面一致的蓝色"""
        # 与 DrawImageLabel 的样式配置保持一致
        stroke_color = QColor(0, 120, 215)  # 蓝色边线
        fill_color = QColor(0, 120, 215, 60)  # 蓝色填充，透明度约25%
        
        pen = QPen(stroke_color, 4)  # 边粗4像素，与绘制界面一致
        brush = QBrush(fill_color)
        painter.setPen(pen)
        painter.setBrush(brush)
        
        for area in self.areas:
            coords = area.get('coords', [])
            if len(coords) >= 3:
                points = []
                for coord in coords:
                    x = int(coord[0] * self.scale_factor + self.offset_x)
                    y = int(coord[1] * self.scale_factor + self.offset_y)
                    points.append(QPoint(x, y))
                
                if points:
                    painter.drawPolygon(points)
                    # 绘制区域名称
                    if points:
                        center_x = sum(p.x() for p in points) // len(points)
                        center_y = sum(p.y() for p in points) // len(points)
                        painter.setPen(QColor(0, 0, 0))
                        font = QFont()
                        font.setBold(True)
                        painter.setFont(font)
                        painter.drawText(center_x - 30, center_y, area.get('name', ''))
                        pen = QPen(stroke_color, 4)
                        painter.setPen(pen)
                        
    def _draw_devices(self, painter):
        """绘制设备 - 使用PNG图标"""
        # 图标最小尺寸（像素）
        MIN_ICON_SIZE = 24
        
        # 图标路径
        icon_dir = os.path.join(os.path.dirname(__file__), "picture", "icon")
        icon_paths = {
            'online_on': os.path.join(icon_dir, "开灯.png"),
            'online_off': os.path.join(icon_dir, "关灯.png"),
            'offline': os.path.join(icon_dir, "离线.png")
        }
        
        # 缓存图标
        if not hasattr(self, '_device_icons'):
            self._device_icons = {}
        
        for device in self.devices:
            x = int(device.get('x', 0) * self.scale_factor + self.offset_x)
            y = int(device.get('y', 0) * self.scale_factor + self.offset_y)
            
            # 判断设备状态
            device_status = self._get_device_status(device)
            
            # 获取对应图标
            icon_key = device_status
            if icon_key not in self._device_icons:
                icon_path = icon_paths.get(icon_key, icon_paths['offline'])
                if os.path.exists(icon_path):
                    self._device_icons[icon_key] = QPixmap(icon_path)
                else:
                    # 图标不存在，使用默认绘制
                    self._device_icons[icon_key] = None
            
            icon_pixmap = self._device_icons.get(icon_key)
            
            # 计算图标尺寸（基于缩放因子，但有最小值）
            base_size = max(24, int(24 * self.scale_factor))
            icon_size = max(MIN_ICON_SIZE, base_size)
            
            if icon_pixmap and not icon_pixmap.isNull():
                # 缩放图标（保持透明度）
                scaled_icon = icon_pixmap.scaled(icon_size, icon_size,
                                                 Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
                # 绘制图标（居中）- 使用原始透明度
                painter.drawPixmap(x - icon_size // 2, y - icon_size // 2, scaled_icon)
            else:
                # 图标不存在，使用默认圆点绘制
                if device_status == 'online_on':
                    color = QColor(255, 200, 0)  # 黄色表示开灯
                elif device_status == 'online_off':
                    color = QColor(100, 100, 100)  # 灰色表示关灯
                else:
                    color = QColor(255, 0, 0)  # 红色表示离线
                
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawEllipse(x - icon_size // 2, y - icon_size // 2, icon_size, icon_size)
            
            # 绘制设备名称（字体大小也有最小值）
            font = painter.font()
            font_size = max(9, int(9 * self.scale_factor))
            font.setPointSize(font_size)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(x + icon_size // 2 + 3, y + 4, device.get('name', '')[:10])
    
    def _get_device_status(self, device):
        """获取设备状态：online_on(开灯), online_off(关灯), offline(离线)
        从device_model中获取调光值"""
        device_id = device.get('id', '')
        if not device_id:
            return 'offline'
        
        # 检查是否有device_model和device_cols_index
        if not hasattr(self, 'device_model') or not hasattr(self, 'device_cols_index'):
            # 回退到使用device字典中的is_online字段
            is_online = device.get('is_online', False)
            return 'online_off' if is_online else 'offline'
        
        # 在device_model中查找设备
        device_id_col = self.device_cols_index.get("设备号", -1)
        online_col = self.device_cols_index.get("在线状态", -1)
        
        if device_id_col < 0:
            return 'offline'
        
        # 遍历device_model查找设备
        for row in range(self.device_model.rowCount()):
            item = self.device_model.item(row, device_id_col)
            if item and item.text() == device_id:
                # 找到设备，检查在线状态
                is_online = False
                if online_col >= 0:
                    online_item = self.device_model.item(row, online_col)
                    if online_item:
                        is_online = online_item.text() == "在线"
                
                if not is_online:
                    return 'offline'
                
                # 在线状态下，检查调光值
                dimming_value = 0
                # 尝试获取调光值（支持多种可能的字段名）
                col_idx = self.device_cols_index.get("调光值", -1)
                if col_idx >= 0:
                    try:
                        val_item = self.device_model.item(row, col_idx)
                        if val_item:
                            val = val_item.text()
                            if val and val != '-':
                                dimming_value = int(float(val))
                    except (ValueError, TypeError):
                        continue
                
                # 调光值 > 0 认为开灯，= 0 认为关灯
                return 'online_on' if dimming_value > 0 else 'online_off'
        
        # 未找到设备，使用device字典中的is_online
        is_online = device.get('is_online', False)
        return 'online_off' if is_online else 'offline'
            
    def set_areas(self, areas):
        """设置区域数据"""
        self.areas = areas
        self.update_display()
        
    def set_devices(self, devices):
        """设置设备数据"""
        self.devices = devices
        self.update_display()
        
    def reset_zoom(self):
        """重置缩放"""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_display()
        
    def resizeEvent(self, event):
        """窗口大小改变时重新绘制"""
        super().resizeEvent(event)
        self.update_display()
        
    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if not self.pixmap_original:
            return
            
        # 中键按下 - 开始平移
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
            
        # 转换坐标到图片坐标系
        img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
        img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
        
        # 检查是否点击了设备
        for device in self.devices:
            dx = device.get('x', 0) - img_x
            dy = device.get('y', 0) - img_y
            if (dx * dx + dy * dy) < 100:  # 10像素半径
                if self.editable and event.button() == Qt.MouseButton.LeftButton:
                    # 开始拖动设备
                    self.dragging_device = device
                    self.drag_start_pos = (img_x, img_y)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                else:
                    self.signal_device_clicked.emit(device.get('id', ''))
                return
                
        # 检查是否点击了区域
        for area in self.areas:
            if self._point_in_polygon(img_x, img_y, area.get('coords', [])):
                self.signal_area_clicked.emit(area.get('name', ''), img_x, img_y)
                return
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 用于拖动设备或平移"""
        # 平移模式
        if self.is_panning and self.last_mouse_pos:
            delta_x = event.pos().x() - self.last_mouse_pos.x()
            delta_y = event.pos().y() - self.last_mouse_pos.y()
            self.pan_x += delta_x
            self.pan_y += delta_y
            self.last_mouse_pos = event.pos()
            self.update_display()
            return
            
        # 拖动设备模式
        if self.dragging_device and self.pixmap_original:
            # 转换坐标到图片坐标系
            img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
            img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
            
            # 确保坐标在图片范围内
            if self.pixmap_original:
                img_x = max(0, min(img_x, self.pixmap_original.width()))
                img_y = max(0, min(img_y, self.pixmap_original.height()))
            
            # 更新设备位置
            self.dragging_device['x'] = img_x
            self.dragging_device['y'] = img_y
            self.update_display()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 结束拖动或平移"""
        # 结束平移
        if event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self.last_mouse_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
            
        # 结束设备拖动
        if self.dragging_device and event.button() == Qt.MouseButton.LeftButton:
            # 发送设备移动信号
            device_id = self.dragging_device.get('id', '')
            new_x = self.dragging_device.get('x', 0)
            new_y = self.dragging_device.get('y', 0)
            
            # 检查位置是否真的改变了
            if self.drag_start_pos:
                start_x, start_y = self.drag_start_pos
                if abs(start_x - new_x) > 5 or abs(start_y - new_y) > 5:
                    self.signal_device_moved.emit(device_id, new_x, new_y)
            
            self.dragging_device = None
            self.drag_start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 缩放"""
        if not self.pixmap_original:
            return
            
        # 获取滚轮方向
        delta = event.angleDelta().y()
        
        # 计算新的缩放因子
        if delta > 0:
            new_zoom = self.zoom_factor * 1.1
        else:
            new_zoom = self.zoom_factor / 1.1
            
        # 限制缩放范围
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        
        # 以鼠标位置为中心缩放
        if new_zoom != self.zoom_factor:
            mouse_x = event.position().x()
            mouse_y = event.position().y()
            
            # 计算鼠标在图片中的相对位置
            img_x = (mouse_x - self.offset_x) / self.scale_factor
            img_y = (mouse_y - self.offset_y) / self.scale_factor
            
            # 更新缩放因子
            old_zoom = self.zoom_factor
            self.zoom_factor = new_zoom
            
            # 调整平移量，使鼠标位置保持对应图片上的同一点
            scale_change = self.zoom_factor / old_zoom
            self.pan_x = mouse_x - img_x * self.scale_factor * scale_change - (self.width() - self.pixmap_original.width() * self.scale_factor * scale_change) / 2
            self.pan_y = mouse_y - img_y * self.scale_factor * scale_change - (self.height() - self.pixmap_original.height() * self.scale_factor * scale_change) / 2
            
            self.update_display()
                    
    def _point_in_polygon(self, x, y, coords):
        """判断点是否在多边形内"""
        if len(coords) < 3:
            return False
            
        n = len(coords)
        inside = False
        j = n - 1
        
        for i in range(n):
            xi, yi = coords[i]
            xj, yj = coords[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
            
        return inside


class ChartBridge(QObject):
    """图表与Python通信的桥梁"""
    signal_area_confirmed = pyqtSignal(str, str)  # chart_name, selected_area
    
    @pyqtSlot(str, str)
    def onChartAreaConfirmed(self, chart_name, selected_area):
        """图表区域选择确认时的回调"""
        self.signal_area_confirmed.emit(chart_name, selected_area)


class AreaImageBindingDialog(QDialog):
    """区域图片绑定对话框 - 支持选择图片和暗黑/明亮模式"""
    signal_binding_complete = pyqtSignal(dict)

    def __init__(self, parent=None, area_name=""):
        super().__init__(parent)
        self.setWindowTitle(f"绑定区域图片 - {area_name}")
        self.setGeometry(100, 100, 600, 500)
        self.area_name = area_name
        self.selected_image_path = None
        self.processed_image = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 图片路径选择区域
        path_layout = QHBoxLayout()
        self.path_label = QLabel("图片路径:")
        path_layout.addWidget(self.path_label)
        
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(self.browse_btn)
        
        layout.addLayout(path_layout)
        
        # 模式选择区域
        mode_layout = QHBoxLayout()
        self.mode_label = QLabel("显示模式:")
        mode_layout.addWidget(self.mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["明亮模式", "暗黑模式"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 图片预览区域
        self.preview_label = QLabel("请选择图片")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        self.preview_label.setMinimumSize(400, 300)
        layout.addWidget(self.preview_label)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.on_save)
        self.save_btn.setEnabled(False)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def browse_image(self):
        """浏览选择图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择区域图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.selected_image_path = file_path
            self.path_edit.setText(file_path)
            self.process_and_show_image()
            self.save_btn.setEnabled(True)
    
    def process_and_show_image(self):
        """处理并显示图片"""
        if not self.selected_image_path:
            return
        
        try:
            from generalfunction import clean_process_image
            from PIL import Image
            
            mode = self.mode_combo.currentText()
            
            if mode == "暗黑模式":
                # 使用暗黑模式处理图片
                self.processed_image = clean_process_image(self.selected_image_path, None)
            else:
                # 明亮模式，原图
                self.processed_image = Image.open(self.selected_image_path).convert("RGBA")
            
            # 显示预览
            self.show_image_preview(self.processed_image)
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"图片处理失败: {e}")
    
    def show_image_preview(self, pil_image):
        """显示图片预览"""
        # 将PIL图像转换为QPixmap
        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')
        
        data = pil_image.tobytes('raw', 'RGBA')
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        
        # 缩放以适应预览区域
        scaled_pixmap = pixmap.scaled(
            self.preview_label.width(), 
            self.preview_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(scaled_pixmap)
    
    def on_mode_changed(self, index):
        """模式切换时重新处理图片"""
        if self.selected_image_path:
            self.process_and_show_image()
    
    def on_save(self):
        """保存按钮点击"""
        if not self.processed_image:
            QMessageBox.warning(self, "提示", "请先选择图片")
            return
        
        result = {
            'original_path': self.selected_image_path,
            'image': self.processed_image,
            'mode': self.mode_combo.currentText()
        }
        self.signal_binding_complete.emit(result)
        self.accept()


class AreaDrawDialog(QDialog):
    """区域绘制对话框 - 使用PyQt原生组件绘制区域"""
    signal_draw_complete = pyqtSignal(dict)

    def __init__(self, parent=None, image_path=None, area_name="", existing_coords=None):
        super().__init__(parent)
        self.setWindowTitle(f"绘制区域 - {area_name}")
        self.setGeometry(100, 100, 1000, 800)

        self.area_name = area_name
        self.existing_coords = existing_coords or []
        self.image_path = image_path
        self.is_drawing = True  # 是否处于绘制状态

        self.init_ui()

        # 加载图片和已有坐标
        if self.image_path and os.path.exists(self.image_path):
            self.draw_label.set_image(self.image_path)
            if self.existing_coords:
                # 优化1：存在原绘制区时，加载坐标但禁止添加新点
                self.draw_label.set_points([list(coord) for coord in self.existing_coords])
                self.draw_label.set_adding_enabled(False)
                self.is_drawing = False  # 不处于绘制状态
            else:
                self.draw_label.set_adding_enabled(True)
                self.is_drawing = True

    def init_ui(self):
        """初始化UI - 使用DrawImageLabel"""
        layout = QVBoxLayout(self)

        # 按钮区域
        btn_layout = QHBoxLayout()

        self.clear_btn = QPushButton("清除")
        self.clear_btn.clicked.connect(self.clear_draw)
        btn_layout.addWidget(self.clear_btn)

        self.undo_btn = QPushButton("撤销")
        self.undo_btn.clicked.connect(self.undo_last_point)
        btn_layout.addWidget(self.undo_btn)

        self.complete_btn = QPushButton("完成")
        self.complete_btn.clicked.connect(self.complete_draw)
        btn_layout.addWidget(self.complete_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        # 添加缩放提示
        hint_label = QLabel("滚轮缩放 | 中键平移 | 左键添加/拖动顶点 | 点击边中点插入顶点 | 右键结束绘制 | 完成按钮保存")
        hint_label.setStyleSheet("color: #666; font-size: 12px;")
        btn_layout.addWidget(hint_label)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 使用DrawImageLabel
        self.draw_label = DrawImageLabel(editable=True)
        self.draw_label.signal_right_click.connect(self.on_right_click)
        layout.addWidget(self.draw_label)

    def clear_draw(self):
        """清除绘制"""
        self.draw_label.clear_points()
        # 优化1：清除后启用添加新点功能
        self.is_drawing = True
        self.draw_label.set_editable(True)
        self.draw_label.set_adding_enabled(True)

    def undo_last_point(self):
        """撤销上一个点"""
        self.draw_label.undo_last_point()

    def complete_draw(self):
        """完成绘制 - 只有点击完成按钮才会调用此方法"""
        points = self.draw_label.get_points()
        if len(points) < 3:
            QMessageBox.warning(self, "提示", "至少需要3个点才能形成区域")
            return

        # 结束绘制状态
        self.is_drawing = False
        self.draw_label.set_editable(False)

        result = {
            'name': self.area_name,
            'coords': points
        }
        self.signal_draw_complete.emit(result)

        # 显示完成提示，让用户选择是否关闭
        reply = QMessageBox.question(self, "绘制完成", "区域绘制完成！\n是否关闭绘制窗口？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.accept()
        else:
            # 重新启用编辑，允许继续修改
            self.is_drawing = True
            self.draw_label.set_editable(True)

    def on_right_click(self):
        """右键点击 - 仅结束绘制状态（停止添加新点），不完成绘制"""
        if self.is_drawing and len(self.draw_label.get_points()) >= 3:
            # 结束绘制状态，禁止继续添加顶点，但可以拖动现有顶点
            self.is_drawing = False
            self.draw_label.set_editable(True)  # 保持可编辑以允许拖动顶点
            self.draw_label.set_adding_enabled(False)  # 禁止添加新点
            QMessageBox.information(self, "提示", "已结束绘制，您可以拖动顶点调整位置，\n或点击'完成'按钮保存区域。")
        elif len(self.draw_label.get_points()) < 3:
            QMessageBox.warning(self, "提示", "至少需要3个点才能形成区域")
        

class DrawImageLabel(QLabel):
    """支持绘制的图片Label - 支持滚轮缩放和边中点插入"""
    signal_point_added = pyqtSignal(int, int)
    signal_right_click = pyqtSignal()
    signal_point_moved = pyqtSignal(int, int, int)  # index, new_x, new_y
    signal_midpoint_added = pyqtSignal(int, int, int)  # edge_index, x, y

    def __init__(self, parent=None, editable=False):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")

        self.pixmap_original = None
        self.points = []  # 当前正在绘制的点
        self.existing_coords = []  # 已存在的区域坐标

        # 基础缩放因子（适应窗口）
        self.base_scale_factor = 1.0
        # 用户缩放因子
        self.zoom_factor = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 5.0

        self.scale_factor = 1.0  # 总缩放因子 = base_scale_factor * zoom_factor
        self.offset_x = 0
        self.offset_y = 0
        self.pan_x = 0  # 平移X
        self.pan_y = 0  # 平移Y
        self.is_panning = False
        self.last_mouse_pos = None

        # 编辑模式
        self.editable = editable
        self.adding_enabled = True  # 是否允许添加新点
        self.dragging_point_index = -1  # 正在拖动的点索引
        self.hover_point_index = -1  # 鼠标悬停的点索引
        self.hover_midpoint_index = -1  # 悬停的边中点索引
        self.hidden_midpoint_edges = []  # 拖动时隐藏的边中点索引

        # 样式配置
        # 优化1：边粗一倍，点放大两倍
        self.style_config = {
            'stroke_color': QColor(0, 120, 215),  # 蓝色边线
            'stroke_width': 4,  # 边粗一倍（原来是2）
            'fill_color': QColor(0, 120, 215, 60),  # 蓝色填充，透明度约25%
            'point_outer_color': QColor(0, 120, 215),  # 顶点外圈蓝色
            'point_inner_color': QColor(255, 255, 255),  # 顶点中心白色
            'point_size': 16,  # 顶点外圈大小，放大两倍（原来是8）
            'point_inner_size': 8,  # 顶点中心大小，放大两倍（原来是4）
            'midpoint_outer_color': QColor(255, 255, 255),  # 边中点外圈白色
            'midpoint_inner_color': QColor(0, 120, 215),  # 边中点中心蓝色
            'midpoint_size': 12,  # 边中点外圈大小，放大两倍（原来是6）
            'midpoint_inner_size': 6,  # 边中点中心大小，放大两倍（原来是3）
            'existing_stroke_color': QColor(0, 0, 255),
            'existing_fill_color': QColor(0, 0, 255, 30)
        }

    def set_image(self, image_path):
        """设置图片"""
        self.pixmap_original = QPixmap(image_path)
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_display()

    def set_points(self, points):
        """设置点列表"""
        self.points = points
        self.update_display()

    def clear_points(self):
        """清除所有点"""
        self.points = []
        self.update_display()

    def set_existing_coords(self, coords):
        """设置已存在的区域坐标"""
        self.existing_coords = coords
        self.update_display()

    def get_points(self):
        """获取当前点列表"""
        return self.points.copy()

    def undo_last_point(self):
        """撤销最后一个点"""
        if self.points:
            self.points.pop()
            self.update_display()

    def set_editable(self, editable):
        """设置编辑状态"""
        self.editable = editable
        self.update_display()

    def set_adding_enabled(self, enabled):
        """设置是否允许添加新点"""
        self.adding_enabled = enabled
        self.update_display()

    def _optimize_collinear_points(self):
        """优化共线点：当一条边上有3个或更多共线点时，中间所有点合并为一个并居中"""
        if len(self.points) < 3:
            return

        def point_to_line_distance(px, py, x1, y1, x2, y2):
            """计算点到直线的距离"""
            if abs(x2 - x1) < 0.001 and abs(y2 - y1) < 0.001:
                return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            return abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / ((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5

        def is_point_on_line(px, py, x1, y1, x2, y2, tolerance=5):
            """检查点是否在直线上（容忍度为像素误差）"""
            return point_to_line_distance(px, py, x1, y1, x2, y2) <= tolerance

        # 遍历每条边（连续的顶点对）
        i = 0
        while i < len(self.points):
            # 获取当前边的两个端点
            start_idx = i
            start_x = self.points[start_idx][0] * self.scale_factor + self.offset_x
            start_y = self.points[start_idx][1] * self.scale_factor + self.offset_y

            # 找到这条边的终点（下一个不在当前直线上的点）
            end_idx = start_idx + 1
            while end_idx < len(self.points):
                end_x = self.points[end_idx][0] * self.scale_factor + self.offset_x
                end_y = self.points[end_idx][1] * self.scale_factor + self.offset_y

                # 检查从start到end之间的所有点是否都在直线上
                all_collinear = True
                for j in range(start_idx + 1, end_idx):
                    px = self.points[j][0] * self.scale_factor + self.offset_x
                    py = self.points[j][1] * self.scale_factor + self.offset_y
                    if not is_point_on_line(px, py, start_x, start_y, end_x, end_y):
                        all_collinear = False
                        break

                if not all_collinear:
                    # 上一个点是最后一个共线点
                    end_idx -= 1
                    break

                end_idx += 1

            # 如果end_idx超出了范围，使用最后一个点
            if end_idx >= len(self.points):
                end_idx = len(self.points) - 1

            # 如果这条边上有3个或更多点（即中间有至少1个点）
            if end_idx - start_idx >= 2:
                # 计算中间所有点的平均位置
                mid_x = sum(self.points[j][0] for j in range(start_idx + 1, end_idx)) // (end_idx - start_idx - 1)
                mid_y = sum(self.points[j][1] for j in range(start_idx + 1, end_idx)) // (end_idx - start_idx - 1)

                # 保留起点和终点，中间所有点替换为一个平均点
                self.points = self.points[:start_idx + 1] + [[mid_x, mid_y]] + self.points[end_idx:]
                # 不增加i，继续检查下一条边
            else:
                i += 1

    def _calculate_scale_and_offset(self):
        """计算缩放因子和偏移量"""
        if not self.pixmap_original:
            return

        # 计算基础缩放（适应窗口）
        scale_x = self.width() / self.pixmap_original.width()
        scale_y = self.height() / self.pixmap_original.height()
        self.base_scale_factor = min(scale_x, scale_y)

        # 应用用户缩放
        self.scale_factor = self.base_scale_factor * self.zoom_factor

        # 计算图片显示尺寸
        display_width = self.pixmap_original.width() * self.scale_factor
        display_height = self.pixmap_original.height() * self.scale_factor

        # 计算偏移（居中 + 平移）
        self.offset_x = (self.width() - display_width) / 2 + self.pan_x
        self.offset_y = (self.height() - display_height) / 2 + self.pan_y

    def _get_midpoints(self):
        """计算边中点"""
        midpoints = []
        if len(self.points) < 2:
            return midpoints

        for i in range(len(self.points)):
            next_i = (i + 1) % len(self.points)
            # 如果区域未闭合（少于3个点），不计算最后一条边的中点
            if i == len(self.points) - 1 and len(self.points) < 3:
                break

            mid_x = (self.points[i][0] + self.points[next_i][0]) / 2
            mid_y = (self.points[i][1] + self.points[next_i][1]) / 2
            midpoints.append({
                'x': mid_x,
                'y': mid_y,
                'edge_index': i
            })
        return midpoints

    def _get_midpoint_at_position(self, x, y):
        """获取指定位置上的边中点索引"""
        cfg = self.style_config
        midpoints = self._get_midpoints()

        for i, mp in enumerate(midpoints):
            px = int(mp['x'] * self.scale_factor + self.offset_x)
            py = int(mp['y'] * self.scale_factor + self.offset_y)

            # 检查是否在中点范围内
            # 使用更精确的检测范围，只检测边中点的外圈范围内
            size = cfg['midpoint_size'] // 2 + 2  # 边中点半径 + 2像素容错
            # 使用圆形检测更精确
            dx = x - px
            dy = y - py
            if dx * dx + dy * dy <= size * size:
                return mp['edge_index']
        return -1

    def update_display(self):
        """更新显示 - 借鉴高德地图样式"""
        if not self.pixmap_original:
            return

        self._calculate_scale_and_offset()

        # 创建空白画布
        display_pixmap = QPixmap(self.width(), self.height())
        display_pixmap.fill(QColor(240, 240, 240))

        painter = QPainter(display_pixmap)
        # 优化2：启用抗锯齿，消除边锯齿
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 计算可见区域
        img_display_width = self.pixmap_original.width() * self.scale_factor
        img_display_height = self.pixmap_original.height() * self.scale_factor

        # 绘制图片（只绘制可见部分）
        visible_x = max(0, -self.offset_x)
        visible_y = max(0, -self.offset_y)
        visible_width = min(img_display_width, self.width() - self.offset_x) - max(0, -self.offset_x)
        visible_height = min(img_display_height, self.height() - self.offset_y) - max(0, -self.offset_y)

        if visible_width > 0 and visible_height > 0:
            source_rect = QRect(
                int(visible_x / self.scale_factor),
                int(visible_y / self.scale_factor),
                int(visible_width / self.scale_factor),
                int(visible_height / self.scale_factor)
            )
            target_rect = QRect(
                int(self.offset_x + visible_x),
                int(self.offset_y + visible_y),
                int(visible_width),
                int(visible_height)
            )
            painter.drawPixmap(target_rect, self.pixmap_original, source_rect)

        cfg = self.style_config

        # 绘制已存在的区域（半透明虚线）
        if self.existing_coords and len(self.existing_coords) >= 3:
            pen = QPen(cfg['existing_stroke_color'], cfg['stroke_width'], Qt.PenStyle.DashLine)
            brush = QBrush(cfg['existing_fill_color'])
            painter.setPen(pen)
            painter.setBrush(brush)

            points = []
            for coord in self.existing_coords:
                x = int(coord[0] * self.scale_factor + self.offset_x)
                y = int(coord[1] * self.scale_factor + self.offset_y)
                points.append(QPoint(x, y))
            painter.drawPolygon(points)

        # 绘制边中点（白圈蓝中心）- 跳过拖动时隐藏的边
        if self.editable and len(self.points) >= 2:
            midpoints = self._get_midpoints()
            for i, mp in enumerate(midpoints):
                # 跳过拖动顶点时相邻两边的中心点
                if i in self.hidden_midpoint_edges:
                    continue

                x = int(mp['x'] * self.scale_factor + self.offset_x)
                y = int(mp['y'] * self.scale_factor + self.offset_y)

                # 悬停的中点用不同大小
                if i == self.hover_midpoint_index:
                    outer_size = cfg['midpoint_size'] + 2
                    inner_size = cfg['midpoint_inner_size'] + 1
                else:
                    outer_size = cfg['midpoint_size']
                    inner_size = cfg['midpoint_inner_size']

                # 绘制外圈（白色）
                painter.setBrush(QBrush(cfg['midpoint_outer_color']))
                painter.setPen(QPen(cfg['midpoint_inner_color'], 1))
                painter.drawEllipse(x - outer_size//2, y - outer_size//2, outer_size, outer_size)
                # 绘制内圈（蓝色）
                painter.setBrush(QBrush(cfg['midpoint_inner_color']))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x - inner_size//2, y - inner_size//2, inner_size, inner_size)

        # 绘制当前正在绘制的区域（蓝色边框+蓝色填充）
        if len(self.points) >= 2:
            # 如果有3个或更多点，填充区域
            if len(self.points) >= 3:
                pen = QPen(cfg['stroke_color'], cfg['stroke_width'])
                brush = QBrush(cfg['fill_color'])
                painter.setPen(pen)
                painter.setBrush(brush)

                points = []
                for point in self.points:
                    x = int(point[0] * self.scale_factor + self.offset_x)
                    y = int(point[1] * self.scale_factor + self.offset_y)
                    points.append(QPoint(x, y))
                painter.drawPolygon(points)

            # 绘制边线
            pen = QPen(cfg['stroke_color'], cfg['stroke_width'])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for i in range(len(self.points) - 1):
                x1 = int(self.points[i][0] * self.scale_factor + self.offset_x)
                y1 = int(self.points[i][1] * self.scale_factor + self.offset_y)
                x2 = int(self.points[i+1][0] * self.scale_factor + self.offset_x)
                y2 = int(self.points[i+1][1] * self.scale_factor + self.offset_y)
                painter.drawLine(x1, y1, x2, y2)

            # 如果区域闭合（3个或更多点），绘制最后一条边
            if len(self.points) >= 3:
                x1 = int(self.points[-1][0] * self.scale_factor + self.offset_x)
                y1 = int(self.points[-1][1] * self.scale_factor + self.offset_y)
                x2 = int(self.points[0][0] * self.scale_factor + self.offset_x)
                y2 = int(self.points[0][1] * self.scale_factor + self.offset_y)
                painter.drawLine(x1, y1, x2, y2)

        # 绘制顶点（蓝圈白中心）
        for i, point in enumerate(self.points):
            x = int(point[0] * self.scale_factor + self.offset_x)
            y = int(point[1] * self.scale_factor + self.offset_y)

            # 悬停的点用不同大小
            if i == self.hover_point_index:
                outer_size = cfg['point_size'] + 2
                inner_size = cfg['point_inner_size'] + 1
            else:
                outer_size = cfg['point_size']
                inner_size = cfg['point_inner_size']

            # 绘制外圈（蓝色）
            painter.setBrush(QBrush(cfg['point_outer_color']))
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawEllipse(x - outer_size//2, y - outer_size//2, outer_size, outer_size)
            # 绘制内圈（白色）
            painter.setBrush(QBrush(cfg['point_inner_color']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x - inner_size//2, y - inner_size//2, inner_size, inner_size)

        painter.end()
        self.setPixmap(display_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()

    def wheelEvent(self, event):
        """滚轮缩放"""
        if not self.pixmap_original:
            return

        # 获取鼠标位置
        mouse_x = event.position().x()
        mouse_y = event.position().y()

        # 计算鼠标在图片中的相对位置（缩放前）
        img_x = (mouse_x - self.offset_x) / self.scale_factor
        img_y = (mouse_y - self.offset_y) / self.scale_factor

        # 计算新的缩放因子
        delta = event.angleDelta().y()
        if delta > 0:
            new_zoom = self.zoom_factor * 1.1
        else:
            new_zoom = self.zoom_factor / 1.1

        # 限制缩放范围
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))

        if new_zoom != self.zoom_factor:
            self.zoom_factor = new_zoom

            # 重新计算缩放因子
            self._calculate_scale_and_offset()

            # 调整平移量，使鼠标位置保持对应图片上的同一点
            self.pan_x = mouse_x - img_x * self.scale_factor - (self.width() - self.pixmap_original.width() * self.scale_factor) / 2
            self.pan_y = mouse_y - img_y * self.scale_factor - (self.height() - self.pixmap_original.height() * self.scale_factor) / 2

            self.update_display()

    def mousePressEvent(self, event):
        if not self.pixmap_original:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击了边中点（插入新点）- 编辑模式下始终允许插入边中点
            if self.editable and len(self.points) >= 2:
                midpoint_edge = self._get_midpoint_at_position(event.pos().x(), event.pos().y())
                if midpoint_edge >= 0:
                    # 计算边中点坐标
                    next_i = (midpoint_edge + 1) % len(self.points)
                    mid_x = int((self.points[midpoint_edge][0] + self.points[next_i][0]) / 2)
                    mid_y = int((self.points[midpoint_edge][1] + self.points[next_i][1]) / 2)

                    # 在边中点插入新点
                    insert_index = next_i
                    self.points.insert(insert_index, [mid_x, mid_y])
                    self.dragging_point_index = insert_index
                    self.signal_midpoint_added.emit(midpoint_edge, mid_x, mid_y)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.update_display()
                    return

            # 检查是否点击了现有点（开始拖动）- 拖动时为拳头型
            if self.editable and len(self.points) >= 3:
                clicked_point_index = self._get_point_at_position(event.pos().x(), event.pos().y())
                if clicked_point_index >= 0:
                    self.dragging_point_index = clicked_point_index
                    # 设置隐藏的边中点（相邻两边的中心点）
                    self.hidden_midpoint_edges = []
                    prev_edge = (clicked_point_index - 1) % len(self.points)
                    curr_edge = clicked_point_index % len(self.points)
                    self.hidden_midpoint_edges = [prev_edge, curr_edge]
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)  # 拳头型
                    self.update_display()
                    return

            # 添加新点 - 只有允许添加时才可添加
            if self.adding_enabled:
                img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
                img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)

                # 确保坐标在图片范围内
                if 0 <= img_x <= self.pixmap_original.width() and 0 <= img_y <= self.pixmap_original.height():
                    self.points.append([img_x, img_y])
                    self.signal_point_added.emit(img_x, img_y)
                    self.update_display()

        elif event.button() == Qt.MouseButton.RightButton:
            self.signal_right_click.emit()

        elif event.button() == Qt.MouseButton.MiddleButton:
            # 中键按下开始平移
            self.is_panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 悬停效果和拖动"""
        if not self.pixmap_original:
            return

        # 平移模式
        if self.is_panning and self.last_mouse_pos:
            delta_x = event.pos().x() - self.last_mouse_pos.x()
            delta_y = event.pos().y() - self.last_mouse_pos.y()
            self.pan_x += delta_x
            self.pan_y += delta_y
            self.last_mouse_pos = event.pos()
            self.update_display()
            return

        # 编辑模式：拖动顶点 - 保持拳头型
        if self.editable and self.dragging_point_index >= 0:
            img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
            img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)

            # 限制在图片范围内
            img_x = max(0, min(img_x, self.pixmap_original.width()))
            img_y = max(0, min(img_y, self.pixmap_original.height()))

            # 更新点位置
            self.points[self.dragging_point_index] = [img_x, img_y]
            self.signal_point_moved.emit(self.dragging_point_index, img_x, img_y)
            self.update_display()
            return

        # 编辑模式：检查悬停 - 悬停时变为手型
        if self.editable:
            # 检查边中点悬停
            if len(self.points) >= 2:
                hover_midpoint = self._get_midpoint_at_position(event.pos().x(), event.pos().y())
                if hover_midpoint != self.hover_midpoint_index:
                    self.hover_midpoint_index = hover_midpoint
                    # 悬停边中点时显示手型
                    self.setCursor(Qt.CursorShape.OpenHandCursor if hover_midpoint >= 0 else Qt.CursorShape.ArrowCursor)
                    self.update_display()
                    if hover_midpoint >= 0:
                        return

            # 检查顶点悬停
            if len(self.points) >= 3:
                hover_index = self._get_point_at_position(event.pos().x(), event.pos().y())
                if hover_index != self.hover_point_index:
                    self.hover_point_index = hover_index
                    # 悬停顶点时显示手型
                    self.setCursor(Qt.CursorShape.OpenHandCursor if hover_index >= 0 else Qt.CursorShape.ArrowCursor)
                    self.update_display()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.last_mouse_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif self.editable and self.dragging_point_index >= 0:
            released_index = self.dragging_point_index
            self.dragging_point_index = -1

            # 检查拖动结束后是否存在多点共线的情况
            if len(self.points) >= 3:
                self._optimize_collinear_points_after_drag(released_index)

            # 清除隐藏的边中点
            self.hidden_midpoint_edges = []

            # 问题2修复：释放后检查鼠标是否仍在顶点上方，如果是则显示手型
            hover_index = self._get_point_at_position(event.pos().x(), event.pos().y())
            if hover_index >= 0:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

            self.update_display()

    def _get_point_at_position(self, x, y):
        """获取指定位置上的点索引"""
        cfg = self.style_config
        for i, point in enumerate(self.points):
            px = int(point[0] * self.scale_factor + self.offset_x)
            py = int(point[1] * self.scale_factor + self.offset_y)

            # 检查是否在点的范围内（考虑点的大小）
            # 使用更精确的检测范围，只检测点的外圈范围内
            size = cfg['point_size'] // 2 + 2  # 点半径 + 2像素容错
            # 使用圆形检测更精确
            dx = x - px
            dy = y - py
            if dx * dx + dy * dy <= size * size:
                return i
        return -1

    def _are_three_points_collinear(self, p1, p2, p3, angle_tolerance=10):
        """检查三个点是否共线（使用角度判断，180±10度）"""
        import math

        # 转换为屏幕坐标检查
        x1 = p1[0] * self.scale_factor + self.offset_x
        y1 = p1[1] * self.scale_factor + self.offset_y
        x2 = p2[0] * self.scale_factor + self.offset_x
        y2 = p2[1] * self.scale_factor + self.offset_y
        x3 = p3[0] * self.scale_factor + self.offset_x
        y3 = p3[1] * self.scale_factor + self.offset_y

        # 计算向量 p2->p1 和 p2->p3
        dx1 = x1 - x2
        dy1 = y1 - y2
        dx2 = x3 - x2
        dy2 = y3 - y2

        # 计算两个向量的长度
        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

        # 如果任一向量长度为0，说明点重合，不认为共线
        if len1 < 0.001 or len2 < 0.001:
            return False

        # 计算点积
        dot_product = dx1 * dx2 + dy1 * dy2

        # 计算夹角（弧度）
        cos_angle = dot_product / (len1 * len2)
        # 限制cos_angle范围在[-1, 1]内，避免浮点误差
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle_rad = math.acos(cos_angle)
        angle_deg = math.degrees(angle_rad)

        print(f"[角度判断] 向量1: ({dx1:.2f}, {dy1:.2f}), 长度: {len1:.2f}")
        print(f"[角度判断] 向量2: ({dx2:.2f}, {dy2:.2f}), 长度: {len2:.2f}")
        print(f"[角度判断] 点积: {dot_product:.2f}, cos角度: {cos_angle:.4f}")
        print(f"[角度判断] 角度: {angle_deg:.2f}度, 与180度差值: {abs(angle_deg - 180):.2f}度")

        # 判断角度是否接近180度（允许±10度误差）
        result = abs(angle_deg - 180) <= angle_tolerance
        print(f"[角度判断] 是否共线: {result} (阈值: ±{angle_tolerance}度)")
        return result

    def _optimize_collinear_points_after_drag(self, dragged_index):
        """
        拖动点后优化共线点
        场景：A,B,C,D,E,F,G，其中B,D,F为中心点
        当移动C至A和E之间位置时，取消B,C,D三点，以AE为顶点形成新边并生成中心点
        """
        import math

        if len(self.points) < 3:
            print(f"[共线优化] 点数不足3个，跳过优化")
            return

        print(f"\n[共线优化] 开始优化，拖动点索引: {dragged_index}")
        print(f"[共线优化] 当前所有点: {self.points}")

        # 简化逻辑：只检查 dragged_index 的左右相邻点是否共线
        # 如果共线，删除 dragged_index，在两端点中点生成新点
        # 然后继续检查新的相邻点是否共线

        # 获取左右相邻点
        prev_idx = (dragged_index - 1) % len(self.points)
        next_idx = (dragged_index + 1) % len(self.points)

        prev_point = self.points[prev_idx]
        dragged_point = self.points[dragged_index]
        next_point = self.points[next_idx]

        print(f"[共线优化] 检查相邻三点: prev_idx={prev_idx}, dragged_idx={dragged_index}, next_idx={next_idx}")
        print(f"[共线优化] 点坐标: prev={prev_point}, dragged={dragged_point}, next={next_point}")

        # 检查三点是否共线
        is_collinear = self._are_three_points_collinear(prev_point, dragged_point, next_point)
        print(f"[共线优化] 共线判断结果: {is_collinear}")

        if is_collinear:
            print(f"[共线优化] 三点共线，执行合并")

            # 删除 dragged_index（中间点），不插入新点
            # 因为 prev 和 next 已经形成直线
            del self.points[dragged_index]
            print(f"[共线优化] 删除索引{dragged_index}（中间点），点总数减少1")

            print(f"[共线优化] 优化后所有点: {self.points}")
        else:
            print(f"[共线优化] 三点不共线，不执行合并")


class AreaMapTab(QWidget):
    """区域地图Tab页 - 显示一级区域的图片和设备"""
    signal_device_clicked = pyqtSignal(str)
    signal_area_control = pyqtSignal(dict)
    
    def __init__(self, parent=None, level1_area=None, image_path=None, db_pool=None, device_model=None, device_cols_index=None):
        super().__init__(parent)
        
        self.level1_area = level1_area
        self.image_path = image_path
        self.db_pool = db_pool
        self.device_model = device_model
        self.device_cols_index = device_cols_index
        self.sub_areas = []  # 子区域列表
        self.filtered_areas = []  # 筛选后的区域
        
        # 定时刷新定时器
        self.refresh_timer = None
        
        self.init_ui()
        self.load_data()
        self.start_auto_refresh()
        
    def init_ui(self):
        """初始化UI - 区域筛选悬浮于背景图左上角"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建主容器（用于悬浮布局）
        self.main_container = QWidget()
        self.main_container.setLayout(QVBoxLayout())
        self.main_container.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.main_container)
        
        # 图片显示（只读模式，不支持拖动）
        self.image_label = AreaImageLabel(editable=False)
        self.image_label.signal_device_clicked.connect(self.on_device_clicked)
        self.image_label.signal_area_clicked.connect(self.on_area_clicked)
        # 设置device_model和device_cols_index引用，用于获取设备实时数据
        self.image_label.device_model = self.device_model
        self.image_label.device_cols_index = self.device_cols_index
        
        # 加载图片
        _log.debug(f"AreaMapTab.init_ui: 准备加载图片, image_path={self.image_path}")
        if self.image_path and os.path.exists(self.image_path):
            _log.debug(f"AreaMapTab.init_ui: 图片文件存在，开始加载")
            self.image_label.set_image(self.image_path)
        else:
            _log.warning(f"AreaMapTab.init_ui: 图片未绑定或不存在: {self.image_path}")
            self.image_label.setText("未绑定图片")
            
        self.main_container.layout().addWidget(self.image_label)
        
        # 创建悬浮的区域筛选面板（位于左上角）
        self.filter_panel = QFrame(self.main_container)
        self.filter_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        self.filter_panel.setFixedWidth(200)
        self.filter_panel.setFixedHeight(250)
        
        filter_layout = QVBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(8, 8, 8, 8)
        filter_layout.setSpacing(4)
        
        # 区域树标题
        tree_label = QLabel("区域筛选")
        tree_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        filter_layout.addWidget(tree_label)
        
        # 区域树
        self.area_tree = QTreeView()
        self.area_tree.setStyleSheet("""
            QTreeView {
                background-color: transparent;
                border: none;
            }
            QTreeView::item {
                padding: 2px;
            }
        """)
        self.area_model = QStandardItemModel()
        self.area_model.setHorizontalHeaderLabels(["区域"])
        self.area_tree.setModel(self.area_model)
        self.area_tree.setHeaderHidden(True)
        self.area_tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.area_tree.clicked.connect(self.on_area_selected)
        filter_layout.addWidget(self.area_tree)
        
        # 重置筛选按钮
        self.reset_filter_btn = QPushButton("显示全部")
        self.reset_filter_btn.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
        """)
        self.reset_filter_btn.setFixedHeight(28)
        self.reset_filter_btn.clicked.connect(self.reset_filter)
        filter_layout.addWidget(self.reset_filter_btn)
        
        # 初始位置（会在resize事件中更新）
        self.filter_panel.move(10, 10)
        self.filter_panel.show()
        
    def set_sub_areas(self, areas):
        """设置子区域数据"""
        self.sub_areas = areas
        self.filtered_areas = areas.copy()
        self.refresh_area_tree()
        self.refresh_display()
        
    def refresh_area_tree(self):
        """刷新区域树"""
        self.area_model.clear()
        self.area_model.setHorizontalHeaderLabels(["区域"])
        
        # 添加"全部"选项
        all_item = QStandardItem("全部区域")
        all_item.setData("__ALL__", Qt.ItemDataRole.UserRole)
        self.area_model.appendRow(all_item)
        
        # 添加子区域
        for area in self.sub_areas:
            self._add_area_to_tree(area, self.area_model.invisibleRootItem())
            
    def _add_area_to_tree(self, area, parent_item):
        """递归添加区域到树"""
        item = QStandardItem(area.get('name', ''))
        item.setData(area, Qt.ItemDataRole.UserRole)
        parent_item.appendRow(item)
        
        # 递归添加子区域
        for child in area.get('children', []):
            self._add_area_to_tree(child, item)
            
    def on_area_selected(self, index):
        """区域被选中"""
        item = self.area_model.itemFromIndex(index)
        if not item:
            return
            
        area_data = item.data(Qt.ItemDataRole.UserRole)
        
        if area_data == "__ALL__":
            self.filtered_areas = self.sub_areas.copy()
        else:
            # 筛选选中区域及其子区域
            self.filtered_areas = [area_data]
            
        self.refresh_display()
        
    def reset_filter(self):
        """重置筛选"""
        self.filtered_areas = self.sub_areas.copy()
        self.refresh_display()
        # 选中"全部"
        self.area_tree.setCurrentIndex(self.area_model.index(0, 0))
        
    def refresh_display(self):
        """刷新显示"""
        # 收集所有需要显示的区域
        areas_to_show = []
        
        def collect_areas(area_list):
            for area in area_list:
                areas_to_show.append(area)
                collect_areas(area.get('children', []))
                
        collect_areas(self.filtered_areas)
        
        # 准备区域绘制数据
        draw_areas = []
        for area in areas_to_show:
            area_data = area.get('area', {})
            coords = area_data.get('coords', [])
            if coords:
                draw_areas.append({
                    'name': area.get('name', ''),
                    'coords': coords
                })
                
        self.image_label.set_areas(draw_areas)
        
        # 准备设备数据
        self.refresh_devices()
        
    def refresh_devices(self):
        """刷新设备显示 - 根据筛选的区域过滤设备"""
        devices = []
        
        # 获取所有筛选区域的名称（包括子区域）
        filtered_area_names = set()
        def collect_area_names(area_list):
            for area in area_list:
                area_name = area.get('name', '')
                if area_name:
                    filtered_area_names.add(area_name)
                # 递归收集子区域
                collect_area_names(area.get('children', []))
        
        collect_area_names(self.filtered_areas)
        
        _log.debug(f"refresh_devices: 筛选区域: {filtered_area_names}")
        _log.debug(f"refresh_devices: 一级区域: {self.level1_area}")
        
        # 遍历所有设备
        for row in range(self.device_model.rowCount()):
            area1_item = self.device_model.item(row, self.device_cols_index.get("区域1", -1))
            area2_item = self.device_model.item(row, self.device_cols_index.get("区域2", -1))
            area3_item = self.device_model.item(row, self.device_cols_index.get("区域3", -1))
            
            if not area1_item:
                continue
            
            dev_area1 = area1_item.text() if area1_item else ""
            dev_area2 = area2_item.text() if area2_item else ""
            dev_area3 = area3_item.text() if area3_item else ""
            
            # 首先检查是否属于当前一级区域
            if dev_area1 != self.level1_area:
                continue
            
            # 检查设备是否属于筛选的区域
            # 如果筛选了特定区域（不是全部），则检查设备是否在筛选区域内
            is_in_filtered_area = False
            if not filtered_area_names or self.level1_area in filtered_area_names:
                # 显示全部或筛选了一级区域本身，显示所有设备
                is_in_filtered_area = True
            else:
                # 检查设备的二级或三级区域是否在筛选列表中
                if dev_area2 in filtered_area_names:
                    is_in_filtered_area = True
                elif dev_area3 in filtered_area_names:
                    is_in_filtered_area = True
            
            if not is_in_filtered_area:
                continue
            
            device_id_item = self.device_model.item(row, self.device_cols_index.get("设备号", -1))
            device_name_item = self.device_model.item(row, self.device_cols_index.get("设备名称", -1))
            online_item = self.device_model.item(row, self.device_cols_index.get("在线状态", -1))
            
            device_id = device_id_item.text() if device_id_item else ""
            
            # 从数据库获取设备位置
            x, y = self._get_device_position_in_area(None, device_id)
            
            if x is not None and y is not None:
                devices.append({
                    'id': device_id,
                    'name': device_name_item.text() if device_name_item else device_id,
                    'x': x,
                    'y': y,
                    'is_online': online_item.text() == "在线" if online_item else False
                })
        
        _log.debug(f"refresh_devices: 共找到 {len(devices)} 个设备")
        
        # 去重
        seen_ids = set()
        unique_devices = []
        for dev in devices:
            if dev['id'] not in seen_ids:
                seen_ids.add(dev['id'])
                unique_devices.append(dev)
                
        self.image_label.set_devices(unique_devices)
        
    def start_auto_refresh(self):
        """启动自动刷新定时器"""
        from PyQt6.QtCore import QTimer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(5000)  # 每5秒刷新一次设备状态
        _log.debug(f"AreaMapTab {self.level1_area}: 启动自动刷新定时器")
    
    def stop_auto_refresh(self):
        """停止自动刷新定时器"""
        if self.refresh_timer:
            self.refresh_timer.stop()
            _log.debug(f"AreaMapTab {self.level1_area}: 停止自动刷新定时器")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.stop_auto_refresh()
        super().closeEvent(event)
        
    def resizeEvent(self, event):
        """窗口大小改变时更新悬浮面板位置"""
        super().resizeEvent(event)
        if hasattr(self, 'filter_panel'):
            self.filter_panel.move(10, 10)
        
    def _get_device_position_in_area(self, area, device_id):
        """获取设备在区域中的位置 - 从数据库的相对X和相对Y字段获取"""
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 使用正确的字段名：相对X 和 相对Y
                    cursor.execute(
                        "SELECT `相对X`, `相对Y` FROM device_info WHERE 设备号 = %s",
                        (device_id,)
                    )
                    result = cursor.fetchone()
                    if result and result['相对X'] is not None and result['相对Y'] is not None:
                        return int(float(result['相对X'])), int(float(result['相对Y']))
        except Exception as e:
            _log.error(f"获取设备 {device_id} 位置失败: {e}")
        
        # 如果没有保存的位置，使用区域中心作为默认位置
        if area is not None:
            area_data = area.get('area', {})
            coords = area_data.get('coords', [])
            
            if len(coords) >= 3:
                center_x = sum(c[0] for c in coords) / len(coords)
                center_y = sum(c[1] for c in coords) / len(coords)
                return int(center_x), int(center_y)
            
        return None, None
        
    def on_device_clicked(self, device_id):
        """设备被点击"""
        self.signal_device_clicked.emit(device_id)
        
    def on_area_clicked(self, area_name, x, y):
        """区域被点击"""
        pass
        
    def load_data(self):
        """加载数据"""
        pass


class Platform(QMainWindow, Ui_MainWindow):
    signal_mess_show = pyqtSignal(object, object)
    signal_chart_update = pyqtSignal()
    signal_chart_data_ready = pyqtSignal(list, list, list, int, int, int, list, list, str, str)
    signal_db_error = pyqtSignal(str)
    signal_db_reconnect_success = pyqtSignal()
    signal_request_devices_info = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow
        self.setupUi(self)

        self.ver = "0.0.3"
        self.setWindowTitle(f"智控平台 V{self.ver}")

        # 下载模板地址
        self.url = "http://opr.iotdirvers.com:83/导入模板.xlsx"
        self.err_list, self.set_flg = get_err_config("./config/err_list.ini")

        _log.debug(f"==========智控平台 V{self.ver}=============")
        
        # 消息界面
        self.mess_ui = Messbox()
        _log.debug(f"==========消息界面初始化完成=============")
        
        # 发送指令模板
        self.send_order = {
            "login_reply": {"SN": "", "TM": "", "SV": "rept", "ID": "", "CT": "L"},
            "time_reply": {"SN": "", "TM": "", "SV": "rqst", "ID": "", "CT": "R", "DT": {"TmCali": 1}},
            "read": {"SN": "", "TM": "", "SV": "prop", "ID": "", "CT": "R",
                     "DT": {"props": ["EleInfo", "RunSts", "Signal", "PerSts", "RunTm", "Dim"]}},
            "on": {"SN": "", "TM": "", "SV": "ctrl", "ID": "", "CT": "W",
                   "DT": {"cnCtrl": [{"cns": 1, "last": 0, "bri": 100}]}},
            "off": {"SN": "", "TM": "", "SV": "ctrl", "ID": "", "CT": "W",
                    "DT": {"cnCtrl": [{"cns": 1, "last": 0, "bri": 0}]}},
            "dimming": {"SN": "", "TM": "", "SV": "ctrl", "ID": "", "CT": "W",
                        "DT": {"cnCtrl": [{"cns": 1, "last": 0, "bri": 50}]}},
            "initialize_1": {"SN": "", "TM": "", "SV": "ctrl", "ID": "", "CT": "W", "DT": {"restore": 5}},
            "Dim": {"SN": "", "TM": "", "ID": "", "SV": "prop", "CT": "W", "DT": {"Dim": [{"cns": 1, "rti": "667"}]}}
        }

        # MQTT主题配置
        self.topic_config = {
            "pub": "MS/#/plt2dev",
            "sub": "MS/#/dev2plt",
        }

        self.outline_time = app_config.outline_time
        self.every_online_rate = []

        self.permission_level = True
        self.console_hwnd = self.get_console_window_handle()
        
        self.db_pool = self.init_db_pool()
        _log.debug(f"==========数据库连接池初始化完成=============")
        
        self.redis_client = self.init_redis()
        _log.debug(f"==========Redis连接初始化完成=============")
        
        self._start_redis_reconnect_timer()

        # 登录界面
        self.login_dialog = LogIn(self.db_pool)
        self.login_dialog.signal_main_exit.connect(self.show_over_time_ui)
        self.login_dialog.exec()
        _log.debug(f"==========登录完成=============")

        # 设置当前用户信息
        self.current_username = self.login_dialog.usr_passwd.split(' ')[0]
        _log.debug(f"当前登录用户: {self.current_username}")

        # 初始化图片存储目录
        self.picture_dir = os.path.join(os.path.dirname(__file__), "picture")
        if not os.path.exists(self.picture_dir):
            os.makedirs(self.picture_dir)
            _log.debug(f"创建图片目录: {self.picture_dir}")

        self.area_list = get_area_dict(self.current_username, self.db_pool)
        _log.debug(f"区域列表更新为：{self.area_list}")
        self.update_area_serch()
        self.UI_area_treeView.treeview_init(self.area_list)
        _log.debug(f"==========区域、区域搜索、区域划分树初始化完成=============")

        # 统一设备表格模型
        self.apply_col_config, self.apply_key_cols, self.apply_FLOAT_cols, self.apply_DATETIME_cols = get_col_apply(self.db_pool)
        
        self.history_ui = History(self.apply_key_cols, self.db_pool)
        
        self.device_cols_name = ["应用勾选", "管理勾选", "设备号", "设备名称", "区域1", "区域2", "区域3", "相对X", "相对Y", "添加日期", "工作计划", "编辑", "删除"]
        
        self.device_cols_name.append("在线状态")
        self.device_cols_name.extend(list(self.apply_col_config.keys()))
        self.device_cols_name.append("历史数据")
        
        self.device_cols_index = {name: i for i, name in enumerate(self.device_cols_name)}
        
        self.dm_hidden_cols = ["应用勾选"] + list(self.apply_col_config.keys()) + ["历史数据", "工作计划"]
        self.apply_hidden_cols = ["管理勾选", "相对X", "相对Y",  "添加日期", "编辑", "删除", "区域1", "区域2", "区域3", "工作计划"]
        
        self.device_model = QStandardItemModel(0, len(self.device_cols_name))
        self.device_model.setHorizontalHeaderLabels(self.device_cols_name)
        
        self._load_device_data()
        
        FLOAT_cols = ["设备号"] + self.apply_FLOAT_cols
        DATETIME_cols = ["添加日期"] + self.apply_DATETIME_cols
        
        self.dm_filter_proxy = ConfigurableSortProxy(FLOAT_cols, DATETIME_cols)
        self.dm_filter_proxy.setSourceModel(self.device_model)
        self.dm_filter_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.dm_filter_proxy.setDynamicSortFilter(True)
        
        self.apply_filter_proxy = ConfigurableSortProxy(FLOAT_cols, DATETIME_cols)
        self.apply_filter_proxy.setSourceModel(self.device_model)
        self.apply_filter_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.apply_filter_proxy.setDynamicSortFilter(True)
        
        # 设备管理视图配置
        self.UI_dm_device_tableView.setModel(self.dm_filter_proxy)
        for col_name in self.dm_hidden_cols:
            if col_name in self.device_cols_index:
                self.UI_dm_device_tableView.hideColumn(self.device_cols_index[col_name])
        self.UI_dm_device_tableView.set_item_delegate(self.device_cols_index["管理勾选"], CheckBoxDelegate(self))
        edit_delegate = OptimizedButtonDelegate(self.device_cols_index["编辑"], "编辑", self.UI_dm_device_tableView)
        edit_delegate.signal_button_click.connect(self.dm_btn_edit_click)
        self.UI_dm_device_tableView.set_item_delegate(self.device_cols_index["编辑"], edit_delegate)
        delete_delegate = OptimizedButtonDelegate(self.device_cols_index["删除"], "删除", self.UI_dm_device_tableView)
        delete_delegate.signal_button_click.connect(self.dm_btn_delete_click)
        self.UI_dm_device_tableView.set_item_delegate(self.device_cols_index["删除"], delete_delegate)
        self.UI_dm_device_tableView.horizontalHeader().setSortIndicatorShown(True)
        self.UI_dm_device_tableView.horizontalHeader().setSectionsClickable(True)
        self.UI_dm_device_tableView.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.UI_dm_device_tableView.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.UI_dm_device_tableView.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.UI_dm_device_tableView.horizontalHeader().sectionClicked.connect(
            lambda column: self._handle_sort_click(self.UI_dm_device_tableView, self.dm_filter_proxy, column)
        )
        
        # 应用视图配置
        self.UI_apply_tableview.setModel(self.apply_filter_proxy)
        for col_name in self.apply_hidden_cols:
            if col_name in self.device_cols_index:
                self.UI_apply_tableview.hideColumn(self.device_cols_index[col_name])
        self.UI_apply_tableview.set_item_delegate(self.device_cols_index["应用勾选"], CheckBoxDelegate(self))
        history_delegate = OptimizedButtonDelegate(self.device_cols_index["历史数据"], "历史数据", self.UI_apply_tableview)
        history_delegate.signal_button_click.connect(self.apply_btn_history_click)
        self.UI_apply_tableview.set_item_delegate(self.device_cols_index["历史数据"], history_delegate)
        self.UI_apply_tableview.horizontalHeader().setSortIndicatorShown(True)
        self.UI_apply_tableview.horizontalHeader().setSectionsClickable(True)
        self.UI_apply_tableview.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.UI_apply_tableview.setColumnWidth(self.device_cols_index["应用勾选"], 60)
        self.UI_apply_tableview.setColumnWidth(self.device_cols_index["设备号"], 125)
        header = self.UI_apply_tableview.horizontalHeader()
        for i in range(1, len(self.device_cols_name)):
            header.setMinimumSectionSize(100)
        self.UI_apply_tableview.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.UI_apply_tableview.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.UI_apply_tableview.horizontalHeader().sectionClicked.connect(
            lambda column: self._handle_sort_click(self.UI_apply_tableview, self.apply_filter_proxy, column)
        )

        # MQTT初始化
        mqtt_config = app_config.get_mqtt_config()
        MQTT_config = [
            mqtt_config['host'],
            mqtt_config['port'],
            mqtt_config['username'] + "_device" + str(randint(1000, 9999)),
            1
        ]
        self.client = MqttThread(MQTT_config)
        self.client.signal_mqtt_connected.connect(self.mqtt_connect)
        self.client.signal_mqtt_message_received.connect(self.receive_data)
        self.client.start()

        # 初始化设备数据处理器
        self.data_processor = DeviceDataProcessor(max_workers=30)
        self.data_processor.device_model = self.device_model
        self.data_processor.device_cols_index = self.device_cols_index
        self.data_processor.signal_mess_show = self.signal_mess_show
        self.data_processor.client = self.client
        self.data_processor.topic_config = self.topic_config
        self.data_processor.send_order = self.send_order
        self.data_processor.err_list = self.err_list
        self.data_processor.apply_key_cols = self.apply_key_cols
        self.data_processor.apply_FLOAT_cols = self.apply_FLOAT_cols
        self.data_processor.apply_DATETIME_cols = self.apply_DATETIME_cols
        self.data_processor.signal_update_ui.connect(self._update_device_ui)
        self.signal_chart_update.connect(self._update_chart_ui)
        self.signal_chart_data_ready.connect(self._on_chart_data_ready)
        self.signal_request_devices_info.connect(self._on_request_devices_info)

        self._device_row_cache = {}
        self._batch_update_timer = QTimer()
        self._batch_update_timer.timeout.connect(self._process_batch_updates)
        self._batch_update_timer.start(100)
        self._pending_updates = {}

        # 设备在线状态检查线程
        self._online_checker = DeviceOnlineChecker(
            self.device_model,
            self.device_cols_index,
            outline_time=self.outline_time,
            check_interval=10
        )
        self._online_checker.signal_status_changed.connect(self._on_device_status_changed)
        self._online_checker.start()
        _log.debug(f"设备在线状态检查线程已启动，离线阈值: {self.outline_time}秒")

        # 初始化区域地图TabWidget
        self._init_area_map_tabs()

        # 信号槽绑定
        self.signal_slot_bind()

        #================================图标刷新线程=============================================
        self.online_7_linecanvas = None # 7天在线率图表
        self.online_pie_canvas = None # 在线率饼图
        self.electricity_7_linecanvas = None # 7天用电量图表
        self.power_24h_linecanvas = None # 24小时功率图表
        self.display_interface_chart_update() # 启动图表更新线程

    def _init_area_map_tabs(self):
        """初始化区域地图TabWidget"""
        _log.debug(f"_init_area_map_tabs: 开始初始化区域地图TabWidget, picture_dir={self.picture_dir}")
        _log.debug(f"_init_area_map_tabs: area_list={self.area_list}")
        
        # 清除旧的地图显示
        if hasattr(self, 'map_layout') and self.map_layout:
            while self.map_layout.count():
                item = self.map_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            # 使用展示界面的tab (self.tab) 的 verticalLayout_3
            self.map_layout = self.verticalLayout_3
        
        # 处理所有一级区域的图片路径
        for level1_area in self.area_list:
            area_name = level1_area.get('name', '')
            area_data = level1_area.get('area', {})
            
            # 获取图片路径
            image_path = area_data.get('image_path', '')
            path = area_data.get('path', '')
            
            # 确定图片文件名
            if image_path:
                file_name = image_path
            elif path:
                file_name = os.path.basename(path)
            else:
                file_name = ''
            
            # 检查本地是否已有图片
            if file_name:
                local_path = os.path.join(self.picture_dir, file_name)
                if os.path.exists(local_path):
                    image_path = file_name
                elif path:
                    # 尝试从服务器下载
                    download_url = f"http://localhost/upload{path}"
                    downloaded_file = self._download_area_background_image(area_name, download_url, path)
                    if downloaded_file:
                        area_data['image_path'] = downloaded_file
                        level1_area['area'] = area_data
                        image_path = downloaded_file
            
            # 拼接完整路径
            if image_path and not os.path.isabs(image_path):
                image_path = os.path.join(self.picture_dir, image_path)
        
        # 创建展示界面Widget，直接插入到布局中
        from area_display_widget import AreaDisplayWidget
        
        # 获取第一个区域的图片作为默认图片
        first_area = self.area_list[0] if self.area_list else {}
        first_area_data = first_area.get('area', {}) if first_area else {}
        default_image_path = first_area_data.get('image_path', '')
        if default_image_path and not os.path.isabs(default_image_path):
            default_image_path = os.path.join(self.picture_dir, default_image_path)
        
        self.area_display_widget = AreaDisplayWidget(
            parent=self,
            level1_area='展示界面',
            image_path=default_image_path if os.path.exists(default_image_path) else None,
            db_pool=self.db_pool,
            device_model=self.device_model,
            device_cols_index=self.device_cols_index
        )
        
        # 传递完整的区域层次结构给图表区域筛选（包含所有1级、2级、3级区域）
        self.area_display_widget.set_full_area_hierarchy(self.area_list)
        
        # 传递所有一级区域作为地图选项
        all_level1_areas = []
        for a in self.area_list:
            area_data = a.get('area', {})
            img_path = area_data.get('image_path', '')
            if img_path:
                full_img_path = os.path.join(self.picture_dir, img_path)
                if os.path.exists(full_img_path):
                    from PyQt6.QtCore import QUrl
                    img_url = QUrl.fromLocalFile(full_img_path).toString()
                else:
                    img_url = ''
            else:
                img_url = ''
            all_level1_areas.append({
                'name': a.get('name', ''),
                'image_path': img_url
            })
        
        first_area_name = self.area_list[0].get('name', '') if self.area_list else ''
        self.area_display_widget.set_map_areas(all_level1_areas, first_area_name)
        self.area_display_widget.signal_device_clicked.connect(self.on_map_device_clicked)
        # 连接图表区域筛选信号
        self.area_display_widget.bridge.signal_chart_filter_changed.connect(self._on_html_chart_filter_changed)
        
        # 直接添加到布局，不使用TabWidget
        self.map_layout.addWidget(self.area_display_widget)
        
        _log.debug(f"_init_area_map_tabs: 展示界面初始化完成，包含 {len(self.area_list)} 个一级区域")

    def _init_charts_widget(self):
        """初始化HTML图表Widget"""
        try:
            # 创建图表显示Widget
            self.charts_widget = QWidget()
            charts_layout = QVBoxLayout(self.charts_widget)
            charts_layout.setContentsMargins(0, 0, 0, 0)
            
            # 创建WebEngineView来显示HTML图表
            self.charts_web_view = QWebEngineView()
            charts_layout.addWidget(self.charts_web_view)
            
            # 设置WebChannel
            self.charts_channel = QWebChannel()
            self.charts_bridge = ChartBridge()
            self.charts_bridge.signal_area_confirmed.connect(self._on_chart_area_confirmed)
            self.charts_channel.registerObject('bridge', self.charts_bridge)
            self.charts_web_view.page().setWebChannel(self.charts_channel)
            
            # 加载HTML图表页面
            html_path = os.path.join(os.path.dirname(__file__), 'static', 'charts_display.html')
            if os.path.exists(html_path):
                # 传递区域列表参数
                from urllib.parse import quote
                areas_json = json.dumps(self.area_list, ensure_ascii=False)
                url = QUrl.fromLocalFile(html_path)
                url.setQuery(f"areas={quote(areas_json)}")
                self.charts_web_view.setUrl(url)
                _log.debug(f"图表页面已加载: {html_path}")
            else:
                _log.error(f"图表HTML文件不存在: {html_path}")
                self.charts_web_view.setHtml("<h1>错误: 找不到图表页面文件</h1>")
            
            # 添加到分割器
            self.display_splitter.addWidget(self.charts_widget)
            
            # 设置分割比例（地图占60%，图表占40%）
            self.display_splitter.setSizes([600, 400])
            
            _log.debug("HTML图表Widget初始化完成")
        except Exception as e:
            _log.error(f"初始化HTML图表Widget失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_charts_area_list(self):
        """更新图表中的区域列表"""
        if hasattr(self, 'charts_web_view') and self.charts_web_view:
            areas_json = json.dumps(self.area_list, ensure_ascii=False)
            js_code = f"""
                if (typeof updateAreaList === 'function') {{
                    updateAreaList({areas_json});
                }}
            """
            self.charts_web_view.page().runJavaScript(js_code)

    def _load_device_data(self):
        """加载设备数据到统一模型"""
        usr = self.login_dialog.usr_passwd.split(' ')[0]
        order = "SELECT * FROM device_info WHERE 账户 = %s"
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(order, (usr,))
                    devices = cursor.fetchall()
                    for device in devices:
                        add_device_default_row(self.device_model, self.apply_col_config, device)
        except Exception as e:
            _log.error(f"加载设备数据失败: {e}")
            traceback.print_exc()

    def init_db_pool(self):
        """创建并返回数据库连接池"""
        self.db_manager = DatabaseConnectionManager(self)
        db_config = app_config.get_db_config()
        success = self.db_manager.init_pool(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database']
        )
        if success:
            return self.db_manager.db_pool
        else:
            return None

    def init_redis(self):
        """初始化Redis连接"""
        try:
            redis_config = app_config.get_redis_config()
            from redis.connection import ConnectionPool
            pool = ConnectionPool(
                host=redis_config['host'],
                port=redis_config['port'],
                password=redis_config['password'],
                db=redis_config['db'],
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=30,
                max_connections=20
            )
            redis_client = Redis(connection_pool=pool)
            redis_client.ping()
            _log.info("Redis连接成功")
            return redis_client
        except Exception as e:
            _log.warning(f"Redis连接失败: {e}，将继续使用MySQL查询")
            return None

    def _start_redis_reconnect_timer(self):
        """启动Redis重连定时器"""
        self._redis_reconnect_timer = QTimer(self)
        self._redis_reconnect_timer.timeout.connect(self._try_redis_reconnect)
        self._redis_reconnect_timer.start(30000)
        _log.debug("Redis重连定时器已启动（30秒间隔）")

    def _try_redis_reconnect(self):
        """尝试重新连接Redis"""
        if self.redis_client:
            try:
                self.redis_client.ping()
                return
            except Exception:
                _log.warning("Redis连接已断开，尝试重连...")
                self.redis_client = None
        
        try:
            self.redis_client = self.init_redis()
            if self.redis_client:
                _log.info("Redis重连成功")
        except Exception as e:
            _log.debug(f"Redis重连失败: {e}")

    def _stop_redis_reconnect_timer(self):
        """停止Redis重连定时器"""
        if hasattr(self, '_redis_reconnect_timer') and self._redis_reconnect_timer:
            self._redis_reconnect_timer.stop()
            _log.debug("Redis重连定时器已停止")

    def show_db_error_dialog(self, error_msg):
        """显示数据库连接错误弹窗"""
        from PyQt6.QtWidgets import QMessageBox
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("数据库连接错误")
        msg_box.setText(f"无法连接到数据库服务器！\n\n错误信息：{error_msg}\n\n系统将在后台尝试自动重连。")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        msg_box.exec()
        
    def on_db_reconnect_success(self):
        """数据库重连成功处理"""
        from PyQt6.QtWidgets import QMessageBox
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("连接恢复")
        msg_box.setText("数据库连接已恢复！")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
        
        _log.info("数据库连接已恢复，系统恢复正常运行")

    def show_over_time_ui(self):
        """用户不进行登录操纵，直接退出软件"""
        self._stop_redis_reconnect_timer()
        
        for window in QApplication.topLevelWidgets():
            window.close()
        QApplication.quit()
        sys.exit(0)

    def console_hide(self, level):
        """控制台隐藏"""
        if not self.permission_level:
            if platform.system() == "Windows" and (hasattr(sys, 'frozen') and getattr(sys, 'frozen')):
                try:
                    if not self.console_hwnd:
                        self.console_hwnd = self.get_console_window_handle()
                    if self.console_hwnd:
                        ShowWindow(self.console_hwnd, SW_HIDE)
                        _log.debug("控制台已隐藏（打包环境）")
                    else:
                        _log.warning("无法获取控制台窗口句柄，无法隐藏控制台")
                except ImportError:
                    _log.error("未安装pywin32，无法隐藏控制台")
        else:
            if platform.system() == "Windows" and (hasattr(sys, 'frozen') and getattr(sys, 'frozen')):
                try:
                    if not self.console_hwnd:
                        self.console_hwnd = self.get_console_window_handle()
                    if self.console_hwnd:
                        ShowWindow(self.console_hwnd, SW_SHOW)
                    else:
                        _log.warning("无法获取控制台窗口句柄，无法显示控制台")
                except ImportError:
                    _log.error("未安装pywin32，无法显示控制台")

    def get_console_window_handle(self):
        """获取程序自己的控制台窗口句柄"""
        if HAS_WIN32CONSOLE and platform.system() == "Windows":
            try:
                return win32console.GetConsoleWindow()
            except:
                pass
        return GetForegroundWindow()

    def signal_slot_bind(self):
        """信号槽绑定"""
        self.signal_mess_show.connect(self.mess_ui.show_message)

        self.UI_area_add_btn.clicked.connect(self.UI_area_treeView.add_child)
        self.UI_area_edit_btn.clicked.connect(self.UI_area_treeView.edit_current)
        self.UI_area_del_btn.clicked.connect(self.on_area_delete_clicked)
        self.UI_area_treeView.signal_area_change.connect(self.update_area_dict)
        self.UI_area_treeView.signal_area_renamed.connect(self.on_area_renamed)

        self.UI_single_add_btn.clicked.connect(self.UI_single_add_btn_clicked)
        self.UI_more_add_btn.clicked.connect(self.UI_more_add_btn_clicked)
        self.UI_template_down_btn.clicked.connect(self.UI_template_down_btn_clicked)

        # 区域绘制按钮
        self.UI_area_divide_btn.clicked.connect(self.map_area_start_draw)
        self.UI_dm_search_btn.clicked.connect(self.dm_serch)

        # 应用界面
        self.UI_all_nall_btn.clicked.connect(self.all_nall_check)
        self.UI_read_send.clicked.connect(partial(self.send, "read", self.UI_read_send))
        self.UI_on_send.clicked.connect(partial(self.send, "on", self.UI_on_send))
        self.UI_off_send.clicked.connect(partial(self.send, "off", self.UI_off_send))
        self.UI_dimming_send.clicked.connect(partial(self.send, "dimming", self.UI_dimming_send))
        self.UI_dimming_in_1.sliderMoved.connect(partial(self.dimming_input_change, self.UI_dimming_in_1))
        self.UI_dimming_in_2.editingFinished.connect(partial(self.dimming_input_change, self.UI_dimming_in_2))
        self.UI_search_btn.clicked.connect(self.apply_serch)

        # GPS坐标编辑按钮
        self.UI_alter_location_btn.clicked.connect(self.open_location_edit_dialog)

    def open_location_edit_dialog(self):
        """打开设备定位编辑对话框（批量编辑模式）"""
        try:
            from batch_location_dialog import BatchLocationDialog
            dialog = BatchLocationDialog(
                parent=self,
                db_pool=self.db_pool,
                device_model=self.device_model,
                area_list=self.area_list,
                device_cols_index=self.device_cols_index,
                picture_dir=self.picture_dir
            )
            dialog.signal_positions_saved.connect(self.on_location_coordinates_updated)
            dialog.exec()
        except Exception as e:
            _log.error(f"打开设备定位编辑对话框失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"打开设备定位编辑对话框失败: {e}")

    def on_location_coordinates_updated(self, updated_devices):
        """设备坐标更新后的处理 - 保存到数据库并刷新显示"""
        try:
            if not updated_devices:
                return
            
            # 保存到数据库
            saved_count = 0
            for device_data in updated_devices:
                device_id = device_data.get('id', '')
                new_x = device_data.get('x', 0)
                new_y = device_data.get('y', 0)
                row = device_data.get('row', -1)
                
                if device_id and row >= 0:
                    # 更新数据库
                    self._save_device_position_to_db(device_id, new_x, new_y)
                    
                    # 更新界面模型
                    x_col = self.device_cols_index.get("相对X", -1)
                    y_col = self.device_cols_index.get("相对Y", -1)
                    if x_col >= 0:
                        self.device_model.item(row, x_col).setText(str(new_x))
                    if y_col >= 0:
                        self.device_model.item(row, y_col).setText(str(new_y))
                    
                    saved_count += 1
            
            # 刷新区域地图显示
            self.refresh_area_map_display()
            
            self.show_message(f"成功更新 {saved_count} 个设备的位置", "success")
            _log.info(f"设备位置已更新: {saved_count} 个设备")
            
        except Exception as e:
            _log.error(f"处理设备坐标更新失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_device_position_to_db(self, device_id, x, y):
        """保存设备位置到数据库"""
        try:
            conn = self.db_pool.connection()
            cursor = conn.cursor()
            
            sql = """
                UPDATE device_info 
                SET `相对X` = %s, `相对Y` = %s 
                WHERE `设备号` = %s
            """
            cursor.execute(sql, (x, y, device_id))
            conn.commit()
            cursor.close()
            conn.close()
            
            _log.debug(f"设备 {device_id} 位置已保存到数据库: ({x}, {y})")
            
        except Exception as e:
            _log.error(f"保存设备 {device_id} 位置到数据库失败: {e}")
            raise

    def refresh_area_map_display(self):
        """刷新区域地图显示"""
        if hasattr(self, 'area_display_widget') and self.area_display_widget:
            self.area_display_widget.refresh_devices()

    def on_map_device_clicked(self, device_id):
        """地图上的设备被点击 - 显示设备详情弹窗"""
        _log.debug(f"点击了地图上的设备: {device_id}")
        try:
            from device_detail_dialog import DeviceDetailDialog
            dialog = DeviceDetailDialog(
                device_id=device_id,
                device_model=self.device_model,
                device_cols_index=self.device_cols_index,
                parent=self
            )
            dialog.signal_control_command.connect(self.on_device_control_command)
            dialog.signal_request_data.connect(self.on_device_request_data)
            dialog.exec()
        except Exception as e:
            _log.error(f"打开设备详情弹窗失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_device_control_command(self, device_id, command):
        """处理设备控制命令"""
        _log.info(f"设备控制命令: {device_id}, 命令: {command}")
        # TODO: 实现设备控制命令发送（MQTT或其他方式）
        self.show_message(f"设备 {device_id} 控制命令: {command}", "info")
    
    def on_device_request_data(self, device_id):
        """请求设备实时数据"""
        _log.debug(f"请求设备实时数据: {device_id}")
        # TODO: 实现从MQTT或数据库获取实时数据
        # 目前数据会从device_model中自动刷新

    def on_area_delete_clicked(self):
        """删除区域按钮点击 - 先同步更新设备区域，再删除区域"""
        item, level = self.UI_area_treeView.get_current_item_level()
        if not item:
            QMessageBox.warning(self, "提示", "请选择节点")
            return
        if level == 1:
            QMessageBox.warning(self, "提示", "区域划分不可删除")
            return
        
        area_name = item.text()
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除区域 '{area_name}' 吗？\n\n删除后将清空该区域内所有设备的区域信息！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 获取被删除区域的所有子区域名称
        deleted_areas = self._get_area_and_children(item)
        _log.debug(f"删除区域 '{area_name}' 及其子区域: {deleted_areas}")
        
        # 同步更新设备和数据库
        self._sync_device_areas_on_delete(deleted_areas, level)
        
        # 执行删除
        parent = item.parent()
        if parent:
            parent.removeRow(item.row())
            self.UI_area_treeView.signal_area_change.emit()
    
    def _get_area_and_children(self, item):
        """获取区域及其所有子区域的名称列表"""
        areas = [item.text()]
        
        def collect_children(parent_item):
            for row in range(parent_item.rowCount()):
                child = parent_item.child(row)
                areas.append(child.text())
                collect_children(child)
        
        collect_children(item)
        return areas
    
    def _sync_device_areas_on_delete(self, deleted_areas, deleted_level):
        """删除区域时同步更新设备的区域信息"""
        if not deleted_areas:
            return
        
        area1_col = self.device_cols_index.get("区域1", -1)
        area2_col = self.device_cols_index.get("区域2", -1)
        area3_col = self.device_cols_index.get("区域3", -1)
        device_id_col = self.device_cols_index.get("设备号", -1)
        
        if area1_col < 0 or device_id_col < 0:
            _log.error("设备模型中缺少必要的列")
            return
        
        updated_count = 0
        
        # 遍历所有设备
        for row in range(self.device_model.rowCount()):
            device_id_item = self.device_model.item(row, device_id_col)
            area1_item = self.device_model.item(row, area1_col)
            area2_item = self.device_model.item(row, area2_col) if area2_col >= 0 else None
            area3_item = self.device_model.item(row, area3_col) if area3_col >= 0 else None
            
            if not device_id_item or not area1_item:
                continue
            
            device_id = device_id_item.text()
            dev_area1 = area1_item.text() if area1_item else ""
            dev_area2 = area2_item.text() if area2_item else ""
            dev_area3 = area3_item.text() if area3_item else ""
            
            needs_update = False
            new_area2 = dev_area2
            new_area3 = dev_area3
            
            # 根据删除的区域级别判断需要清空哪些字段
            if deleted_level == 2:  # 删除一级区域
                if dev_area1 in deleted_areas:
                    # 设备属于被删除的一级区域，清空区域2和区域3
                    needs_update = True
                    new_area2 = ""
                    new_area3 = ""
            elif deleted_level == 3:  # 删除二级区域
                if dev_area2 in deleted_areas:
                    # 设备属于被删除的二级区域，清空区域2和区域3
                    needs_update = True
                    new_area2 = ""
                    new_area3 = ""
            elif deleted_level == 4:  # 删除三级区域
                if dev_area3 in deleted_areas:
                    # 设备属于被删除的三级区域，只清空区域3
                    needs_update = True
                    new_area3 = ""
            
            if needs_update:
                # 更新数据模型
                if area2_item:
                    area2_item.setText(new_area2)
                if area3_item:
                    area3_item.setText(new_area3)
                
                # 同步更新数据库
                self._update_device_area_in_db(device_id, new_area2, new_area3)
                updated_count += 1
                _log.debug(f"更新设备 {device_id} 的区域信息: 区域2={new_area2}, 区域3={new_area3}")
        
        if updated_count > 0:
            self.show_message(f"已同步更新 {updated_count} 个设备的区域信息", "success")
            _log.info(f"删除区域后同步更新了 {updated_count} 个设备的区域信息")
        
        # 清除被删除区域的Redis缓存
        if deleted_level == 2:  # 删除一级区域
            for area_name in deleted_areas:
                self._clear_area_cache_from_redis(area_name)
                _log.info(f"区域删除: 已清除区域 '{area_name}' 的Redis缓存")

    def on_area_renamed(self, old_name, new_name, level):
        """区域重命名时同步更新设备的区域信息"""
        _log.info(f"区域重命名: {old_name} -> {new_name}, 级别: {level}")

        area1_col = self.device_cols_index.get("区域1", -1)
        area2_col = self.device_cols_index.get("区域2", -1)
        area3_col = self.device_cols_index.get("区域3", -1)
        device_id_col = self.device_cols_index.get("设备号", -1)

        if area1_col < 0 or device_id_col < 0:
            _log.error("设备模型中缺少必要的列")
            return

        updated_count = 0

        # 遍历所有设备
        for row in range(self.device_model.rowCount()):
            device_id_item = self.device_model.item(row, device_id_col)
            area1_item = self.device_model.item(row, area1_col)
            area2_item = self.device_model.item(row, area2_col) if area2_col >= 0 else None
            area3_item = self.device_model.item(row, area3_col) if area3_col >= 0 else None

            if not device_id_item or not area1_item:
                continue

            device_id = device_id_item.text()
            dev_area1 = area1_item.text() if area1_item else ""
            dev_area2 = area2_item.text() if area2_item else ""
            dev_area3 = area3_item.text() if area3_item else ""

            needs_update = False
            new_area1 = dev_area1
            new_area2 = dev_area2
            new_area3 = dev_area3

            # 根据区域级别判断需要更新哪个字段
            if level == 2:  # 一级区域重命名
                if dev_area1 == old_name:
                    needs_update = True
                    new_area1 = new_name
            elif level == 3:  # 二级区域重命名
                if dev_area2 == old_name:
                    needs_update = True
                    new_area2 = new_name
            elif level == 4:  # 三级区域重命名
                if dev_area3 == old_name:
                    needs_update = True
                    new_area3 = new_name

            if needs_update:
                # 更新数据模型
                area1_item.setText(new_area1)
                if area2_item:
                    area2_item.setText(new_area2)
                if area3_item:
                    area3_item.setText(new_area3)

                # 同步更新数据库
                self._update_device_area_in_db_rename(device_id, new_area1, new_area2, new_area3)
                updated_count += 1
                _log.debug(f"更新设备 {device_id} 的区域信息: 区域1={new_area1}, 区域2={new_area2}, 区域3={new_area3}")

        if updated_count > 0:
            self.show_message(f"已同步更新 {updated_count} 个设备的区域信息", "success")
            _log.info(f"区域重命名后同步更新了 {updated_count} 个设备的区域信息")
        
        # 清除旧区域名称的Redis缓存
        if level == 2:  # 一级区域重命名
            self._clear_area_cache_from_redis(old_name)
            _log.info(f"区域重命名: 已清除旧区域 '{old_name}' 的Redis缓存")

    def _update_device_area_in_db_rename(self, device_id, area1, area2, area3):
        """更新数据库中设备的区域信息（重命名时使用）"""
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    sql = """
                        UPDATE device_info
                        SET `区域1` = %s, `区域2` = %s, `区域3` = %s
                        WHERE `设备号` = %s
                    """
                    cursor.execute(sql, (area1, area2, area3, device_id))
                    conn.commit()
                    _log.debug(f"数据库更新设备 {device_id} 区域信息成功")
        except Exception as e:
            _log.error(f"数据库更新设备 {device_id} 区域信息失败: {e}")

    def _update_device_area_in_db(self, device_id, area2, area3):
        """更新数据库中设备的区域信息"""
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    sql = """
                        UPDATE device_info 
                        SET `区域2` = %s, `区域3` = %s 
                        WHERE `设备号` = %s
                    """
                    cursor.execute(sql, (area2, area3, device_id))
                    conn.commit()
                    _log.debug(f"数据库更新设备 {device_id} 区域信息成功")
        except Exception as e:
            _log.error(f"数据库更新设备 {device_id} 区域信息失败: {e}")

    def map_area_start_draw(self):
        """打开绘制区域对话框"""
        item, level = self.UI_area_treeView.get_current_item_level()
        if not item:
            self.mess_ui.show_message("请选择一个区域")
            return
            
        area_name = item.text()
        existing_area_data = item.data(Qt.ItemDataRole.UserRole) or {}
        
        _log.debug(f"选中区域: {area_name}, 级别: {level}")
        _log.debug(f"已绑定的区域数据：{existing_area_data}")

        # 一级区域需要绑定图片
        if level == 2:  # 一级区域（根节点是level=1）
            # 检查是否已有图片
            image_path = existing_area_data.get('image_path', '')
            if image_path:
                # 已有图片，询问是否覆盖
                reply = QMessageBox.question(
                    self, 
                    "确认", 
                    f"一级区域 '{area_name}' 已绑定图片: {image_path}\n是否重新绑定新图片？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # 打开图片绑定对话框（支持暗黑/明亮模式选择）
            dialog = AreaImageBindingDialog(self, area_name=area_name)
            dialog.signal_binding_complete.connect(
                lambda data: self.on_image_binding_complete(item, area_name, data)
            )
            dialog.exec()
                
        elif level >= 3:  # 二级、三级区域
            # 需要找到所属的一级区域（level=2）
            parent = item.parent()
            parent_level = level - 1
            
            # 向上遍历直到找到一级区域（level=2）
            while parent and parent_level > 2:
                parent = parent.parent()
                parent_level -= 1
                
            if not parent or parent_level != 2:
                QMessageBox.warning(self, "提示", "无法确定所属一级区域")
                return
                
            parent_name = parent.text()
            parent_data = parent.data(Qt.ItemDataRole.UserRole) or {}
            # 优先使用image_path，如果没有则使用path字段
            image_path = parent_data.get('image_path', '')
            path = parent_data.get('path', '')
            _log.debug(f"二级/三级区域 '{area_name}' 所属一级区域: '{parent_name}', image_path: {image_path}, path: {path}")
            
            # 确定图片文件名
            if image_path:
                file_name = image_path
            elif path:
                # 从path中提取文件名 (path格式: /picture/文件名.png)
                file_name = os.path.basename(path)
            else:
                QMessageBox.warning(self, "提示", "请先为一级区域绑定图片")
                return
                
            full_image_path = os.path.join(self.picture_dir, file_name)
            if not os.path.exists(full_image_path):
                QMessageBox.warning(self, "提示", "一级区域绑定的图片不存在，请重新绑定")
                return
                
            # 打开绘制对话框
            dialog = AreaDrawDialog(
                self,
                image_path=full_image_path,
                area_name=area_name,
                existing_coords=existing_area_data.get('coords', [])
            )
            dialog.signal_draw_complete.connect(lambda data: self.on_draw_complete(item, data))
            dialog.exec()
        else:
            QMessageBox.warning(self, "提示", "根节点不能绑定图片或绘制区域")

    def on_draw_complete(self, item, draw_data):
        """绘制完成回调"""
        area_data = item.data(Qt.ItemDataRole.UserRole) or {}
        area_data['coords'] = draw_data.get('coords', [])
        area_data['area_name'] = draw_data.get('name', '')
        item.setData(area_data, Qt.ItemDataRole.UserRole)
        self.update_area_dict()
        _log.debug(f"区域绘制完成: {draw_data}")

    def on_image_binding_complete(self, item, area_name, binding_data):
        """图片绑定完成回调 - 保存处理后的图片"""
        try:
            original_path = binding_data.get('original_path')
            processed_image = binding_data.get('image')
            mode = binding_data.get('mode', '明亮模式')
            
            if not original_path or not processed_image:
                _log.error("图片绑定数据不完整")
                return
            
            # 生成文件名
            usr = self.login_dialog.usr_passwd.split(" ")[0]
            file_name = f"{usr}_{area_name}.png"
            dest_path = os.path.join(self.picture_dir, file_name)
            
            # 保存处理后的图片
            processed_image.save(dest_path, format="PNG", compress_level=1)
            _log.debug(f"图片已保存到: {dest_path}, 模式: {mode}")
            
            # 生成path字段
            path = f"/picture/{file_name}"
            
            # 上传图片到服务器
            try:
                upload_url = "http://localhost/do_upload.php"
                with open(dest_path, "rb") as f:
                    files = {"file": (file_name, f, "image/png")}
                    response = requests.post(upload_url, files=files, timeout=30)
                
                if response.status_code == 200:
                    response_text = response.text
                    _log.debug(f"上传响应: {response_text[:200]}")
                    
                    if "上传成功" in response_text or "✅" in response_text:
                        _log.debug(f"图片上传成功，path已保存: {path}")
                    else:
                        _log.warning(f"上传响应异常: {response_text[:200]}")
                elif response.status_code == 403:
                    _log.error(f"图片上传失败，状态码: 403 (禁止访问)")
                    QMessageBox.warning(self, "警告", f"图片上传失败: 403禁止访问\n请检查服务器权限设置")
                else:
                    _log.warning(f"图片上传失败，状态码: {response.status_code}")
            except Exception as e:
                _log.error(f"图片上传失败: {e}")
                QMessageBox.warning(self, "警告", f"图片已保存到本地，但上传到服务器失败: {e}")
            
            # 更新区域数据
            existing_area_data = item.data(Qt.ItemDataRole.UserRole) or {}
            existing_area_data['image_path'] = file_name
            existing_area_data['path'] = path
            existing_area_data['display_mode'] = mode  # 保存显示模式
            _log.debug(f"绑定图片: 设置节点数据: {existing_area_data}")
            item.setData(existing_area_data, Qt.ItemDataRole.UserRole)
            
            try:
                self.update_area_dict()
                _log.debug("绑定图片: update_area_dict调用成功")
            except Exception as e:
                _log.error(f"绑定图片: update_area_dict调用失败: {e}")
                import traceback
                traceback.print_exc()
            
            QMessageBox.information(self, "成功", f"已绑定图片: {file_name}\n显示模式: {mode}")
            
        except Exception as e:
            _log.error(f"图片绑定完成处理失败: {e}")
            QMessageBox.warning(self, "错误", f"图片保存失败: {e}")

    def _download_area_background_image(self, area_name, download_url, path):
        """下载区域背景图"""
        try:
            _log.debug(f"开始下载区域背景图: {area_name} -> {download_url}")
            
            # 发送下载请求
            response = requests.get(download_url, timeout=30)
            
            if response.status_code == 200:
                # 从path中提取文件名 (path格式: /picture/账户名_一级区域名.png)
                file_name = os.path.basename(path)
                if not file_name:
                    # 如果path中没有文件名，使用默认格式
                    usr = self.login_dialog.usr_passwd.split(" ")[0]
                    file_name = f"{usr}_{area_name}.png"
                dest_path = os.path.join(self.picture_dir, file_name)
                
                # 保存图片
                with open(dest_path, 'wb') as f:
                    f.write(response.content)
                
                _log.debug(f"区域背景图下载成功: {dest_path}")
                return file_name
            else:
                _log.warning(f"下载区域背景图失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            _log.error(f"下载区域背景图失败: {e}")
            return None

    def update_area_dict(self):
        """更新区域列表以及同步至服务器数据库"""
        self.area_list = self.UI_area_treeView.get_all_sub_areas()
        _log.debug(f"update_area_dict: 从TreeView获取的区域列表: {self.area_list}")
        
        # 为每个一级区域添加level和path字段到area字典中
        usr = self.login_dialog.usr_passwd.split(" ")[0]
        for area in self.area_list:
            if area.get('level') == 1:  # 一级区域 (根据用户数据结构，level=1是一级区域)
                area_name = area.get('name', '')
                area_data = area.get('area', {})
                _log.debug(f"update_area_dict: 处理一级区域 '{area_name}', 当前area数据: {area_data}")
                if 'area' not in area:
                    area['area'] = {}
                # 添加path字段 (格式: /picture/账户名_一级区域名.png)
                path = f"/picture/{usr}_{area_name}.png"
                area['area']['path'] = path
                _log.debug(f"update_area_dict: 为一级区域 '{area_name}' 添加 path={path}, image_path={area['area'].get('image_path', '')}")

        usr = self.login_dialog.usr_passwd.split(" ")[0]
        passwd = self.login_dialog.usr_passwd.split(" ")[1]

        order = "UPDATE sys_user SET 区域信息 = %s WHERE 用户名 = %s AND 密码 = %s;"
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(order, (json.dumps(self.area_list), usr, passwd))
                    conn.commit()
                    _log.debug(f"区域列表同步至服务器数据库：{self.area_list}")
        except Exception as e:
            _log.error(f"区域列表同步至服务器数据库失败: {str(e)}")
            traceback.print_exc()
        else:
            _log.debug(f"区域列表同步至服务器数据库成功")

        # 刷新区域地图Tab
        self._init_area_map_tabs()
        self.update_area_serch()
        self._update_chart_area_filters()

    def _update_chart_area_filters(self):
        """更新所有图表的区域筛选器"""
        try:
            if hasattr(self, 'realtime_pie_area_filter') and self.realtime_pie_area_filter:
                self.realtime_pie_area_filter.update_area_list(self.area_list)
            if hasattr(self, 'online_7d_area_filter') and self.online_7d_area_filter:
                self.online_7d_area_filter.update_area_list(self.area_list)
            if hasattr(self, 'electricity_7d_area_filter') and self.electricity_7d_area_filter:
                self.electricity_7d_area_filter.update_area_list(self.area_list)
            if hasattr(self, 'power_24h_area_filter') and self.power_24h_area_filter:
                self.power_24h_area_filter.update_area_list(self.area_list)
            _log.debug("所有图表区域筛选器已更新")
        except Exception as e:
            _log.error(f"更新图表区域筛选器失败: {e}")

    def UI_single_add_btn_clicked(self):
        """主界面添加单个设备按钮点击"""
        dialog = SingleAddDialog(self.area_list, row=-1)
        dialog.signal_add.connect(self.add_single_device)
        dialog.exec()
    
    def UI_more_add_btn_clicked(self):
        """主界面添加多设备按钮点击"""
        dialog = MoreAddDialog(self.login_dialog.usr_passwd.split(' ')[0], self.db_pool, self.device_model, self.apply_col_config, self.area_list)
        dialog.exec()
        self._clear_online_rate_cache()
        self._clear_ec_cache()
        QTimer.singleShot(500, self.refresh_area_map_display)
        
    def add_single_device(self, row, device_id, device_name, area_1, area_2, area_3, x, y):
        """单设备添加对话框确认添加信号-槽函数"""
        add_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_account = self.login_dialog.usr_passwd.split(' ')[0]
        _log.debug(f"添加单个设备：{row},{device_name}, {device_id} ,{current_account}, {add_datetime}, {area_1}, {area_2}, {area_3}, {x}, {y}")

        order = """
        INSERT INTO device_info (
            `设备名称`, `设备号`, `账户`, `日期`, `区域1`, `区域2`, `区域3`, `相对X`, `相对Y`
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            `设备名称` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`设备名称`), `设备名称`),
            `日期` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`日期`), `日期`),
            `区域1` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`区域1`), `区域1`),
            `区域2` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`区域2`), `区域2`),
            `区域3` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`区域3`), `区域3`),
            `相对X` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`相对X`), `相对X`),
            `相对Y` = IF(`账户`='' OR `账户` IS NULL OR `账户`=VALUES(`账户`), VALUES(`相对Y`), `相对Y`)
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(order, (device_name, device_id, self.login_dialog.usr_passwd.split(' ')[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), area_1, area_2, area_3, x, y))
                    conn.commit()
                    rowcount = cursor.rowcount
        except Exception as e:
            if "1062" in str(e):
                in_flg = is_in_item(self.device_model, self.device_cols_index["设备号"], device_id)
                if in_flg:
                    _log.error(f"添加单个设备：{device_name}, {device_id}, {area_1}, {area_2}, {area_3} 失败: 设备号已存在其他账户")
                else:
                    _log.error(f"添加单个设备：{device_name}, {device_id}, {area_1}, {area_2}, {area_3} 失败: 设备号已存在本地账户")
            else:
                _log.error(f"添加单个设备：{device_name}, {device_id}, {area_1}, {area_2}, {area_3} 失败: {str(e)}")
                traceback.print_exc()
        else:
            _log.debug(f"添加单个设备rowcount：{rowcount}")
            if rowcount == 1:
                device = {
                    "设备号": device_id,
                    "设备名称": device_name,
                    "区域1": area_1,
                    "区域2": area_2,
                    "区域3": area_3,
                    "相对X": x,
                    "相对Y": y,
                    "日期": add_datetime,
                    "工作计划": "{}"
                }
                add_device_default_row(self.device_model, self.apply_col_config, device)
                _log.debug(f"添加单个设备：{device_name}, {device_id}, {current_account}, {area_1}, {area_2}, {area_3}, {x}, {y}, {add_datetime} 成功")
                self._clear_online_rate_cache()
                self._clear_ec_cache()
                self._clear_devices_cache()  # 清除设备缓存
                self.refresh_area_map_display()
            elif rowcount == 2:
                if row != -1:
                    col_name = ["设备名称", "区域1", "区域2", "区域3", "相对X", "相对Y"]
                    datas = [device_name, area_1, area_2, area_3, x, y]
                    for col in range(len(col_name)):
                        item = self.device_model.item(row, self.device_cols_index[col_name[col]])
                        if item:
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            item.setText(str(datas[col]))
                            item.setData(datas[col], Qt.ItemDataRole.DisplayRole)
                    self.device_model.dataChanged.emit(
                        self.device_model.index(row, 0),
                        self.device_model.index(row, self.device_model.columnCount() - 1)
                    )
                    _log.debug(f"更新单个设备：{device_name}, {device_id}, {current_account}, {area_1}, {area_2}, {area_3}, {x}, {y}, {add_datetime} 成功")
                    self.refresh_area_map_display()
                elif row == -1:
                    device = {
                        "设备号": device_id,
                        "设备名称": device_name,
                        "区域1": area_1,
                        "区域2": area_2,
                        "区域3": area_3,
                        "相对X": x,
                        "相对Y": y,
                        "日期": add_datetime,
                        "工作计划": "{}"
                    }
                    add_device_default_row(self.device_model, self.apply_col_config, device)
                    _log.debug(f"添加单个设备：{device_name}, {device_id}, {area_1}, {area_2}, {area_3}, {x}, {y} 成功")
                    self._clear_online_rate_cache()
                    self._clear_ec_cache()
                    self._clear_devices_cache()  # 清除设备缓存
                    self.refresh_area_map_display()
            else:
                with self.db_pool.connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 账户 FROM device_info WHERE 设备号 = %s", (device_id,))
                        db_account = cursor.fetchone()["账户"]
                        
                        if db_account == current_account:
                            _log.error("设备已是自己的，不允许重复操作")
                        else:
                            _log.error(f"设备已被他人占用，占用账户：{db_account}")

    def UI_template_down_btn_clicked(self):
        try:
            session = requests.Session()
            response = session.get(
                self.url,
                headers={"Accept-Encoding": "identity"},
                timeout=15
            )
            response.raise_for_status()

            file_name = "导入模板.xlsx"
            with open(file_name, "wb") as f:
                f.write(response.content)
            QMessageBox.information(self, "成功", "下载成功！" + file_name)
            _log.debug(f"下载成功：{file_name}")

        except Exception as e:
            if "404" in str(e):
                QMessageBox.information(self, "失败", "下载失败！文件不存在")
            elif "13" in str(e):
                QMessageBox.information(self, "失败", "下载失败！本地导入模板已被打开")
            else:
                QMessageBox.information(self, "失败", "下载失败！" + str(e))
                _log.error(f"下载失败：{str(e)}")
            

    def batch_refresh(self, tableView):
        """批量刷新可见区域，减少重绘开销"""
        visible_rect = tableView.viewport().rect()
        top_left = tableView.indexAt(visible_rect.topLeft())
        bottom_right = tableView.indexAt(visible_rect.bottomRight())

        if top_left.isValid() and bottom_right.isValid():
            model = tableView.model()
            for row in range(top_left.row(), bottom_right.row() + 1):
                index = model.index(row, 0)
                tableView.update(index)
            tableView.viewport().update()

    def _handle_sort_click(self, table_view, proxy_model, column):
        """处理表头点击，实现三级排序：升序 -> 降序 -> 恢复默认"""
        proxy_model.sort(column)
        sort_state = proxy_model.get_sort_state(column)
        header = table_view.horizontalHeader()

        if sort_state == 0:
            header.setSortIndicator(column, Qt.SortOrder.AscendingOrder)
            header.setSortIndicatorShown(False)
        elif sort_state == 1:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(column, Qt.SortOrder.AscendingOrder)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(column, Qt.SortOrder.DescendingOrder)

        self.batch_refresh(table_view)
        
    def dm_btn_edit_click(self, index):
        """设备配置表格编辑按钮点击-槽函数"""
        dev_row = index.row()
        name = self.device_model.item(dev_row, self.device_cols_index["设备名称"]).text()
        id = self.device_model.item(dev_row, self.device_cols_index["设备号"]).text()
        area1 = self.device_model.item(dev_row, self.device_cols_index["区域1"]).text()
        area2 = self.device_model.item(dev_row, self.device_cols_index["区域2"]).text()
        area3 = self.device_model.item(dev_row, self.device_cols_index["区域3"]).text()
        x = self.device_model.item(dev_row, self.device_cols_index["相对X"]).text()
        y = self.device_model.item(dev_row, self.device_cols_index["相对Y"]).text()

        default_dev_config = {
            "设备名称": name, 
            "设备号": id, 
            "区域1": area1, 
            "区域2": area2, 
            "区域3": area3,
            "相对X": x,
            "相对Y": y,
        }
        dialog = SingleAddDialog(self.area_list, dev_row, default_dev_config)
        dialog.signal_add.connect(self.add_single_device)
        dialog.exec()

    def dm_btn_delete_click(self, index):
        """设备配置表格删除按钮点击-槽函数"""
        _log.debug(f"设备配置表格删除按钮点击-槽函数：{index}")
        dev_id = self.device_model.item(index.row(), self.device_cols_index["设备号"]).text()
        self.delete_device([dev_id])
    
    def dm_delete_more_click(self):
        """设备配置表格删除更多按钮点击-槽函数"""
        rows = self.dm_filter_proxy.selectedRows()
        dev_id_list = []
        for row in rows:
            if self.device_model.item(row, self.device_cols_index["管理勾选"]).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked:
                dev_id_list.append(self.device_model.item(row, self.device_cols_index["设备号"]).text())
        self.delete_device(dev_id_list)
        
    def _clear_online_rate_cache(self):
        """清空在线率缓存"""
        if hasattr(self, '_online_rate_cache'):
            self._online_rate_cache.clear()
            _log.debug("在线率缓存已清空（设备列表变化）")

    def delete_device(self, device_id_list):
        """删除设备"""
        order = f"UPDATE device_info SET 账户 = '' WHERE 设备号 IN ({','.join(device_id_list)})"
        if device_id_list:
            try:
                with self.db_pool.connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(order)
                        conn.commit()
                        _log.debug(f"删除设备：{device_id_list} 成功")

                        rows_count = self.device_model.rowCount()
                        for row in range(rows_count-1, -1, -1):
                            device_id = self.device_model.item(row, self.device_cols_index["设备号"]).text()
                            if device_id in device_id_list:
                                try:
                                    self.device_model.removeRow(row)
                                    _log.debug(f"删除设备：{device_id} 成功")
                                except Exception as e:
                                    _log.error(f"删除设备：{device_id} 失败：{str(e)}")
                                else:
                                    self.client.unsubscribe(f"{device_id}")
                                    _log.debug(f"取消设备：{device_id} 的MQTT订阅")
                        self._clear_online_rate_cache()
                        self._clear_ec_cache()
                        self._clear_devices_cache()  # 清除设备缓存
            except Exception as e:
                _log.error(f"删除设备：{device_id_list} 失败：{str(e)}")
                traceback.print_exc()


    def apply_btn_history_click(self, index):
        """应用表格历史数据按钮点击-槽函数"""
        source_index = self.apply_filter_proxy.mapToSource(index)
        if not source_index.isValid():
            return

        row = source_index.row()
        self.history_ui.table_name = self.device_model.item(row, self.device_cols_index["设备号"]).text()
        self.history_ui.setWindowTitle(f"历史数据-{self.history_ui.table_name}")
        self.history_ui.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.history_ui.UI_table_data.setRowCount(0)
        self.history_ui.canvas.axes.clear()
        self.history_ui.exec()
    
    def mqtt_connect(self, connected, first_connect):
        """MQTT连接成功-槽函数"""
        if connected and first_connect:
            _log.debug("MQTT 首次连接成功，订阅所有主题")
            for row in range(self.device_model.rowCount()):
                dev_id = self.device_model.item(row, self.device_cols_index["设备号"]).text()
                if not self.client.subscribe(f"{dev_id}"):
                    _log.error(f"订阅主题：{dev_id} 失败")


    def all_nall_check(self):
        """全选列表或取消全选"""
        if self.UI_all_nall_btn.text() == "全选":
            self.UI_all_nall_btn.setText("取消全选")
            for row in range(self.device_model.rowCount()):
                item = self.device_model.item(row, self.device_cols_index["应用勾选"])
                if item:
                    item.setData(Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        else:
            self.UI_all_nall_btn.setText("全选")
            for row in range(self.device_model.rowCount()):
                item = self.device_model.item(row, self.device_cols_index["应用勾选"])
                if item:
                    item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)


    def send(self, type, widget):
        """发送指令"""
        _log.debug(f"发送指令--{type}")
        name = widget.text()
        order = self.send_order[type]
        req = "000000" + str(randint(0, 999999))
        order["ID"] = req[-6:]
        order["TM"] = get_time("UTC")
        if type == "dimming":
            order["DT"]["cnCtrl"][0]["bri"] = int(self.UI_dimming_in_2.text())
        elif type == "Dim":
            set_e = self.get_lineedit_text(self.UI_electricity_1, "int")
            max_e = self.get_lineedit_text(self.UI_electricity_2, "int")
            order["DT"]["Dim"][0]["rti"] = int(set_e / max_e * 1000)

        def send_order_thread(order, name):
            err_text = ""
            for row in range(self.device_model.rowCount()):
                if self.device_model.item(row, self.device_cols_index["应用勾选"]).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked:
                    dev = self.device_model.item(row, self.device_cols_index["设备号"]).text()
                    order["SN"] = dev
                    pub_topic = self.topic_config["pub"].replace("#", dev)
                    if not self.client.publish(pub_topic, str(order).replace("'", "\"")):
                        err_text += f"{dev} {name}指令发送失败\n"
            if err_text != "":
                self.signal_mess_show.emit("end", err_text)
            else:
                self.signal_mess_show.emit("end", f"指令发送{name}成功")

        thread = Thread(target=send_order_thread, args=(order, name))
        thread.start()
        self.signal_mess_show.emit("start", f"正在发送{name}指令...")


    def get_lineedit_text(self, widget, type_teturn):
        """获取输入框文本"""
        text = widget.text()
        if type_teturn == "int":
            if text == "":
                text = widget.placeholderText()
                if text == "":
                    return 0
                else:
                    text = int(text)
            else:
                text = int(text)
        elif type_teturn == "str":
            if text == "":
                text = widget.placeholderText()
        return text

    def dimming_input_change(self, widget):
        if type(widget).__name__ == "QSlider":
            value = widget.value()
            self.UI_dimming_in_2.setText(str(value))
        else:
            try:
                value = int(widget.text())
                self.UI_dimming_in_1.setValue(value)
            except:
                self.UI_dimming_in_2.setText(str(50))
                self.UI_dimming_in_1.setValue(50)
    
    def display_interface_chart_update(self):
        """更新显示界面图表 - 初始化图表数据并启动更新线程（优化版）"""
        if hasattr(self, '_chart_thread_running') and self._chart_thread_running:
            _log.debug("图表更新线程已在运行，跳过重复初始化")
            return

        self._chart_last_day_time = datetime.now()
        self._chart_date_list = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        self._chart_online_list = [0] * 7
        self._chart_electricity_list = [0] * 7
        self._chart_new_day_flg = True
        self._chart_realtime_online = 0
        self._chart_realtime_offline = 0

        self._chart_thread_running = True
        self._chart_thread_stop_flag = False

        # self._init_all_charts()

        self._chart_thread = Thread(target=self.thread_update_chart, daemon=True)
        self._chart_thread.start()
        _log.debug("图表更新线程已启动")

    def _init_all_charts(self):
        """初始化所有图表（带区域筛选）"""
        _log.debug("初始化所有图表控件（带区域筛选）")

        if self.online_pie_canvas is None:
            self._init_realtime_pie_chart()

        if self.online_7_linecanvas is None:
            self._init_7d_online_chart()

        if self.electricity_7_linecanvas is None:
            self._init_7d_electricity_chart()

        if self.power_24h_linecanvas is None:
            self._init_24h_power_chart()

    def _init_realtime_pie_chart(self):
        """初始化实时在线率饼图（带区域筛选）"""
        try:
            # 检查UI元素是否存在（HTML版本不需要这些）
            if not hasattr(self, 'UI_real_time_online_rate_groupBox'):
                _log.debug("UI_real_time_online_rate_groupBox不存在，跳过PyQt图表初始化")
                return

            old_layout = self.UI_real_time_online_rate_groupBox.layout()
            if old_layout:
                while old_layout.count():
                    item = old_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            main_layout = QVBoxLayout(self.UI_real_time_online_rate_groupBox)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)

            self.realtime_pie_area_filter = ChartAreaFilter('realtime_pie')
            self.realtime_pie_area_filter.set_area_list(self.area_list)
            self.realtime_pie_area_filter.area_confirmed.connect(self._on_chart_area_confirmed)
            main_layout.addWidget(self.realtime_pie_area_filter)

            self.online_pie_canvas = PieCanvas()
            main_layout.addWidget(self.online_pie_canvas)

            _log.debug("实时在线率饼图初始化完成（带区域筛选）")
        except Exception as e:
            _log.error(f"初始化实时在线率饼图失败: {e}")

    def _init_7d_online_chart(self):
        """初始化7天在线率折线图（带区域筛选）"""
        try:
            # 检查UI元素是否存在（HTML版本不需要这些）
            if not hasattr(self, 'UI_7_online_rate_groupBox'):
                _log.debug("UI_7_online_rate_groupBox不存在，跳过PyQt图表初始化")
                return

            old_layout = self.UI_7_online_rate_groupBox.layout()
            if old_layout:
                while old_layout.count():
                    item = old_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            main_layout = QVBoxLayout(self.UI_7_online_rate_groupBox)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)

            self.online_7d_area_filter = ChartAreaFilter('online_7d')
            self.online_7d_area_filter.set_area_list(self.area_list)
            self.online_7d_area_filter.area_confirmed.connect(self._on_chart_area_confirmed)
            main_layout.addWidget(self.online_7d_area_filter)

            self.online_7_linecanvas = BrokenLineCanvas(self._chart_date_list, self._chart_online_list)
            main_layout.addWidget(self.online_7_linecanvas)

            _log.debug("7天在线率图表初始化完成（带区域筛选）")
        except Exception as e:
            _log.error(f"初始化7天在线率图表失败: {e}")

    def _init_7d_electricity_chart(self):
        """初始化7天用电量折线图（带区域筛选）"""
        try:
            # 检查UI元素是否存在（HTML版本不需要这些）
            if not hasattr(self, 'UI_7_electricity_groupBox'):
                _log.debug("UI_7_electricity_groupBox不存在，跳过PyQt图表初始化")
                return

            old_layout = self.UI_7_electricity_groupBox.layout()
            if old_layout:
                while old_layout.count():
                    item = old_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            main_layout = QVBoxLayout(self.UI_7_electricity_groupBox)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)

            self.electricity_7d_area_filter = ChartAreaFilter('electricity_7d')
            self.electricity_7d_area_filter.set_area_list(self.area_list)
            self.electricity_7d_area_filter.area_confirmed.connect(self._on_chart_area_confirmed)
            main_layout.addWidget(self.electricity_7d_area_filter)

            self.electricity_7_linecanvas = BrokenLineCanvas(self._chart_date_list, self._chart_electricity_list)
            main_layout.addWidget(self.electricity_7_linecanvas)

            _log.debug("7天用电量图表初始化完成（带区域筛选）")
        except Exception as e:
            _log.error(f"初始化7天用电量图表失败: {e}")

    def _init_24h_power_chart(self):
        """初始化24分钟功率折线图（验证模式：带区域筛选）"""
        try:
            # 检查UI元素是否存在（HTML版本不需要这些）
            if not hasattr(self, 'UI_24_power_groupBox'):
                _log.debug("UI_24_power_groupBox不存在，跳过PyQt图表初始化")
                return

            old_layout = self.UI_24_power_groupBox.layout()
            if old_layout:
                while old_layout.count():
                    item = old_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            main_layout = QVBoxLayout(self.UI_24_power_groupBox)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)

            self.power_24h_area_filter = ChartAreaFilter('power_24h')
            self.power_24h_area_filter.set_area_list(self.area_list)
            self.power_24h_area_filter.area_confirmed.connect(self._on_chart_area_confirmed)
            main_layout.addWidget(self.power_24h_area_filter)

            now = datetime.now()
            initial_labels = []
            for i in range(23, 0, -1):
                point_time = now - timedelta(minutes=i)
                initial_labels.append(point_time.strftime("%H:%M"))
            initial_values = [0] * 23

            self.power_24h_linecanvas = Power24hCanvas(initial_labels, initial_values)
            main_layout.addWidget(self.power_24h_linecanvas)

            _log.debug("24分钟功率图表初始化完成（带区域筛选）")
        except Exception as e:
            _log.error(f"初始化24分钟功率图表失败: {e}")

    def _on_chart_area_confirmed(self, chart_name, selected_area):
        """图表区域选择确认处理"""
        _log.info(f"图表[{chart_name}]确认区域: {selected_area}")

        if not hasattr(self, '_current_chart_areas'):
            self._current_chart_areas = {}
        self._current_chart_areas[chart_name] = selected_area

        try:
            if chart_name == 'power_24h':
                self._update_24h_power_chart_by_area(selected_area)
            elif chart_name == 'realtime_pie':
                _log.info(f"开始更新实时在线率饼图，区域: {selected_area}")
                self._update_realtime_pie_by_area(selected_area)
                _log.info(f"实时在线率饼图更新完成")
            elif chart_name == 'online_7d':
                self._update_7d_online_chart_by_area(selected_area)
            elif chart_name == 'electricity_7d':
                self._update_7d_electricity_chart_by_area(selected_area)
        except Exception as e:
            _log.error(f"图表[{chart_name}]更新失败: {e}")
            import traceback
            traceback.print_exc()

    def _on_html_chart_filter_changed(self, chart_index, area_value):
        """HTML展示界面图表区域筛选改变处理
        
        Args:
            chart_index: 图表索引 (0=实时在线率, 1=7天在线率, 2=7天用电量, 3=24小时功率)
            area_value: 选择的区域值，格式为 "区域1/区域2/区域3" 或 "ALL"
        """
        _log.info(f"HTML图表筛选改变: chart_index={chart_index}, area_value={area_value}")
        
        # 映射图表索引到图表名称
        chart_names = ['realtime_pie', 'online_7d', 'electricity_7d', 'power_24h']
        if chart_index < 0 or chart_index >= len(chart_names):
            _log.error(f"无效的图表索引: {chart_index}")
            return
        
        chart_name = chart_names[chart_index]
        
        # 统一处理区域值格式
        selected_area = area_value if area_value else 'ALL'
        
        # 调用统一的图表区域选择处理
        self._on_chart_area_confirmed(chart_name, selected_area)

    def _update_24h_power_chart_by_area(self, area_path):
        """根据区域更新24小时功率图表（优先Redis，失败则查MySQL）"""
        try:
            devices_info = self._get_devices_for_current_user(area_path)
            _log.info(f"24小时功率图表 - 区域: {area_path}, 设备数量: {len(devices_info)}")
            if devices_info:
                _log.info(f"  设备列表: {[d[0] for d in devices_info[:5]]}{'...' if len(devices_info) > 5 else ''}")
            time_labels, power_sums = self._query_24h_power_data(devices_info, area_path)

            if self.power_24h_linecanvas:
                self.power_24h_linecanvas.update_data(time_labels, power_sums)

            # 更新HTML展示界面的图表
            if hasattr(self, 'area_display_widget') and self.area_display_widget:
                chart_data = {
                    'chart4': {'times': time_labels, 'values': power_sums}
                }
                self.area_display_widget.update_chart_data(chart_data)
                _log.info(f"HTML24小时功率图表已更新，数据点: {len(power_sums)}")

            _log.debug(f"24小时功率图表已更新，区域: {area_path}")
        except Exception as e:
            _log.error(f"更新24小时功率图表失败: {e}")

    def _update_realtime_pie_by_area(self, area_path):
        """根据区域更新实时在线率饼图"""
        try:
            # 优先使用内存数据模型获取实时在线率，与后台线程保持一致
            online_count, offline_count = self._get_realtime_online_from_model(area_path)
            _log.info(f"实时在线率饼图 - 区域: {area_path}, 在线: {online_count}, 离线: {offline_count}")

            if self.online_pie_canvas:
                total = online_count + offline_count
                if total > 0:
                    online_rate = (online_count / total) * 100
                    offline_rate = (offline_count / total) * 100
                    self.online_pie_canvas.update_data(online_rate, offline_rate)

            # 更新HTML展示界面的图表
            if hasattr(self, 'area_display_widget') and self.area_display_widget:
                chart_data = {
                    'chart1': {'online': online_count, 'offline': offline_count}
                }
                self.area_display_widget.update_chart_data(chart_data)
                _log.info(f"HTML实时在线率饼图已更新，在线: {online_count}, 离线: {offline_count}")

            _log.debug(f"实时在线率饼图已更新，区域: {area_path}, 在线: {online_count}, 离线: {offline_count}")
        except Exception as e:
            _log.error(f"更新实时在线率饼图失败: {e}")

    def _update_7d_online_chart_by_area(self, area_path):
        """根据区域更新7天在线率图表（优先预聚合表，失败则使用逐设备查询）"""
        try:
            _log.info(f"7天在线率图表 - 区域: {area_path}")
            date_list = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
            online_list = [0] * 7

            # 尝试从预聚合表查询（支持1000-2000台设备场景）
            account = getattr(self, 'current_username', '')
            if account and self._query_7d_online_from_aggregation(account, area_path, date_list, online_list):
                _log.info(f"7天在线率图表从预聚合表获取成功")
            else:
                # 预聚合表查询失败，使用逐设备查询（兼容旧逻辑）
                _log.info(f"7天在线率图表从预聚合表获取失败，使用逐设备查询")
                devices_info = self._get_devices_for_current_user(area_path)
                _log.info(f"  设备数量: {len(devices_info)}")
                
                if devices_info:
                    for i, date_day in enumerate(date_list):
                        online_count = 0
                        total_count = 0
                        
                        _log.info(f"  日期 {date_day}: 开始查询 {len(devices_info)} 个设备")

                        for dev_id, add_datetime in devices_info:
                            day_end = datetime.strptime(date_day + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                            if add_datetime <= day_end:
                                total_count += 1
                                # 优先使用Redis缓存，失败则查MySQL
                                is_online, _ = self._query_device_history_data(
                                    dev_id, date_day, area_path, is_today=(i == 6)
                                )
                                if is_online:
                                    online_count += 1
                                _log.info(f"    设备 {dev_id}: add_datetime={add_datetime}, is_online={is_online}, day_end={day_end}, include={add_datetime <= day_end}")

                        online_list[i] = (online_count / total_count * 100) if total_count > 0 else 0
                        _log.info(f"  日期 {date_day}: 在线 {online_count}/{total_count} = {online_list[i]}%")

            if self.online_7_linecanvas:
                self.online_7_linecanvas.update_data(date_list, online_list)

            # 更新HTML展示界面的图表
            if hasattr(self, 'area_display_widget') and self.area_display_widget:
                chart_data = {
                    'chart2': {'dates': date_list, 'values': online_list}
                }
                self.area_display_widget.update_chart_data(chart_data)
                _log.info(f"HTML7天在线率图表已更新，数据点: {len(online_list)}")

            _log.debug(f"7天在线率图表已更新，区域: {area_path}")
        except Exception as e:
            _log.error(f"更新7天在线率图表失败: {e}")

    def _query_7d_online_from_aggregation(self, account, area_path, date_list, online_list):
        """从预聚合表查询7天在线率数据
        
        Returns:
            bool: 是否成功获取数据
        """
        try:
            if not self.db_pool:
                return False

            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 判断使用哪个表
                    if area_path == "ALL":
                        table_name = "summary_daily_online"
                        sql = """
                            SELECT `日期`, `在线率` 
                            FROM `{}` 
                            WHERE `账户` = %s AND `日期` IN ({}) 
                            ORDER BY `日期` ASC
                        """.format(table_name, ','.join(['%s'] * len(date_list)))
                        params = [account] + date_list
                    else:
                        table_name = "summary_daily_online_by_area"
                        sql = """
                            SELECT `日期`, `在线率` 
                            FROM `{}` 
                            WHERE `账户` = %s AND `区域路径` = %s AND `日期` IN ({}) 
                            ORDER BY `日期` ASC
                        """.format(table_name, ','.join(['%s'] * len(date_list)))
                        params = [account, area_path] + date_list

                    cursor.execute(sql, params)
                    rows = cursor.fetchall()

                    if not rows:
                        return False

                    # 将查询结果转换为字典
                    rate_map = {row['日期'].strftime("%Y-%m-%d"): float(row['在线率']) for row in rows}

                    # 填充在线率列表
                    missing_dates = []  # 记录缺失数据的日期
                    for i, date_str in enumerate(date_list):
                        if date_str in rate_map:
                            online_list[i] = rate_map[date_str]
                        else:
                            # 如果某天没有数据，标记为需要补充
                            online_list[i] = -1  # 标记为需要补充
                            missing_dates.append(date_str)

                    # 如果有缺失数据，返回False让调用方使用逐设备查询补充
                    if missing_dates:
                        _log.info(f"预聚合表缺少 {len(missing_dates)} 天的数据: {missing_dates}")
                        return False

                    return True

        except Exception as e:
            _log.error(f"从预聚合表查询7天在线率失败: {e}")
            return False

    def _update_7d_electricity_chart_by_area(self, area_path):
        """根据区域更新7天用电量图表（优先预聚合表，失败则使用逐设备查询）"""
        try:
            _log.info(f"7天用电量图表 - 区域: {area_path}")
            date_list = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
            electricity_list = [0] * 7

            # 尝试从预聚合表查询（支持1000-2000台设备场景）
            account = getattr(self, 'current_username', '')
            if account and self._query_7d_electricity_from_aggregation(account, area_path, date_list, electricity_list):
                _log.info(f"7天用电量图表从预聚合表获取成功")
            else:
                # 预聚合表查询失败，使用逐设备查询（兼容旧逻辑）
                _log.info(f"7天用电量图表从预聚合表获取失败，使用逐设备查询")
                devices_info = self._get_devices_for_current_user(area_path)
                _log.info(f"  设备数量: {len(devices_info)}")

                if devices_info:
                    for i, date_day in enumerate(date_list):
                        daily_electricity = 0

                        for dev_id, add_datetime in devices_info:
                            day_end = datetime.strptime(date_day + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                            if add_datetime <= day_end:
                                # 优先使用Redis缓存，失败则查MySQL
                                _, electricity = self._query_device_history_data(
                                    dev_id, date_day, area_path, is_today=(i == 6)
                                )
                                daily_electricity += electricity

                        electricity_list[i] = daily_electricity

            if self.electricity_7_linecanvas:
                self.electricity_7_linecanvas.update_data(date_list, electricity_list)

            # 更新HTML展示界面的图表
            if hasattr(self, 'area_display_widget') and self.area_display_widget:
                chart_data = {
                    'chart3': {'dates': date_list, 'values': electricity_list}
                }
                self.area_display_widget.update_chart_data(chart_data)
                _log.info(f"HTML7天用电量图表已更新，数据点: {len(electricity_list)}")

            _log.debug(f"7天用电量图表已更新，区域: {area_path}")
        except Exception as e:
            _log.error(f"更新7天用电量图表失败: {e}")

    def _query_7d_electricity_from_aggregation(self, account, area_path, date_list, electricity_list):
        """从预聚合表查询7天能耗数据

        Returns:
            bool: 是否成功获取数据
        """
        try:
            if not self.db_pool:
                return False

            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 判断使用哪个表
                    if area_path == "ALL":
                        table_name = "summary_daily_electricity"
                        sql = """
                            SELECT `日期`, `总用电量`
                            FROM `{}`
                            WHERE `账户` = %s AND `日期` IN ({})
                            ORDER BY `日期` ASC
                        """.format(table_name, ','.join(['%s'] * len(date_list)))
                        params = [account] + date_list
                    else:
                        table_name = "summary_daily_electricity_by_area"
                        sql = """
                            SELECT `日期`, `总用电量`
                            FROM `{}`
                            WHERE `账户` = %s AND `区域路径` = %s AND `日期` IN ({})
                            ORDER BY `日期` ASC
                        """.format(table_name, ','.join(['%s'] * len(date_list)))
                        params = [account, area_path] + date_list

                    cursor.execute(sql, params)
                    rows = cursor.fetchall()

                    if not rows:
                        return False

                    # 将查询结果转换为字典
                    elec_map = {row['日期'].strftime("%Y-%m-%d"): int(row['总用电量']) for row in rows}

                    # 填充能耗列表
                    missing_dates = []  # 记录缺失数据的日期
                    for i, date_str in enumerate(date_list):
                        if date_str in elec_map:
                            electricity_list[i] = elec_map[date_str]
                        else:
                            # 如果某天没有数据，标记为需要补充
                            electricity_list[i] = -1
                            missing_dates.append(date_str)

                    # 如果有缺失数据，返回False让调用方使用逐设备查询补充
                    if missing_dates:
                        _log.info(f"预聚合表缺少 {len(missing_dates)} 天的能耗数据: {missing_dates}")
                        return False

                    return True

        except Exception as e:
            _log.error(f"从预聚合表查询7天能耗失败: {e}")
            return False

    def _get_devices_for_current_user(self, area_path="ALL"):
        """获取当前用户指定区域的设备（优化版：支持区域筛选和缓存）
        
        Args:
            area_path: 区域路径，格式为 "区域1/区域2/区域3" 或 "ALL" 表示全部区域
            
        Returns:
            list: [(dev_id, add_datetime), ...]
        """
        if not hasattr(self, 'current_username') or not self.current_username:
            _log.warning("当前用户名为空，无法获取设备列表")
            return []

        # 尝试从缓存获取（仅当区域为ALL时缓存）
        cache_key = f"devices:{self.current_username}:{area_path}"
        if area_path == "ALL" and hasattr(self, '_devices_cache'):
            cached = self._devices_cache.get(cache_key)
            if cached:
                return cached

        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    if area_path == "ALL":
                        cursor.execute(
                            "SELECT `设备号`, `日期` FROM `device_info` WHERE `账户` = %s",
                            (self.current_username,)
                        )
                    else:
                        parts = area_path.split('/')
                        area1 = parts[0] if len(parts) > 0 else ''
                        area2 = parts[1] if len(parts) > 1 else ''
                        area3 = parts[2] if len(parts) > 2 else ''
                        
                        _log.info(f"区域筛选参数: area1='{area1}', area2='{area2}', area3='{area3}'")

                        # 优化：使用更灵活的查询，允许空值匹配
                        if area3:
                            # 三级区域筛选
                            _log.info(f"执行三级区域筛选SQL: 账户='{self.current_username}', 区域1='{area1}', 区域2='{area2}', 区域3='{area3}'")
                            cursor.execute(
                                "SELECT `设备号`, `日期` FROM `device_info` WHERE `账户` = %s AND `区域1` = %s AND `区域2` = %s AND `区域3` = %s",
                                (self.current_username, area1, area2, area3)
                            )
                        elif area2:
                            # 二级区域筛选（包含该二级区域下的所有三级区域）
                            _log.info(f"执行二级区域筛选SQL: 账户='{self.current_username}', 区域1='{area1}', 区域2='{area2}'")
                            cursor.execute(
                                "SELECT `设备号`, `日期` FROM `device_info` WHERE `账户` = %s AND `区域1` = %s AND `区域2` = %s",
                                (self.current_username, area1, area2)
                            )
                        else:
                            # 一级区域筛选（包含该一级区域下的所有二级和三级区域）
                            _log.info(f"执行一级区域筛选SQL: 账户='{self.current_username}', 区域1='{area1}'")
                            cursor.execute(
                                "SELECT `设备号`, `日期` FROM `device_info` WHERE `账户` = %s AND `区域1` = %s",
                                (self.current_username, area1)
                            )

                    rows = cursor.fetchall()
                    devices = []
                    for row in rows:
                        dev_id = row['设备号']
                        add_date = row['日期']
                        if isinstance(add_date, str):
                            add_datetime = datetime.strptime(add_date, "%Y-%m-%d %H:%M:%S")
                        else:
                            add_datetime = add_date
                        devices.append((dev_id, add_datetime))
                    
                    # 缓存结果（仅ALL区域）
                    if area_path == "ALL":
                        if not hasattr(self, '_devices_cache'):
                            self._devices_cache = {}
                        self._devices_cache[cache_key] = devices
                    
                    return devices
        except Exception as e:
            _log.error(f"获取用户设备失败: {e}")
            return []

    def _clear_devices_cache(self):
        """清除设备列表缓存（在设备增删改时调用）"""
        if hasattr(self, '_devices_cache'):
            self._devices_cache.clear()
            _log.debug("设备列表缓存已清除")

    def thread_update_chart(self):
        """更新图表线程（优化版）"""
        _log.info("图表更新线程启动")
        update_interval = app_config.chart_update_interval/1000
        last_update_time = time.time() - update_interval

        import queue
        devices_info_queue = queue.Queue(maxsize=1)

        while not getattr(self, '_chart_thread_stop_flag', False):
            current_time = time.time()
            elapsed = current_time - last_update_time
            # _log.error(f"{app_config.chart_update_interval},{elapsed},{update_interval}")
            if elapsed < update_interval:
                sleep(0.5)
                continue

            last_update_time = current_time
            _log.info("图表更新开始")

            try:
                while not devices_info_queue.empty():
                    try:
                        devices_info_queue.get_nowait()
                    except queue.Empty:
                        break

                self._devices_info_queue = devices_info_queue
                _log.debug("请求主线程获取设备信息...")
                self.signal_request_devices_info.emit()

                try:
                    devices_info = devices_info_queue.get(timeout=5)
                    _log.debug(f"获取到 {len(devices_info)} 个设备信息")
                except queue.Empty:
                    _log.warning("获取设备信息超时（5秒），跳过本次更新")
                    continue

                if not devices_info:
                    _log.debug("设备列表为空，跳过图表更新")
                    continue

            except RuntimeError:
                _log.debug("设备模型已被删除，图表更新线程退出")
                self._chart_thread_running = False
                return
            except Exception as e:
                _log.error(f"获取设备信息失败: {e}")
                continue
            finally:
                self._devices_info_queue = None

            try:
                if datetime.now() - self._chart_last_day_time > timedelta(days=1):
                    self._chart_last_day_time = datetime.now()
                    for i in range(6, -1, -1):
                        self._chart_date_list[6-i] = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    self._chart_new_day_flg = True
                    _log.debug(f"新一天，更新日期列表：{self._chart_date_list}")
            except Exception as e:
                _log.error(f"检查日期失败: {e}")

            try:
                (date_list, online_list, electricity_list, realtime_online, realtime_offline,
                 total_power, power_24h_data, online_7d_area, electricity_7d_area) = self._query_chart_data_in_thread(devices_info)
                
                if power_24h_data and len(power_24h_data) == 2:
                    power_24h_labels, power_24h_values = power_24h_data
                else:
                    _log.warning(f"功率数据为空或格式错误: {power_24h_data}")
                    power_24h_labels = []
                    power_24h_values = []

                self.signal_chart_data_ready.emit(date_list, online_list, electricity_list, realtime_online,
                                                  realtime_offline, total_power, power_24h_labels, power_24h_values,
                                                  online_7d_area, electricity_7d_area)

            except RuntimeError as e:
                _log.error(f"图表对象已被删除，退出线程：{e}")
                self._chart_thread_running = False
                return
            except Exception as e:
                _log.error(f"图表更新失败：{e}")
                import traceback
                traceback.print_exc()

        self._chart_thread_running = False
        _log.debug("图表更新线程已停止")

    def stop_chart_update_thread(self):
        """停止图表更新线程"""
        if hasattr(self, '_chart_thread_running') and self._chart_thread_running:
            _log.debug("正在停止图表更新线程...")
            self._chart_thread_stop_flag = True
            if hasattr(self, '_chart_thread') and self._chart_thread.is_alive():
                self._chart_thread.join(timeout=2)
            _log.debug("图表更新线程已停止")

    def _on_request_devices_info(self):
        """主线程槽函数：响应后台线程请求，获取设备信息"""
        _log.debug("主线程：收到获取设备信息请求")
        try:
            devices_info = self._get_devices_info()
            _log.debug(f"主线程：获取到 {len(devices_info)} 个设备")
            if hasattr(self, '_devices_info_queue') and self._devices_info_queue is not None:
                try:
                    self._devices_info_queue.put_nowait(devices_info)
                    _log.debug("主线程：设备信息已写入队列")
                except Exception as e:
                    _log.error(f"向队列写入设备信息失败: {e}")
            else:
                _log.warning("主线程：队列引用不存在，无法写入设备信息")
        except Exception as e:
            _log.error(f"获取设备信息失败: {e}")
            if hasattr(self, '_devices_info_queue') and self._devices_info_queue is not None:
                try:
                    self._devices_info_queue.put_nowait([])
                except:
                    pass

    def _get_devices_info(self):
        """获取设备信息列表（在主线程中调用）"""
        devices_info = []
        row_count = self.device_model.rowCount()
        for row in range(row_count):
            try:
                dev_id = self.device_model.item(row, self.device_cols_index["设备号"]).text().strip()
                add_time = self.device_model.item(row, self.device_cols_index["添加日期"]).text().strip()
                add_datetime = datetime.strptime(add_time, "%Y-%m-%d %H:%M:%S")
                devices_info.append((dev_id, add_datetime))
            except (RuntimeError, AttributeError, ValueError):
                continue
        return devices_info

    def _init_chart_cache(self):
        """初始化图表数据缓存"""
        if not hasattr(self, '_chart_data_cache'):
            self._chart_data_cache = {}
            self._chart_cache_date = None

        today = datetime.now().strftime("%Y-%m-%d")
        if self._chart_cache_date != today:
            self._chart_data_cache.clear()
            self._chart_cache_date = today
            _log.debug(f"图表数据缓存已清空，新的一天: {today}")

    def update_history_charts(self, devices_info=None):
        """
        更新前6天历史数据（仅在启动或跨天时调用）
        """
        if devices_info is None:
            devices_info = self._get_devices_info()
        if not devices_info:
            return

        self._init_chart_cache()

        _log.debug("更新前6天图表数据开始！")
        for i in range(6, 0, -1):
            date_day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            day_end = datetime.strptime(date_day + " 23:59:59", "%Y-%m-%d %H:%M:%S")

            all_dev_count = 0
            online_count = 0
            electricity_sum = 0
            need_query_devices = []

            for dev_id, add_datetime in devices_info:
                if add_datetime <= day_end:
                    all_dev_count += 1
                    cache_key = (dev_id, date_day)
                    if cache_key in self._chart_data_cache:
                        is_online_day, electricity, _ = self._chart_data_cache[cache_key]
                        if is_online_day:
                            online_count += 1
                        electricity_sum += electricity
                    else:
                        need_query_devices.append(dev_id)

            for dev_id in need_query_devices:
                is_online_day, electricity, _, _, _ = get_parsed_all_data(
                    self.db_pool, dev_id, date_day, self.outline_time, is_today=False
                )
                cache_key = (dev_id, date_day)
                self._chart_data_cache[cache_key] = (is_online_day, electricity, False)
                if is_online_day:
                    online_count += 1
                electricity_sum += electricity

            online_rate = online_count / all_dev_count if all_dev_count > 0 else 0
            self._chart_online_list[6 - i] = online_rate * 100
            self._chart_electricity_list[6 - i] = electricity_sum

            _log.info(f"前{i}天：设备{all_dev_count}，在线{online_count}，能耗{electricity_sum}，缓存命中{all_dev_count - len(need_query_devices)}")

        _log.debug("更新前6天图表数据完成！")

    def update_today_and_realtime(self, devices_info=None):
        """
        更新今天（第7天）数据和实时在线率（每10秒调用一次）
        """
        if devices_info is None:
            devices_info = self._get_devices_info()
        if not devices_info:
            return 0, 0

        date_day = datetime.now().strftime("%Y-%m-%d")
        online_count = 0
        electricity_sum = 0
        realtime_online_count = 0
        realtime_offline_count = 0
        total_power = 0
        valid_power_count = 0
        time_threshold = datetime.now() - timedelta(minutes=60)

        for dev_id, _ in devices_info:
            is_online_day, electricity, is_realtime_online, power, power_time = get_parsed_all_data(
                self.db_pool, dev_id, date_day, self.outline_time, is_today=True
            )

            if is_online_day:
                online_count += 1
            electricity_sum += electricity

            if is_realtime_online:
                realtime_online_count += 1
            else:
                realtime_offline_count += 1

            if power_time and power_time >= time_threshold:
                total_power += power
                valid_power_count += 1

        online_rate = online_count / len(devices_info) if devices_info else 0
        self._chart_online_list[6] = online_rate * 100
        self._chart_electricity_list[6] = electricity_sum

        self._chart_total_power = total_power
        self._chart_valid_power_count = valid_power_count

        _log.debug(f"今天数据更新：在线率{self._chart_online_list[6]:.2f}%，能耗{self._chart_electricity_list[6]}")
        _log.debug(f"实时在线统计：在线{realtime_online_count}，离线{realtime_offline_count}")
        _log.debug(f"60分钟内有效功率之和：{total_power}，有效设备数：{valid_power_count}")

        return realtime_online_count, realtime_offline_count

    def _query_chart_data_in_thread(self, devices_info):
        """在后台线程中并行查询图表数据（优化版：实时在线用数据模型，历史数据优先Redis）"""
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor, as_completed

        start_time = time.time()

        chart_areas = getattr(self, '_current_chart_areas', {})
        realtime_pie_area = chart_areas.get('realtime_pie', 'ALL')
        online_7d_area = chart_areas.get('online_7d', 'ALL')
        electricity_7d_area = chart_areas.get('electricity_7d', 'ALL')
        power_24h_area = chart_areas.get('power_24h', 'ALL')
        _log.info(f"后台线程图表区域: realtime_pie={realtime_pie_area}, online_7d={online_7d_area}, electricity_7d={electricity_7d_area}, power_24h={power_24h_area}")

        date_list = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

        online_list = getattr(self, '_chart_online_list', [0] * 7).copy() if hasattr(self, '_chart_online_list') else [0] * 7
        electricity_list = getattr(self, '_chart_electricity_list', [0] * 7).copy() if hasattr(self, '_chart_electricity_list') else [0] * 7

        all_devices = devices_info
        online_7d_devices = self._get_devices_for_current_user(online_7d_area) if online_7d_area != 'ALL' else all_devices
        electricity_7d_devices = self._get_devices_for_current_user(electricity_7d_area) if electricity_7d_area != 'ALL' else all_devices

        if self._chart_new_day_flg:
            _log.debug(f"更新前6天数据（启动或跨天），区域: {online_7d_area}")
            self._init_chart_cache()

            def query_history_day(day_offset):
                date_day = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                day_end = datetime.strptime(date_day + " 23:59:59", "%Y-%m-%d %H:%M:%S")

                all_dev_count = 0
                online_count = 0
                electricity_sum = 0

                for dev_id, add_datetime in online_7d_devices:
                    if add_datetime <= day_end:
                        all_dev_count += 1
                        # 使用优化后的查询方法（优先Redis）
                        is_online_day, electricity = self._query_device_history_data(
                            dev_id, date_day, online_7d_area, is_today=False
                        )
                        if is_online_day:
                            online_count += 1
                        electricity_sum += electricity

                online_rate = online_count / all_dev_count if all_dev_count > 0 else 0
                return {
                    'index': 6 - day_offset,
                    'online_rate': online_rate * 100,
                    'electricity': electricity_sum
                }

            with ThreadPoolExecutor(max_workers=6) as executor:
                future_to_day = {executor.submit(query_history_day, i): i for i in range(6, 0, -1)}

                for future in as_completed(future_to_day):
                    day = future_to_day[future]
                    try:
                        result = future.result(timeout=120)
                        online_list[result['index']] = result['online_rate']
                        electricity_list[result['index']] = result['electricity']
                    except TimeoutError:
                        _log.error(f"第 {day} 天历史数据查询超时")
                    except Exception as e:
                        _log.error(f"第 {day} 天历史数据查询失败: {e}")

            self._chart_new_day_flg = False
            _log.debug("更新前6天图表数据完成！")

        date_day = datetime.now().strftime("%Y-%m-%d")

        def query_today_online():
            """查询今天在线率（使用优化后的方法，优先Redis）"""
            online_count = 0
            for dev_id, _ in online_7d_devices:
                try:
                    # 使用优化后的查询方法（今天数据不走Redis缓存，直接查MySQL）
                    is_online_day, _ = self._query_device_history_data(
                        dev_id, date_day, online_7d_area, is_today=True
                    )
                    if is_online_day:
                        online_count += 1
                except Exception as e:
                    _log.error(f"查询设备 {dev_id} 在线状态失败: {e}")
            return online_count

        def query_today_electricity():
            """查询今天用电量（使用优化后的方法，优先Redis）"""
            electricity_sum = 0
            for dev_id, _ in electricity_7d_devices:
                try:
                    # 使用优化后的查询方法（今天数据不走Redis缓存，直接查MySQL）
                    _, electricity = self._query_device_history_data(
                        dev_id, date_day, electricity_7d_area, is_today=True
                    )
                    electricity_sum += electricity
                except Exception as e:
                    _log.error(f"查询设备 {dev_id} 用电量失败: {e}")
            return electricity_sum

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_online = executor.submit(query_today_online)
            future_electricity = executor.submit(query_today_electricity)
            future_power = executor.submit(self._query_24h_power_data, devices_info, power_24h_area)

            realtime_online_count, realtime_offline_count = self._get_realtime_online_from_model(realtime_pie_area)

            try:
                online_count_7d = future_online.result(timeout=120)
                online_rate_7d = online_count_7d / len(online_7d_devices) if online_7d_devices else 0
                online_list[6] = online_rate_7d * 100
            except TimeoutError:
                _log.error("今天在线率查询超时")
                online_list[6] = 0
            except Exception as e:
                _log.error(f"今天在线率查询失败: {e}")
                online_list[6] = 0

            try:
                electricity_sum_7d = future_electricity.result(timeout=120)
                electricity_list[6] = electricity_sum_7d
            except TimeoutError:
                _log.error("今天用电量查询超时")
                electricity_sum_7d = 0
            except Exception as e:
                _log.error(f"今天用电量查询失败: {e}")
                electricity_sum_7d = 0

            try:
                power_24h_data = future_power.result(timeout=60)
            except TimeoutError:
                _log.error("功率数据查询超时")
                power_24h_data = ([], [])
            except Exception as e:
                _log.error(f"功率数据查询失败: {e}")
                power_24h_data = ([], [])

        elapsed_time = time.time() - start_time
        _log.debug(f"并行查询完成，耗时: {elapsed_time:.2f}秒")
        _log.debug(f"今天数据查询完成：")
        _log.debug(f"  7天在线率图表(区域:{online_7d_area})：在线率{online_list[6]:.2f}%")
        _log.debug(f"  7天用电量图表(区域:{electricity_7d_area})：能耗{electricity_list[6]}")
        _log.debug(f"  实时在线率(区域:{realtime_pie_area})：在线{realtime_online_count}，离线{realtime_offline_count}")
        _log.debug(f"  24分钟功率(区域:{power_24h_area})")

        return (date_list, online_list, electricity_list, realtime_online_count, realtime_offline_count,
                electricity_sum_7d, power_24h_data, online_7d_area, electricity_7d_area)

    def _get_realtime_online_from_model(self, area_path="ALL"):
        """从数据模型获取实时在线率（优化版：支持区域筛选）
        
        Args:
            area_path: 区域路径，格式为 "区域1/区域2/区域3" 或 "ALL" 表示全部区域
        
        Returns:
            tuple: (online_count, offline_count)
        """
        online_count = 0
        offline_count = 0

        try:
            online_status_col = self.device_cols_index.get("在线状态", -1)
            device_id_col = self.device_cols_index.get("设备号", -1)
            area1_col = self.device_cols_index.get("区域1", -1)
            area2_col = self.device_cols_index.get("区域2", -1)
            area3_col = self.device_cols_index.get("区域3", -1)

            if online_status_col == -1:
                _log.warning("在线状态列不存在")
                return 0, 0

            # 解析区域路径
            target_area1 = None
            target_area2 = None
            target_area3 = None
            if area_path != "ALL":
                parts = area_path.split('/')
                target_area1 = parts[0] if len(parts) > 0 else None
                target_area2 = parts[1] if len(parts) > 1 else None
                target_area3 = parts[2] if len(parts) > 2 else None

            row_count = self.device_model.rowCount()
            _log.info(f"_get_realtime_online_from_model: 区域={area_path}, 行数={row_count}, target_area1={target_area1}, target_area2={target_area2}, target_area3={target_area3}")
            
            matched_count = 0
            for row in range(row_count):
                # 区域筛选
                if area_path != "ALL":
                    # 获取设备的区域值
                    area1_val = self.device_model.item(row, area1_col).text() if area1_col != -1 and self.device_model.item(row, area1_col) else ""
                    area2_val = self.device_model.item(row, area2_col).text() if area2_col != -1 and self.device_model.item(row, area2_col) else ""
                    area3_val = self.device_model.item(row, area3_col).text() if area3_col != -1 and self.device_model.item(row, area3_col) else ""
                    device_id = self.device_model.item(row, device_id_col).text() if device_id_col != -1 and self.device_model.item(row, device_id_col) else f"行{row}"
                    
                    if row < 5:  # 只打印前5行
                        _log.info(f"  设备{device_id}: 区域1='{area1_val}', 区域2='{area2_val}', 区域3='{area3_val}'")
                    
                    # 检查区域1
                    if target_area1 and area1_col != -1:
                        area1_item = self.device_model.item(row, area1_col)
                        if area1_item and area1_item.text() != target_area1:
                            continue
                    
                    # 检查区域2
                    if target_area2 and area2_col != -1:
                        area2_item = self.device_model.item(row, area2_col)
                        if area2_item and area2_item.text() != target_area2:
                            continue
                    
                    # 检查区域3
                    if target_area3 and area3_col != -1:
                        area3_item = self.device_model.item(row, area3_col)
                        if area3_item and area3_item.text() != target_area3:
                            continue
                    
                    matched_count += 1
                    _log.info(f"  设备{device_id} 匹配区域筛选")

                # 获取在线状态
                status_item = self.device_model.item(row, online_status_col)
                if status_item:
                    status_text = status_item.text()
                    if status_text == "在线":
                        online_count += 1
                    else:
                        offline_count += 1
                else:
                    offline_count += 1
            
            _log.info(f"_get_realtime_online_from_model: 匹配设备数={matched_count}, 在线={online_count}, 离线={offline_count}")

        except Exception as e:
            _log.error(f"从数据模型获取实时在线率失败: {e}")
            return 0, 0

        return online_count, offline_count

    def _query_24h_power_data(self, devices_info, area_path="ALL"):
        """查询24分钟功率数据（从_power表）- 验证模式"""
        now = datetime.now()
        time_points = []
        time_labels = []

        for i in range(24, 0, -1):
            point_time = now - timedelta(minutes=i)
            point_time = point_time.replace(second=0, microsecond=0)
            time_points.append(point_time)
            time_labels.append(point_time.strftime("%H:%M"))

        power_sums = [0] * 24

        if self.redis_client:
            try:
                cached_data = self._get_24h_power_from_redis(time_points, area_path)
                if cached_data:
                    _log.debug(f"24分钟功率数据从Redis缓存获取（24个点，区域: {area_path}）")
                    return time_labels, cached_data
            except Exception as e:
                _log.warning(f"从Redis获取缓存失败: {e}")

        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    account = getattr(self, 'current_username', '')

                    if area_path == "ALL":
                        cursor.execute(
                            """
                            SELECT `时间点`, `功率之和`, `在线设备数`, `设备总数`
                            FROM `summary_power`
                            WHERE `账户` = %s AND `时间点` BETWEEN %s AND %s
                            ORDER BY `时间点` ASC
                            """,
                            (account, time_points[0], time_points[-1])
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT `时间点`, `功率之和`, `在线设备数`, `设备数`
                            FROM `summary_power_by_area`
                            WHERE `账户` = %s AND `区域路径` = %s AND `时间点` BETWEEN %s AND %s
                            ORDER BY `时间点` ASC
                            """,
                            (account, area_path, time_points[0], time_points[-1])
                        )
                    rows = cursor.fetchall()

            power_map = {}
            for row in rows:
                time_key = row['时间点'].strftime("%H:%M")
                power_map[time_key] = {
                    'power': row['功率之和'] or 0,
                    'online': row['在线设备数'] or 0,
                    'total': row.get('设备总数', row.get('设备数', 0))
                }

            missing_recent_points = []
            for i in range(max(0, len(time_points) - 2), len(time_points)):
                point_time = time_points[i]
                time_key = point_time.strftime("%H:%M")
                if time_key not in power_map:
                    missing_recent_points.append((i, point_time))

            if missing_recent_points:
                _log.debug(f"预聚合表缺少 {len(missing_recent_points)} 个最新时间点数据，从原始表补充")
                try:
                    for idx, point_time in missing_recent_points:
                        realtime_data = self._query_power_at_timepoint(devices_info, point_time, area_path)
                        time_key = point_time.strftime("%H:%M")
                        power_map[time_key] = realtime_data
                except Exception as e:
                    _log.warning(f"从原始表补充实时数据失败: {e}")

            for i, point_time in enumerate(time_points):
                time_key = point_time.strftime("%H:%M")
                data = power_map.get(time_key, {'power': 0, 'online': 0, 'total': 0})
                power_sums[i] = data['power']

            _log.debug(f"24小时功率数据查询完成（预聚合表+实时补充，区域: {area_path}）：{len(rows)} 个预聚合点 + {len(missing_recent_points)} 个实时点")

            if self.redis_client:
                try:
                    self._cache_24h_power_to_redis(time_points, power_sums, area_path)
                except Exception as e:
                    _log.warning(f"缓存到Redis失败: {e}")

        except Exception as e:
            _log.error(f"查询24小时功率数据失败（预聚合表），fallback到原始查询: {e}")
            return self._query_24h_power_data_fallback(devices_info, time_points, time_labels)

        return time_labels, power_sums
    
    def _get_24h_power_from_redis(self, time_points, area_path="ALL"):
        """从Redis获取24小时功率缓存数据（支持NULL值）
        
        注意：功率数据使用统一的缓存键（不包含区域路径），
        因为功率数据与区域无关，只与账户和时间点有关。
        """
        if not self.redis_client:
            return None

        power_sums = []
        account = getattr(self, 'current_username', '')
        if not account:
            _log.warning("current_username为空，无法查询Redis缓存")
            return None
        # 使用统一的缓存键（不包含区域路径），避免同一功率数据在不同区域下重复缓存
        cache_key_prefix = f"power:{account}:ALL"
        _log.debug(f"Redis缓存查询前缀: {cache_key_prefix}")

        for point_time in time_points:
            time_str = point_time.strftime("%Y%m%d%H%M")
            cache_key = f"{cache_key_prefix}:{time_str}"

            cached = self.redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                total_power = data.get('total_power')
                has_data = data.get('has_data', total_power is not None)
                
                # 支持NULL值：None表示无数据，0表示功率为0
                if has_data and total_power is not None:
                    power_sums.append(total_power)
                elif has_data and total_power is None:
                    # 有数据但功率为NULL（无有效数据），使用0代替
                    power_sums.append(0)
                else:
                    # 无数据标记，使用0
                    power_sums.append(0)
            else:
                _log.debug(f"Redis缓存缺失: {cache_key}")
                return None

        return power_sums

    def _cache_24h_power_to_redis(self, time_points, power_sums, area_path="ALL"):
        """将24小时功率数据缓存到Redis（支持NULL值）
        
        注意：功率数据使用统一的缓存键（不包含区域路径），
        因为功率数据与区域无关，只与账户和时间点有关。
        """
        if not self.redis_client or len(time_points) != len(power_sums):
            return

        try:
            pipe = self.redis_client.pipeline()
            account = getattr(self, 'current_username', '')
            # 使用统一的缓存键（不包含区域路径）
            cache_key_prefix = f"power:{account}:ALL"

            for i, point_time in enumerate(time_points):
                time_str = point_time.strftime("%Y%m%d%H%M")
                cache_key = f"{cache_key_prefix}:{time_str}"

                # 支持NULL值：None表示无数据，0表示功率为0
                total_power = power_sums[i]
                value = {
                    'account': account,
                    'area_path': 'ALL',  # 统一使用ALL，不区分区域
                    'time_point': point_time.isoformat(),
                    'total_power': total_power if total_power is not None else None,
                    'has_data': total_power is not None,
                    'cached_at': datetime.now().isoformat()
                }
                pipe.setex(cache_key, 300, json.dumps(value))

            pipe.execute()
            _log.debug(f"24小时功率数据已缓存到Redis（账户隔离，统一缓存）: {len(time_points)} 个点")

        except Exception as e:
            _log.warning(f"缓存到Redis失败: {e}")
    
    def _query_power_at_timepoint(self, devices_info, point_time, area_path="ALL"):
        """查询单个时间点的实时功率数据（从原始_power表）"""
        total_power = 0
        online_count = 0
        total_count = 0
        
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    for dev_id, add_datetime in devices_info:
                        if add_datetime > point_time:
                            continue
                            
                        total_count += 1
                        try:
                            power_table = f"{dev_id}_power"
                            cursor.execute(
                                f"SELECT `功率` FROM `{power_table}` WHERE `时间点` = %s LIMIT 1",
                                (point_time,)
                            )
                            row = cursor.fetchone()
                            if row and row['功率']:
                                total_power += row['功率']
                                online_count += 1
                        except Exception:
                            pass
                            
            _log.debug(f"实时查询时间点 {point_time.strftime('%H:%M')}：功率={total_power}, 在线={online_count}, 总数={total_count}")
            
        except Exception as e:
            _log.error(f"实时查询功率数据失败: {e}")
            
        return {
            'power': total_power,
            'online': online_count,
            'total': total_count
        }

    def _get_history_data_from_redis(self, dev_id, date_day, area_path="ALL"):
        """从Redis获取设备历史数据（在线情况、用电量）
        
        注意：历史数据使用统一的缓存键（不包含区域路径），
        因为历史数据与区域无关，只与设备ID和日期有关。
        
        Returns:
            tuple: (is_online_day, electricity) 或 None（如果缓存不存在）
        """
        if not self.redis_client:
            return None
        
        try:
            account = getattr(self, 'current_username', '')
            if not account:
                return None
            
            # 统一使用 "ALL" 作为缓存键，与缓存写入保持一致
            cache_key = f"history:{account}:ALL:{dev_id}:{date_day}"
            _log.info(f"    Redis查询: key={cache_key}")
            cached = self.redis_client.get(cache_key)
            
            if cached:
                data = json.loads(cached)
                _log.info(f"    Redis命中: key={cache_key}, is_online={data.get('is_online_day', 0)}")
                return (data.get('is_online_day', 0), data.get('electricity', 0))
            _log.info(f"    Redis未命中: key={cache_key}")
            return None
        except Exception as e:
            _log.debug(f"从Redis获取历史数据失败: {e}")
            return None

    def _cache_history_data_to_redis(self, dev_id, date_day, is_online_day, electricity, area_path="ALL", expire=3600):
        """缓存设备历史数据到Redis
        
        注意：历史数据使用统一的缓存键（不包含区域路径），
        因为历史数据与区域无关，只与设备ID和日期有关。
        
        Args:
            expire: 缓存过期时间（秒），默认1小时
        """
        if not self.redis_client:
            return
        
        try:
            account = getattr(self, 'current_username', '')
            if not account:
                return
            
            # 统一使用 "ALL" 作为缓存键，避免不同区域查询时缓存不命中
            cache_key = f"history:{account}:ALL:{dev_id}:{date_day}"
            value = {
                'account': account,
                'area_path': 'ALL',  # 统一使用 ALL
                'dev_id': dev_id,
                'date_day': date_day,
                'is_online_day': is_online_day,
                'electricity': electricity,
                'cached_at': datetime.now().isoformat()
            }
            self.redis_client.setex(cache_key, expire, json.dumps(value))
            _log.info(f"    Redis写入: key={cache_key}, is_online={is_online_day}")
        except Exception as e:
            _log.debug(f"缓存历史数据到Redis失败: {e}")

    def _clear_area_cache_from_redis(self, area_path):
        """清除指定区域的Redis缓存
        
        当区域名称更改或区域被删除时调用，清除该区域相关的所有缓存数据。
        注意：历史数据和功率数据使用统一的缓存键（不包含区域路径），
        因此不需要按区域清除。
        """
        if not self.redis_client:
            return
        
        try:
            account = getattr(self, 'current_username', '')
            if not account:
                return
            
            # 注意：历史数据缓存使用统一的键（history:{account}:ALL:{dev_id}:{date_day}）
            # 不区分区域，因此不需要按区域清除
            # 当区域更改时，今天的数据会重新查询，历史数据不受影响
            
            # 清除设备列表缓存（按区域存储）
            devices_cache_key = f"devices:{account}:{area_path}"
            if self.redis_client.exists(devices_cache_key):
                self.redis_client.delete(devices_cache_key)
                _log.info(f"已清除区域 '{area_path}' 的设备列表缓存")
            
            # 注意：功率数据缓存也使用统一的键（power:{account}:ALL:{time_str}）
            # 不区分区域，因此不需要按区域清除
                
        except Exception as e:
            _log.error(f"清除区域 '{area_path}' 的Redis缓存失败: {e}")
    
    def _query_device_history_data(self, dev_id, date_day, area_path="ALL", is_today=False):
        """查询设备历史数据（优先Redis，失败则查MySQL并缓存）
        
        注意：历史数据（非今天）使用统一的缓存键（不包含区域路径），
        因为历史数据与区域无关，只与设备ID和日期有关。
        今天的数据需要实时查询，因为可能随区域筛选变化。
        
        Returns:
            tuple: (is_online_day, electricity)
        """
        # 1. 尝试从Redis获取（非今天数据才走缓存）
        # 历史数据使用统一的缓存键（不包含区域路径），避免同一设备在不同区域下重复缓存
        if not is_today:
            cached = self._get_history_data_from_redis(dev_id, date_day, "ALL")
            if cached is not None:
                _log.info(f"    设备 {dev_id} 日期 {date_day}: Redis缓存命中, is_online={cached[0]}")
                return cached
        
        # 2. 从MySQL查询
        try:
            is_online_day, electricity, _, _, _ = get_parsed_all_data(
                self.db_pool, dev_id, date_day, self.outline_time, is_today=is_today
            )
            
            _log.info(f"    设备 {dev_id} 日期 {date_day}: MySQL查询, is_online={is_online_day}, electricity={electricity}")
            
            # 3. 缓存到Redis（非今天数据）
            # 历史数据使用统一的缓存键（不包含区域路径）
            if not is_today:
                self._cache_history_data_to_redis(dev_id, date_day, is_online_day, electricity, "ALL")
            
            return (is_online_day, electricity)
        except Exception as e:
            _log.error(f"查询设备 {dev_id} 历史数据失败: {e}")
            return (0, 0)

    def _query_24h_power_data_fallback(self, devices_info, time_points, time_labels):
        """Fallback：从各设备的_power表查询（原始方式）"""
        power_sums = [0] * len(time_points)
        
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    for idx, point_time in enumerate(time_points):
                        total_power = 0
                        for dev_id, _ in devices_info:
                            try:
                                power_table = f"{dev_id}_power"
                                cursor.execute(
                                    f"SELECT `功率` FROM `{power_table}` WHERE `时间点` = %s LIMIT 1",
                                    (point_time,)
                                )
                                row = cursor.fetchone()
                                if row:
                                    total_power += row['功率'] or 0
                            except Exception:
                                pass
                        power_sums[idx] = total_power
            _log.warning("使用fallback方式查询24小时功率数据")
        except Exception as e:
            _log.error(f"Fallback查询失败: {e}")
            
        return time_labels, power_sums

    def _on_chart_data_ready(self, date_list, online_list, electricity_list, realtime_online, realtime_offline, total_power, power_24h_labels, power_24h_values, online_7d_area, electricity_7d_area):
        """主线程槽函数：图表数据准备就绪后更新UI（支持区域筛选）"""
        try:
            self._chart_date_list = date_list
            self._chart_online_list = online_list
            self._chart_electricity_list = electricity_list
            self._chart_realtime_online = realtime_online
            self._chart_realtime_offline = realtime_offline
            self._chart_total_power = total_power
            self._chart_power_24h_labels = power_24h_labels
            self._chart_power_24h_values = power_24h_values

            chart_areas = getattr(self, '_current_chart_areas', {})
            current_online_7d_area = chart_areas.get('online_7d', 'ALL')
            current_electricity_7d_area = chart_areas.get('electricity_7d', 'ALL')
            current_realtime_pie_area = chart_areas.get('realtime_pie', 'ALL')
            current_power_24h_area = chart_areas.get('power_24h', 'ALL')

            # 更新PyQt图表（如果存在）
            if online_7d_area == current_online_7d_area:
                if self.online_7_linecanvas is not None:
                    self.online_7_linecanvas.update_data(self._chart_date_list, self._chart_online_list)
                    _log.debug(f"7天在线率图表已更新，区域: {online_7d_area}")

            if electricity_7d_area == current_electricity_7d_area:
                if self.electricity_7_linecanvas is not None:
                    self.electricity_7_linecanvas.update_data(self._chart_date_list, self._chart_electricity_list)
                    _log.debug(f"7天用电量图表已更新，区域: {electricity_7d_area}")

            self.update_real_time_online_pie(self._chart_realtime_online, self._chart_realtime_offline)
            self._update_24h_power_chart()

            # 更新HTML展示界面图表（如果存在）
            self._update_html_charts(date_list, online_list, electricity_list, realtime_online, realtime_offline, power_24h_labels, power_24h_values)

            _log.debug("图表UI更新完成")
        except RuntimeError as e:
            _log.error(f"图表UI更新失败（对象可能已被删除）：{e}")
        except Exception as e:
            _log.error(f"图表UI更新失败：{e}")
            import traceback
            traceback.print_exc()

    def _update_html_charts(self, date_list, online_list, electricity_list, realtime_online, realtime_offline, power_24h_labels, power_24h_values):
        """更新HTML展示界面的图表数据"""
        try:
            if hasattr(self, 'area_display_widget') and self.area_display_widget:
                # 转换日期格式
                formatted_dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d in date_list]
                
                chart_data = {
                    'chart1': {
                        'online': realtime_online,
                        'offline': realtime_offline
                    },
                    'chart2': {
                        'dates': formatted_dates,
                        'values': online_list
                    },
                    'chart3': {
                        'dates': formatted_dates,
                        'values': electricity_list
                    },
                    'chart4': {
                        'times': power_24h_labels if power_24h_labels else [],
                        'values': power_24h_values if power_24h_values else []
                    }
                }
                self.area_display_widget.update_chart_data(chart_data)
                _log.debug("HTML图表数据已更新")
        except Exception as e:
            _log.error(f"更新HTML图表失败: {e}")

    def _update_24h_power_chart(self):
        """更新24小时功率折线图"""
        try:
            if hasattr(self, 'power_24h_linecanvas') and self.power_24h_linecanvas is not None:
                labels = getattr(self, '_chart_power_24h_labels', [])
                values = getattr(self, '_chart_power_24h_values', [])
                if labels and values:
                    self.power_24h_linecanvas.update_data(labels, values)
                    _log.debug(f"24小时功率图表更新: {len(labels)} 个数据点")
        except RuntimeError:
            _log.error("24小时功率图表对象已被删除")
        except Exception as e:
            _log.error(f"更新24小时功率图表失败: {e}")

    def _update_chart_ui(self):
        """主线程槽函数：更新图表UI（由后台线程通过信号触发）"""
        try:
            if self.online_7_linecanvas is not None:
                self.online_7_linecanvas.update_data(self._chart_date_list, self._chart_online_list)
            if self.electricity_7_linecanvas is not None:
                self.electricity_7_linecanvas.update_data(self._chart_date_list, self._chart_electricity_list)
        except RuntimeError:
            _log.error("7天图表对象已被删除")

        self.update_real_time_online_pie(self._chart_realtime_online, self._chart_realtime_offline)
        self._update_24h_power_chart()

    def update_real_time_online_pie(self, online_count, offline_count):
        """
        实时在线率饼状图更新（使用已统计的数据）
        """
        if self.online_pie_canvas is None:
            return

        try:
            _ = self.online_pie_canvas.fig
        except RuntimeError:
            _log.debug("实时在线率饼状图对象已被删除")
            self.online_pie_canvas = None
            return

        total_count = online_count + offline_count
        if total_count == 0:
            self.online_pie_canvas.update_data(0, 0)
            return

        try:
            online_rate = (online_count / total_count * 100) if total_count > 0 else 0
            offline_rate = (offline_count / total_count * 100) if total_count > 0 else 0
            self.online_pie_canvas.update_data(online_rate, offline_rate)
            _log.debug(f"实时在线率更新：在线{online_count}，离线{offline_count}，总计{total_count}")
        except Exception as e:
            _log.error(f"更新实时在线率饼状图失败: {e}")

    def _clear_ec_cache(self):
        """清空能耗缓存"""
        if hasattr(self, '_ec_cache'):
            self._ec_cache.clear()
            _log.debug("能耗缓存已清空（设备列表变化）")

    def receive_data(self, topic, data):
        try:
            device_id = self._extract_device_id_from_topic(topic)
            if device_id:
                self._update_device_online_status(device_id, True)
            self.data_processor.receive_data(topic, data)
        except Exception as e:
            _log.error(f"处理MQTT数据失败: {e}, topic={topic}")
            import traceback
            traceback.print_exc()

    def _extract_device_id_from_topic(self, topic):
        """从MQTT topic中提取设备号"""
        try:
            parts = topic.split('/')
            if len(parts) >= 2:
                return parts[1]
        except:
            pass
        return None

    def _update_device_online_status(self, device_id, is_online):
        """更新设备模型中的在线状态列"""
        try:
            row = self._device_row_cache.get(device_id)
            if row is None:
                for r in range(self.device_model.rowCount()):
                    if self.device_model.item(r, self.device_cols_index["设备号"]).text() == device_id:
                        row = r
                        self._device_row_cache[device_id] = row
                        break

            if row is not None and "在线状态" in self.device_cols_index:
                item = self.device_model.item(row, self.device_cols_index["在线状态"])
                if item:
                    item.setText("在线" if is_online else "离线")
                    if is_online:
                        item.setForeground(Qt.GlobalColor.green)
                    else:
                        item.setForeground(Qt.GlobalColor.red)
        except Exception as e:
            _log.error(f"更新设备 {device_id} 在线状态失败: {e}")

    def _on_device_status_changed(self, device_id, is_online):
        """设备状态变化处理槽函数"""
        try:
            _log.debug(f"设备 {device_id} 状态变化: {'在线' if is_online else '离线'}")
            self._update_device_online_status(device_id, is_online)
        except Exception as e:
            _log.error(f"处理设备 {device_id} 状态变化失败: {e}")

    def _update_device_ui(self, dev, result):
        """在主线程中更新设备UI（槽函数）- 使用批量更新机制"""
        self._pending_updates[dev] = result

    def _process_batch_updates(self):
        """批量处理设备UI更新（每100ms执行一次）"""
        if not self._pending_updates:
            return

        updates = self._pending_updates.copy()
        self._pending_updates.clear()

        if len(self._device_row_cache) != self.device_model.rowCount():
            self._refresh_device_row_cache()

        for dev, result in updates.items():
            self._update_single_device_ui(dev, result)

    def _refresh_device_row_cache(self):
        """刷新设备行索引缓存"""
        self._device_row_cache.clear()
        for row in range(self.device_model.rowCount()):
            try:
                dev_id = self.device_model.item(row, self.device_cols_index["设备号"]).text()
                self._device_row_cache[dev_id] = row
            except:
                pass

    def _update_single_device_ui(self, dev, result):
        """更新单个设备的UI"""
        try:
            row = self._device_row_cache.get(dev)
            if row is None:
                for r in range(self.device_model.rowCount()):
                    if self.device_model.item(r, self.device_cols_index["设备号"]).text() == dev:
                        row = r
                        self._device_row_cache[dev] = row
                        break

            if row is None:
                return

            for col_name, col_data in result.items():
                if col_name not in self.device_cols_index:
                    continue

                item = self.device_model.item(row, self.device_cols_index[col_name])
                if not item:
                    continue

                if isinstance(col_data, dict):
                    text_value = col_data.get('text', '')
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setText(text_value)

                    col_type = col_data.get('type', '')
                    if col_type in ('FLOAT', 'INT'):
                        try:
                            value = col_data.get('value')
                            if value is not None:
                                item.setData(float(value), Qt.ItemDataRole.UserRole)
                        except (ValueError, TypeError):
                            pass
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setText(str(col_data))
                    if col_name in self.apply_FLOAT_cols:
                        try:
                            if col_data and col_data != '-':
                                item.setData(float(col_data), Qt.ItemDataRole.UserRole)
                        except (ValueError, TypeError):
                            pass

        except Exception as e:
            _log.error(f"更新设备 {dev} UI失败: {e}")

    def update_area_serch(self):
        """更新区域搜索"""        
        self.UI_dm_area_combobox.clear()
        self.UI_dm_area_combobox.addItem("-- 请选择区域 --", None)

        self.UI_apply_area_combobox.clear()
        self.UI_apply_area_combobox.addItem("-- 请选择区域 --", None)
        
        def add_node_to_combobox(node, prefix="", parent_chain=None):
            name = node.get('name', '')
            level = node.get('level', 1)
            display_name = prefix + name
            
            if parent_chain is None:
                parent_chain = []
            
            node_data = {
                'name': name,
                'level': level,
                'parent_chain': parent_chain.copy(),
                'full_path': parent_chain + [name]
            }
            
            self.UI_dm_area_combobox.addItem(display_name, node_data)
            self.UI_apply_area_combobox.addItem(display_name, node_data)
            
            children = node.get('children', [])
            for child in children:
                add_node_to_combobox(child, prefix + "  ", parent_chain + [name])
        
        for area in self.area_list:
            add_node_to_combobox(area)

    def apply_serch(self):
        """应用界面搜索"""
        area_data = self.UI_apply_area_combobox.currentData()
        search_text = self.UI_search_in.text().strip()
        
        if area_data:
            area_path = "/".join(area_data.get('full_path', []))
        else:
            area_path = ""
        
        # 设置文本筛选条件
        self.apply_filter_proxy.setFilterFixedString(search_text)
        
        # 如果有区域选择，按区域筛选
        if area_path:
            # 获取该区域下的所有设备
            filtered_rows = set()
            for row in range(self.device_model.rowCount()):
                area1 = self.device_model.item(row, self.device_cols_index.get("区域1", -1))
                area2 = self.device_model.item(row, self.device_cols_index.get("区域2", -1))
                area3 = self.device_model.item(row, self.device_cols_index.get("区域3", -1))
                
                dev_area_path = ""
                if area1:
                    dev_area_path = area1.text()
                if area2 and area2.text():
                    dev_area_path += "/" + area2.text()
                if area3 and area3.text():
                    dev_area_path += "/" + area3.text()
                
                if dev_area_path.startswith(area_path):
                    filtered_rows.add(row)
            
            # 设置行筛选，只显示匹配的行
            self.apply_filter_proxy.set_filter_rows(filtered_rows)
            _log.info(f"应用界面按区域筛选: {area_path}, 匹配行数: {len(filtered_rows)}")
        else:
            # 清除行筛选
            self.apply_filter_proxy.clear_filter_rows()

    def dm_serch(self):
        """设备管理界面搜索"""
        area_data = self.UI_dm_area_combobox.currentData()
        search_text = self.UI_dm_search_in.text().strip()
        
        if area_data:
            area_path = "/".join(area_data.get('full_path', []))
        else:
            area_path = ""
        
        # 设置筛选条件
        self.dm_filter_proxy.setFilterFixedString(search_text)
        
        # 如果有区域选择，按区域筛选
        if area_path:
            # 获取该区域下的所有设备
            filtered_rows = set()
            for row in range(self.device_model.rowCount()):
                area1 = self.device_model.item(row, self.device_cols_index.get("区域1", -1))
                area2 = self.device_model.item(row, self.device_cols_index.get("区域2", -1))
                area3 = self.device_model.item(row, self.device_cols_index.get("区域3", -1))
                
                dev_area_path = ""
                if area1:
                    dev_area_path = area1.text()
                if area2 and area2.text():
                    dev_area_path += "/" + area2.text()
                if area3 and area3.text():
                    dev_area_path += "/" + area3.text()
                
                if dev_area_path.startswith(area_path):
                    filtered_rows.add(row)
            
            # 设置行筛选，只显示匹配的行
            self.dm_filter_proxy.set_filter_rows(filtered_rows)
            _log.info(f"设备管理按区域筛选: {area_path}, 匹配行数: {len(filtered_rows)}")
        else:
            # 清除行筛选
            self.dm_filter_proxy.clear_filter_rows()

    def show_message(self, message, msg_type="info"):
        """显示消息"""
        self.mess_ui.show_message(message, msg_type)

    def closeEvent(self, event):
        """窗口关闭事件"""
        _log.debug("窗口关闭事件触发")
        
        # 先接受关闭事件，确保窗口可以关闭
        event.accept()
        
        # 停止各个组件（使用try-except防止阻塞）
        try:
            self.stop_chart_update_thread()
        except Exception as e:
            _log.error(f"停止图表更新线程失败: {e}")
        
        try:
            self._stop_redis_reconnect_timer()
        except Exception as e:
            _log.error(f"停止Redis重连定时器失败: {e}")
        
        try:
            if hasattr(self, '_online_checker') and self._online_checker:
                self._online_checker.stop()
        except Exception as e:
            _log.error(f"停止在线检查器失败: {e}")
        
        # MQTT客户端停止可能阻塞，使用超时机制
        try:
            if hasattr(self, 'client') and self.client:
                # 使用QTimer延迟停止MQTT客户端，避免阻塞关闭过程
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, self._stop_mqtt_client)
        except Exception as e:
            _log.error(f"停止MQTT客户端失败: {e}")
    
    def _stop_mqtt_client(self):
        """停止MQTT客户端（异步）"""
        try:
            if hasattr(self, 'client') and self.client:
                self.client.stop()
                _log.debug("MQTT客户端已停止")
        except Exception as e:
            _log.error(f"停止MQTT客户端失败: {e}")


def main():
    """主函数"""
    # 启用高DPI支持
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    # 创建主窗口
    window = Platform()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()