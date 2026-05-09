"""
批量设备位置编辑对话框
用于在图片上批量编辑所有设备的位置
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QMessageBox, QComboBox, QSplitter, QWidget,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QFrame
)
from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
import os
import json


class EditableDeviceLabel(QLabel):
    """可编辑设备位置的图片Label"""
    
    signal_device_moved = pyqtSignal(str, int, int)  # 设备ID, 新X, 新Y
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 2px solid #ccc; background-color: #f0f0f0;")
        
        # 图片相关
        self.pixmap_original = None
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        
        # 设备数据
        self.devices = []  # [{'id': '', 'name': '', 'x': 0, 'y': 0, 'area1': '', 'area2': '', 'area3': ''}]
        
        # 拖动状态
        self.dragging_device = None
        self.drag_start_pos = None
        self.hovered_device = None
        
        # 缩放和平移
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.is_panning = False
        self.last_mouse_pos = None
        
        # 显示设置
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
    
    def set_image(self, image_path):
        """设置背景图片"""
        if os.path.exists(image_path):
            self.pixmap_original = QPixmap(image_path)
            self.reset_view()
        else:
            self.pixmap_original = None
            self.setText(f"图片不存在: {image_path}")
    
    def set_devices(self, devices):
        """设置设备列表"""
        self.devices = devices
        self.update_display()
    
    def reset_view(self):
        """重置视图"""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_display()
    
    def update_display(self):
        """更新显示"""
        if not self.pixmap_original:
            return
        
        # 获取当前尺寸
        current_width = max(self.width(), 400)
        current_height = max(self.height(), 300)
        
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
        display_pixmap.fill(QColor(240, 240, 240))
        
        painter = QPainter(display_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 绘制图片
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
        
        # 绘制设备
        self._draw_devices(painter)
        
        # 绘制提示信息
        painter.setPen(QColor(0, 0, 0))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(10, 20, f"缩放: {self.zoom_factor*100:.0f}% | 滚轮缩放 | 中键平移 | 拖动设备调整位置")
        
        painter.end()
        self.setPixmap(display_pixmap)
    
    def _draw_devices(self, painter):
        """绘制设备"""
        for device in self.devices:
            x = int(device.get('x', 0) * self.scale_factor + self.offset_x)
            y = int(device.get('y', 0) * self.scale_factor + self.offset_y)
            device_id = device.get('id', '')
            
            # 判断是否是当前拖动的设备
            is_dragging = self.dragging_device and self.dragging_device.get('id') == device_id
            # 判断是否是鼠标悬浮的设备
            is_hovered = self.hovered_device and self.hovered_device.get('id') == device_id
            
            # 选择颜色：拖动中为黄色，悬浮为橙色，其他为蓝色
            if is_dragging:
                color = QColor(255, 255, 0)  # 黄色
                border_color = QColor(255, 165, 0)  # 橙色边框
                radius = 10
            elif is_hovered:
                color = QColor(255, 200, 100)  # 浅橙色
                border_color = QColor(255, 140, 0)  # 深橙色边框
                radius = 8
            else:
                color = QColor(100, 150, 255)  # 蓝色
                border_color = QColor(0, 100, 200)  # 深蓝色边框
                radius = 6
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(border_color, 2))
            painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
            
            # 绘制设备名称和ID
            painter.setPen(QColor(0, 0, 0))
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            name = device.get('name', '') or device_id
            painter.drawText(x + radius + 3, y + 4, f"{name} ({device.get('x', 0)}, {device.get('y', 0)})")
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if not self.pixmap_original:
            return
        
        # 中键按下 - 开始平移
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        
        # 左键按下 - 检查是否点击了设备
        if event.button() == Qt.MouseButton.LeftButton:
            img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
            img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
            
            # 查找点击的设备（倒序，优先选中最上层的）
            for device in reversed(self.devices):
                dx = device.get('x', 0) - img_x
                dy = device.get('y', 0) - img_y
                if (dx * dx + dy * dy) < 144:  # 12像素半径
                    self.dragging_device = device
                    self.drag_start_pos = (device.get('x', 0), device.get('y', 0))
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.update_display()
                    return
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
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
        
        # 拖动设备模式
        if self.dragging_device:
            img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
            img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
            
            # 确保坐标在图片范围内
            img_x = max(0, min(img_x, self.pixmap_original.width()))
            img_y = max(0, min(img_y, self.pixmap_original.height()))
            
            # 更新设备位置
            self.dragging_device['x'] = img_x
            self.dragging_device['y'] = img_y
            self.update_display()
            return
        
        # 检查鼠标悬浮在哪个设备上
        img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
        img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
        
        prev_hovered = self.hovered_device
        self.hovered_device = None
        
        for device in reversed(self.devices):
            dx = device.get('x', 0) - img_x
            dy = device.get('y', 0) - img_y
            if (dx * dx + dy * dy) < 144:  # 12像素半径
                self.hovered_device = device
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                break
        
        if self.hovered_device != prev_hovered:
            self.update_display()
        
        if not self.hovered_device:
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        # 结束平移
        if event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
            self.is_panning = False
            self.last_mouse_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        
        # 结束设备拖动
        if self.dragging_device and event.button() == Qt.MouseButton.LeftButton:
            device_id = self.dragging_device.get('id', '')
            new_x = self.dragging_device.get('x', 0)
            new_y = self.dragging_device.get('y', 0)
            
            # 检查位置是否真的改变了
            if self.drag_start_pos:
                start_x, start_y = self.drag_start_pos
                if abs(start_x - new_x) > 0 or abs(start_y - new_y) > 0:
                    self.signal_device_moved.emit(device_id, new_x, new_y)
            
            self.dragging_device = None
            self.drag_start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update_display()
    
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 缩放"""
        if not self.pixmap_original:
            return
        
        delta = event.angleDelta().y()
        
        # 计算新的缩放因子
        if delta > 0:
            new_zoom = self.zoom_factor * 1.1
        else:
            new_zoom = self.zoom_factor / 1.1
        
        # 限制缩放范围
        new_zoom = max(0.5, min(new_zoom, 5.0))
        
        if new_zoom != self.zoom_factor:
            self.zoom_factor = new_zoom
            self.update_display()
    
    def resizeEvent(self, event):
        """窗口大小改变时重新绘制"""
        super().resizeEvent(event)
        self.update_display()
    
    def get_device_positions(self):
        """获取所有设备的当前位置"""
        return [
            {
                'id': d.get('id', ''),
                'name': d.get('name', ''),
                'x': d.get('x', 0),
                'y': d.get('y', 0)
            }
            for d in self.devices
        ]


class BatchLocationDialog(QDialog):
    """批量设备位置编辑对话框"""
    
    signal_positions_saved = pyqtSignal(list)  # 发送保存的设备位置列表
    
    def __init__(self, parent=None, db_pool=None, device_model=None, 
                 area_list=None, device_cols_index=None, picture_dir=None):
        super().__init__(parent)
        
        self.db_pool = db_pool
        self.device_model = device_model
        self.area_list = area_list or []
        self.device_cols_index = device_cols_index or {}
        self.picture_dir = picture_dir or os.path.join(os.path.dirname(__file__), "picture")
        
        # 数据存储
        self.all_devices = []  # 所有设备
        self.changed_devices = {}  # 记录修改过的设备 {device_id: {x, y}}
        self.current_area1 = None  # 当前选中的一级区域
        self.area1_images = {}  # 一级区域对应的图片路径
        
        self.setWindowTitle("批量编辑设备位置")
        self.setGeometry(100, 100, 1400, 900)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # 顶部信息栏 - 使用QWidget包装以控制高度
        top_widget = QWidget()
        top_widget.setFixedHeight(40)  # 固定高度40像素
        top_widget.setStyleSheet("background-color: #f5f5f5; border-bottom: 1px solid #ddd;")
        info_layout = QHBoxLayout(top_widget)
        info_layout.setContentsMargins(10, 5, 10, 5)
        info_layout.setSpacing(10)
        
        info_layout.addWidget(QLabel("选择一级区域:"))
        
        self.area1_combo = QComboBox()
        self.area1_combo.setFixedWidth(200)
        self.area1_combo.currentTextChanged.connect(self.on_area1_changed)
        info_layout.addWidget(self.area1_combo)
        
        info_layout.addStretch()
        
        self.info_label = QLabel("准备就绪")
        self.info_label.setStyleSheet("color: blue;")
        info_layout.addWidget(self.info_label)
        
        layout.addWidget(top_widget)
        
        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧设备列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("设备列表:"))
        
        self.device_tree = QTreeWidget()
        self.device_tree.setHeaderLabels(["设备", "位置", "状态"])
        self.device_tree.setColumnWidth(0, 150)
        self.device_tree.setColumnWidth(1, 100)
        self.device_tree.itemClicked.connect(self.on_device_clicked)
        left_layout.addWidget(self.device_tree)
        
        # 统计信息
        self.stats_label = QLabel("总设备: 0 | 已定位: 0 | 未定位: 0")
        left_layout.addWidget(self.stats_label)
        
        splitter.addWidget(left_widget)
        
        # 右侧图片编辑区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 图片显示区域
        self.image_label = EditableDeviceLabel(self)
        self.image_label.signal_device_moved.connect(self.on_device_moved)
        right_layout.addWidget(self.image_label)
        
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setSizes([300, 1100])
        
        layout.addWidget(splitter)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        self.reset_btn = QPushButton("重置视图")
        self.reset_btn.clicked.connect(self.on_reset_view)
        btn_layout.addWidget(self.reset_btn)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存所有修改")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 16px;")
        self.save_btn.clicked.connect(self.on_save)
        btn_layout.addWidget(self.save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def load_data(self):
        """加载数据"""
        # 加载一级区域列表
        self.load_area1_list()
        
        # 加载所有设备
        self.load_all_devices()
        
        # 加载区域图片映射
        self.load_area_images()
    
    def load_area1_list(self):
        """加载一级区域列表"""
        self.area1_combo.clear()
        self.area1_combo.addItem("请选择...")
        
        for area in self.area_list:
            if area.get('level') == 1 or area.get('level') == 2:  # 根节点是1，一级区域是2
                area_name = area.get('name', '')
                if area_name:
                    self.area1_combo.addItem(area_name)
    
    def load_all_devices(self):
        """从device_model加载所有设备"""
        self.all_devices = []
        
        device_id_col = self.device_cols_index.get("设备号", -1)
        device_name_col = self.device_cols_index.get("设备名称", -1)
        area1_col = self.device_cols_index.get("区域1", -1)
        area2_col = self.device_cols_index.get("区域2", -1)
        area3_col = self.device_cols_index.get("区域3", -1)
        x_col = self.device_cols_index.get("相对X", -1)
        y_col = self.device_cols_index.get("相对Y", -1)
        
        for row in range(self.device_model.rowCount()):
            device_id_item = self.device_model.item(row, device_id_col)
            if not device_id_item:
                continue
            
            device_id = device_id_item.text()
            device_name = self.device_model.item(row, device_name_col).text() if device_name_col >= 0 else ""
            area1 = self.device_model.item(row, area1_col).text() if area1_col >= 0 else ""
            area2 = self.device_model.item(row, area2_col).text() if area2_col >= 0 else ""
            area3 = self.device_model.item(row, area3_col).text() if area3_col >= 0 else ""
            
            # 获取XY坐标，默认为0
            x = 0
            y = 0
            if x_col >= 0:
                x_text = self.device_model.item(row, x_col).text()
                try:
                    x = int(float(x_text)) if x_text else 0
                except ValueError:
                    x = 0
            if y_col >= 0:
                y_text = self.device_model.item(row, y_col).text()
                try:
                    y = int(float(y_text)) if y_text else 0
                except ValueError:
                    y = 0
            
            self.all_devices.append({
                'id': device_id,
                'name': device_name,
                'area1': area1,
                'area2': area2,
                'area3': area3,
                'x': x,
                'y': y,
                'row': row  # 记录在model中的行号
            })
        
        self.update_stats()
    
    def load_area_images(self):
        """加载一级区域对应的图片路径"""
        self.area1_images = {}
        
        # 从区域列表中获取path字段
        for area in self.area_list:
            if area.get('level') == 1 or area.get('level') == 2:
                area_name = area.get('name', '')
                area_data = area.get('area', {})
                path = area_data.get('path', '')
                
                if area_name and path:
                    # 构建完整路径
                    image_name = os.path.basename(path)
                    full_path = os.path.join(self.picture_dir, image_name)
                    self.area1_images[area_name] = full_path
    
    def on_area1_changed(self, area1_name):
        """一级区域改变时"""
        if area1_name == "请选择..." or not area1_name:
            self.current_area1 = None
            self.image_label.setText("请选择一级区域")
            self.device_tree.clear()
            return
        
        self.current_area1 = area1_name
        
        # 加载对应区域的图片
        image_path = self.area1_images.get(area1_name, '')
        if image_path and os.path.exists(image_path):
            self.image_label.set_image(image_path)
            self.info_label.setText(f"当前区域: {area1_name} | 图片: {os.path.basename(image_path)}")
        else:
            self.image_label.setText(f"区域 '{area1_name}' 未绑定图片，请先绑定图片！")
            self.info_label.setText(f"当前区域: {area1_name} | 未绑定图片")
        
        # 更新设备列表
        self.update_device_tree()
        
        # 更新图片上的设备显示
        self.update_image_devices()
    
    def update_device_tree(self):
        """更新设备树列表"""
        self.device_tree.clear()
        
        if not self.current_area1:
            return
        
        # 筛选当前区域的设备
        area_devices = [d for d in self.all_devices if d.get('area1') == self.current_area1]
        
        # 按二级区域分组
        area2_groups = {}
        for device in area_devices:
            area2 = device.get('area2', '') or '未分组'
            if area2 not in area2_groups:
                area2_groups[area2] = []
            area2_groups[area2].append(device)
        
        # 构建树
        for area2, devices in sorted(area2_groups.items()):
            area2_item = QTreeWidgetItem(self.device_tree)
            area2_item.setText(0, area2)
            area2_item.setText(1, f"{len(devices)}个设备")
            
            for device in devices:
                device_item = QTreeWidgetItem(area2_item)
                device_item.setText(0, device.get('name', '') or device.get('id', ''))
                
                x, y = device.get('x', 0), device.get('y', 0)
                if x == 0 and y == 0:
                    device_item.setText(1, "未定位")
                    device_item.setForeground(1, QColor(255, 0, 0))
                else:
                    device_item.setText(1, f"({x}, {y})")
                
                # 标记是否被修改过
                device_id = device.get('id', '')
                if device_id in self.changed_devices:
                    device_item.setText(2, "已修改")
                    device_item.setForeground(2, QColor(0, 128, 0))
                
                device_item.setData(0, Qt.ItemDataRole.UserRole, device)
        
        self.device_tree.expandAll()
    
    def update_image_devices(self):
        """更新图片上显示的设备"""
        if not self.current_area1:
            self.image_label.set_devices([])
            return
        
        # 筛选当前区域的设备
        area_devices = [d for d in self.all_devices if d.get('area1') == self.current_area1]
        self.image_label.set_devices(area_devices)
    
    def on_device_clicked(self, item, column):
        """设备树中的设备被点击"""
        device = item.data(0, Qt.ItemDataRole.UserRole)
        if device:
            # 可以在这里高亮显示设备
            pass
    
    def on_device_moved(self, device_id, new_x, new_y):
        """设备被移动"""
        # 更新all_devices中的位置
        for device in self.all_devices:
            if device.get('id') == device_id:
                device['x'] = new_x
                device['y'] = new_y
                break
        
        # 记录修改
        self.changed_devices[device_id] = {'x': new_x, 'y': new_y}
        
        # 更新UI
        self.update_device_tree()
        self.info_label.setText(f"设备 {device_id} 位置已修改为 ({new_x}, {new_y})")
    
    def on_reset_view(self):
        """重置视图"""
        self.image_label.reset_view()
    
    def on_save(self):
        """保存所有修改"""
        if not self.changed_devices:
            QMessageBox.information(self, "提示", "没有需要保存的修改")
            return
        
        # 确认保存
        reply = QMessageBox.question(
            self, 
            "确认保存", 
            f"确定要保存 {len(self.changed_devices)} 个设备的位置修改吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 准备保存的数据
        devices_to_save = []
        for device_id, pos in self.changed_devices.items():
            # 查找完整的设备信息
            for device in self.all_devices:
                if device.get('id') == device_id:
                    devices_to_save.append({
                        'id': device_id,
                        'name': device.get('name', ''),
                        'x': pos['x'],
                        'y': pos['y'],
                        'row': device.get('row', -1)
                    })
                    break
        
        # 发送信号
        self.signal_positions_saved.emit(devices_to_save)
        
        # 关闭对话框
        self.accept()
    
    def update_stats(self):
        """更新统计信息"""
        total = len(self.all_devices)
        positioned = sum(1 for d in self.all_devices if d.get('x', 0) != 0 or d.get('y', 0) != 0)
        unpositioned = total - positioned
        
        self.stats_label.setText(f"总设备: {total} | 已定位: {positioned} | 未定位: {unpositioned}")
