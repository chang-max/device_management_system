"""
    单个导入界面
"""
from telnetlib import X3PAD
import PyQt6.QtWidgets as QtWidgets
from PyQt6.QtCore import pyqtSignal, Qt,QRegularExpression,QRect
from PyQt6.QtGui import QRegularExpressionValidator,QFont
from datetime import datetime


from UI.single_add_ui import Ui_Dialog

from log_save import Logger
_log = Logger(True).logger


class SingleAddDialog(QtWidgets.QDialog, Ui_Dialog):
    signal_add = pyqtSignal(int,str,str,str, str, str,float,float) # 信号槽：添加设备：设备名称-设备号-区域1-区域2-区域3-相对x-相对y
    
    def __init__(self, area_list,row = None ,default_config={}, parent=None):
        super(SingleAddDialog, self).__init__(parent)
        self.setupUi(self)
        self.row = row
        self.default_config = default_config
        _log.debug(f"单个导入界面初始化：{self.default_config}")
        
        # 设置窗口置顶
        self.setWindowFlags(
            Qt.WindowType.Dialog| Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint
        )
        self.setModal(True)

        # #测试窗口新创建
        # import random
        # self.setWindowTitle(f"single_add_{random.randint(0, 1000000)}")
        #限制设备号输入框只能输入数字
        self.UI_dev_num_lineedit.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]+")))

        self.area_dict = area_list

        # 初始化区域下拉框
        self.UI_area_1_combobox.addItem('')
        for area in self.area_dict:
            self.UI_area_1_combobox.addItem(area['name'])
        
        
        self.UI_area_1_combobox.textActivated.connect(self.update_area_2_combobox)
        self.UI_area_2_combobox.textActivated.connect(self.update_area_3_combobox)
        self.UI_affirm_btn.clicked.connect(self.UI_affirm_btn_clicked)
        self.UI_automatic_orientation_btn.clicked.connect(self.map_location_start_draw)
        self.UI_add_more_btn.clicked.connect(self.UI_add_more_btn_clicked)
        self.UI_cancel_btn.clicked.connect(self.close_and_destroy)


        if self.default_config:# 初始化默认配置
            _log.debug(f"初始化默认配置：{self.default_config}")
            self.UI_add_more_btn.setHidden(True) #隐藏保存并新增下一个

            self.UI_dev_name_lineedit.setText(self.default_config["设备名称"])
            self.UI_dev_num_lineedit.setText(self.default_config["设备号"])
            self.UI_dev_num_lineedit.setReadOnly(True)
            # 逐级设置区域，确保下拉框数据已加载
            self.UI_area_1_combobox.setCurrentText(self.default_config["区域1"])
            self.update_area_2_combobox()  # 手动触发更新区域2下拉框
            self.UI_area_2_combobox.setCurrentText(self.default_config["区域2"])
            self.update_area_3_combobox()  # 手动触发更新区域3下拉框
            self.UI_area_3_combobox.setCurrentText(self.default_config["区域3"])
            self.UI_X_lineedit.setText(str(self.default_config["相对X"]))
            self.UI_Y_lineedit.setText(str(self.default_config["相对Y"]))


    def update_area_2_combobox(self):
        """更新区域2下拉框"""
        area_1_index =  self.UI_area_1_combobox.currentIndex()-1
        self.UI_area_2_combobox.clear()
        self.UI_area_2_combobox.addItem("")
        self.UI_area_3_combobox.clear()
        self.UI_area_3_combobox.addItem("")
        if area_1_index != -1:
            for child in self.area_dict[area_1_index]['children']:
                self.UI_area_2_combobox.addItem(child['name'])
            area_2_index =  self.UI_area_2_combobox.currentIndex()-1

            if area_1_index != -1 and area_2_index != -1:
                for child in self.area_dict[area_1_index]['children'][area_2_index]['children']:
                    self.UI_area_3_combobox.addItem(child['name'])
    
    def update_area_3_combobox(self):
        """更新区域3下拉框"""
        area_1_index =  self.UI_area_1_combobox.currentIndex()-1
        area_2_index =  self.UI_area_2_combobox.currentIndex()-1
        self.UI_area_3_combobox.clear()
        self.UI_area_3_combobox.addItem("")
        if area_1_index != -1 and area_2_index != -1:
            for child in self.area_dict[area_1_index]['children'][area_2_index]['children']:
                self.UI_area_3_combobox.addItem(child['name'])

    def UI_add_more_btn_clicked(self):
        """保存并新增下一个设备"""
        device_name = self.UI_dev_name_lineedit.text()
        device_id = self.UI_dev_num_lineedit.text()
        area_1 = self.UI_area_1_combobox.currentText()
        area_2 = self.UI_area_2_combobox.currentText()
        area_3 = self.UI_area_3_combobox.currentText()

        X = self.UI_X_lineedit.text()
        Y = self.UI_Y_lineedit.text()
        if device_name == "" or device_id == "":
            QtWidgets.QMessageBox.warning(self, "警告", "设备名称和设备号不能为空！")
            return
        if X == "" or Y == "":
            QtWidgets.QMessageBox.warning(self, "警告", "请输入相对位置！")
            return
        else:
            X = float(X)
            Y = float(Y)

            # 确保 row 是整数
            row = self.row if self.row is not None else -1
            _log.debug(f"UI_add_more_btn_clicked 发射信号: row={row}, device_id={device_id}, device_name={device_name}")
            self.signal_add.emit(row, device_id, device_name, area_1, area_2, area_3, X, Y)
    
    def UI_affirm_btn_clicked(self):
        """确认仅添加当前设备"""
        device_name = self.UI_dev_name_lineedit.text()
        device_id = self.UI_dev_num_lineedit.text()
        area_1 = self.UI_area_1_combobox.currentText()
        area_2 = self.UI_area_2_combobox.currentText()
        area_3 = self.UI_area_3_combobox.currentText()

        X = self.UI_X_lineedit.text()
        Y = self.UI_Y_lineedit.text()

        
        if device_name == "" or device_id == "":
            QtWidgets.QMessageBox.warning(self, "警告", "设备名称和设备号不能为空！")
            return
        if X == "" or Y == "":
            QtWidgets.QMessageBox.warning(self, "警告", "请输入相对位置！")
            return
        else:
            X = float(X)
            Y = float(Y)
           
            # 确保 row 是整数
            row = self.row if self.row is not None else -1
            _log.debug(f"UI_affirm_btn_clicked 发射信号: row={row}, device_id={device_id}, device_name={device_name}")
            self.signal_add.emit(row, device_id, device_name, area_1, area_2, area_3, X, Y)
        self.close_and_destroy()

    def map_location_start_draw(self):
        """打开定位区域对话框 - 使用图片区域系统"""
        try:
            _log.debug("开始打开定位对话框（图片区域模式）")
            
            # 获取当前选择的区域
            area_1 = self.UI_area_1_combobox.currentText()
            area_2 = self.UI_area_2_combobox.currentText()
            area_3 = self.UI_area_3_combobox.currentText()
            
            if not area_1:
                QtWidgets.QMessageBox.warning(self, "警告", "请先选择一级区域！")
                return
            
            # 查找一级区域的图片路径
            image_path = None
            for area in self.area_dict:
                if area['name'] == area_1:
                    area_data = area.get('area', {})
                    # 优先使用 image_path，如果没有则使用 path
                    image_path = area_data.get('image_path', '') or area_data.get('path', '')
                    break
            
            if not image_path:
                QtWidgets.QMessageBox.warning(self, "警告", f"一级区域 '{area_1}' 未绑定图片，请先绑定图片！")
                return
            
            # 构建完整图片路径
            import os
            picture_dir = os.path.join(os.path.dirname(__file__), "picture")
            
            # 处理路径：移除开头的 / 或 \，因为 path 字段可能以 /picture/... 格式存储
            image_path_clean = image_path.lstrip('/\\')
            full_image_path = os.path.join(picture_dir, image_path_clean) if not os.path.isabs(image_path) else image_path
            
            # 如果拼接后的路径不存在，尝试直接使用 picture_dir + 文件名
            if not os.path.exists(full_image_path):
                # 从 path 中提取文件名
                filename = os.path.basename(image_path_clean)
                alternative_path = os.path.join(picture_dir, filename)
                if os.path.exists(alternative_path):
                    full_image_path = alternative_path
            
            if not os.path.exists(full_image_path):
                QtWidgets.QMessageBox.warning(self, "警告", f"区域图片不存在: {image_path}\n查找路径: {full_image_path}")
                return
            
            # 打开图片定位对话框
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QWidget
            from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QFont
            from PyQt6.QtCore import Qt, pyqtSignal, QRect
            
            class ImageLocationDialog(QDialog):
                """图片定位对话框 - 参照BatchLocationDialog实现"""
                signal_location_confirmed = pyqtSignal(dict)
                
                def __init__(self, image_path, existing_pos=None, parent=None):
                    super().__init__(parent)
                    self.setWindowTitle("在图片上定位设备")
                    self.setGeometry(100, 100, 1200, 900)
                    self.setWindowFlags(
                        Qt.WindowType.Window |
                        Qt.WindowType.WindowMaximizeButtonHint |
                        Qt.WindowType.WindowCloseButtonHint
                    )
                    
                    self.image_path = image_path
                    self.selected_pos = None  # 存储原始图片坐标
                    self.existing_pos = existing_pos  # 已有位置 (x, y) - 原始图片坐标
                    
                    self.init_ui()
                
                def init_ui(self):
                    """初始化UI - 参照BatchLocationDialog"""
                    layout = QVBoxLayout(self)
                    layout.setContentsMargins(10, 10, 10, 10)
                    layout.setSpacing(5)
                    
                    # 顶部信息栏
                    top_widget = QWidget()
                    top_widget.setFixedHeight(50)
                    top_widget.setStyleSheet("background-color: #f5f5f5; border-bottom: 1px solid #ddd;")
                    top_layout = QHBoxLayout(top_widget)
                    top_layout.setContentsMargins(10, 5, 10, 5)
                    
                    # 提示标签
                    if self.existing_pos:
                        hint_text = f"设备已有位置: ({self.existing_pos[0]}, {self.existing_pos[1]}) | 点击图片选择新位置（红色=旧位置，绿色=新位置）"
                    else:
                        hint_text = "点击图片选择设备位置"
                    hint_label = QLabel(hint_text)
                    hint_label.setStyleSheet("color: blue; font-size: 13px;")
                    top_layout.addWidget(hint_label)
                    
                    top_layout.addStretch()
                    layout.addWidget(top_widget)
                    
                    # 图片显示区域 - 使用QWidget包装
                    image_container = QWidget()
                    image_layout = QVBoxLayout(image_container)
                    image_layout.setContentsMargins(0, 0, 0, 0)
                    
                    self.image_label = ImageClickLabel(self)
                    self.image_label.signal_clicked.connect(self.on_image_clicked)
                    
                    pixmap = QPixmap(self.image_path)
                    if not pixmap.isNull():
                        self.pixmap_original = pixmap
                        self.image_label.set_image(self.image_path)
                        
                        # 如果有已有位置（原始坐标），设置到image_label中显示
                        if self.existing_pos:
                            self.image_label.existing_point_original = self.existing_pos
                            self.image_label.update_display()
                    else:
                        self.image_label.setText("无法加载图片")
                    
                    image_layout.addWidget(self.image_label)
                    layout.addWidget(image_container, 1)  # 占据剩余空间
                    
                    # 底部按钮区域
                    btn_widget = QWidget()
                    btn_widget.setFixedHeight(50)
                    btn_widget.setStyleSheet("background-color: #f5f5f5; border-top: 1px solid #ddd;")
                    btn_layout = QHBoxLayout(btn_widget)
                    btn_layout.setContentsMargins(10, 5, 10, 5)
                    
                    btn_layout.addStretch()
                    
                    self.confirm_btn = QPushButton("确认")
                    self.confirm_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #67c23a;
                            color: white;
                            padding: 8px 24px;
                            border-radius: 4px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: #85ce61;
                        }
                    """)
                    self.confirm_btn.clicked.connect(self.on_confirm)
                    self.confirm_btn.setEnabled(self.existing_pos is not None)
                    btn_layout.addWidget(self.confirm_btn)
                    
                    cancel_btn = QPushButton("取消")
                    cancel_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #909399;
                            color: white;
                            padding: 8px 24px;
                            border-radius: 4px;
                        }
                        QPushButton:hover {
                            background-color: #a6a9ad;
                        }
                    """)
                    cancel_btn.clicked.connect(self.reject)
                    btn_layout.addWidget(cancel_btn)
                    
                    layout.addWidget(btn_widget)
                
                def on_image_clicked(self, x, y):
                    """图片被点击 - 接收的是原始图片坐标"""
                    self.selected_pos = (x, y)
                    self.confirm_btn.setEnabled(True)
                    _log.debug(f"选择位置(原始图片坐标): ({x}, {y})")
                
                def on_confirm(self):
                    """确认选择 - 发送原始图片坐标"""
                    if self.selected_pos:
                        location_data = {
                            'x': self.selected_pos[0],
                            'y': self.selected_pos[1]
                        }
                        self.signal_location_confirmed.emit(location_data)
                        self.accept()
            
            class ImageClickLabel(QLabel):
                """可点击的图片Label - 参照EditableDeviceLabel实现"""
                signal_clicked = pyqtSignal(int, int)  # 发送原始图片坐标
                
                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setStyleSheet("border: 2px solid #ccc; background-color: #f0f0f0;")
                    self.setMouseTracking(True)
                    
                    # 设置最小尺寸
                    self.setMinimumSize(600, 400)
                    
                    # 原始图片
                    self.pixmap_original = None
                    
                    # 选择的点（原始图片坐标）
                    self.selected_point_original = None
                    self.existing_point_original = None
                    
                    # 缩放和平移参数
                    self.scale_factor = 1.0
                    self.zoom_factor = 1.0
                    self.offset_x = 0
                    self.offset_y = 0
                    self.pan_x = 0
                    self.pan_y = 0
                    
                    # 交互状态
                    self.is_panning = False
                    self.last_mouse_pos = None
                
                def set_image(self, image_path):
                    """设置背景图片"""
                    if os.path.exists(image_path):
                        self.pixmap_original = QPixmap(image_path)
                        self.reset_view()
                    else:
                        self.pixmap_original = None
                        self.setText(f"图片不存在: {image_path}")
                
                def reset_view(self):
                    """重置视图"""
                    self.zoom_factor = 1.0
                    self.pan_x = 0
                    self.pan_y = 0
                    self.update_display()
                
                def update_display(self):
                    """更新显示 - 参照EditableDeviceLabel"""
                    if not self.pixmap_original:
                        return
                    
                    # 获取当前尺寸（使用widget的实际尺寸）
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
                    
                    # 绘制标记点
                    self._draw_markers(painter)
                    
                    # 绘制提示信息
                    painter.setPen(QColor(0, 0, 0))
                    font = QFont()
                    font.setPointSize(10)
                    painter.setFont(font)
                    painter.drawText(10, 20, f"缩放: {self.zoom_factor*100:.0f}% | 滚轮缩放 | 中键平移 | 左键选点")
                    
                    painter.end()
                    self.setPixmap(display_pixmap)
                
                def _draw_markers(self, painter):
                    """绘制标记点"""
                    # 绘制已有位置（红色）
                    if self.existing_point_original:
                        pen = QPen(QColor(255, 0, 0), 3)
                        painter.setPen(pen)
                        brush = QBrush(QColor(255, 0, 0))
                        painter.setBrush(brush)
                        
                        x = int(self.existing_point_original[0] * self.scale_factor + self.offset_x)
                        y = int(self.existing_point_original[1] * self.scale_factor + self.offset_y)
                        
                        painter.drawEllipse(x - 6, y - 6, 12, 12)
                        painter.drawText(x + 15, y, f"旧位置({self.existing_point_original[0]}, {self.existing_point_original[1]})")
                    
                    # 绘制新选择的位置（绿色）
                    if self.selected_point_original:
                        pen = QPen(QColor(0, 255, 0), 3)
                        painter.setPen(pen)
                        brush = QBrush(QColor(0, 255, 0))
                        painter.setBrush(brush)
                        
                        x = int(self.selected_point_original[0] * self.scale_factor + self.offset_x)
                        y = int(self.selected_point_original[1] * self.scale_factor + self.offset_y)
                        
                        painter.drawEllipse(x - 6, y - 6, 12, 12)
                        painter.drawText(x + 15, y, f"新位置({self.selected_point_original[0]}, {self.selected_point_original[1]})")
                
                def mousePressEvent(self, event):
                    if not self.pixmap_original:
                        return
                    
                    # 中键按下 - 开始平移
                    if event.button() == Qt.MouseButton.MiddleButton:
                        self.is_panning = True
                        self.last_mouse_pos = event.pos()
                        self.setCursor(Qt.CursorShape.ClosedHandCursor)
                        return
                    
                    # 左键按下 - 选择位置
                    if event.button() == Qt.MouseButton.LeftButton:
                        img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
                        img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
                        
                        if 0 <= img_x <= self.pixmap_original.width() and 0 <= img_y <= self.pixmap_original.height():
                            self.selected_point_original = (img_x, img_y)
                            self.signal_clicked.emit(img_x, img_y)
                            self.update_display()
                
                def mouseMoveEvent(self, event):
                    if not self.pixmap_original:
                        return
                    
                    if self.is_panning and self.last_mouse_pos:
                        delta_x = event.pos().x() - self.last_mouse_pos.x()
                        delta_y = event.pos().y() - self.last_mouse_pos.y()
                        self.pan_x += delta_x
                        self.pan_y += delta_y
                        self.last_mouse_pos = event.pos()
                        self.update_display()
                        return
                    
                    img_x = int((event.pos().x() - self.offset_x) / self.scale_factor)
                    img_y = int((event.pos().y() - self.offset_y) / self.scale_factor)
                    
                    if 0 <= img_x <= self.pixmap_original.width() and 0 <= img_y <= self.pixmap_original.height():
                        self.setCursor(Qt.CursorShape.CrossCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                
                def mouseReleaseEvent(self, event):
                    if event.button() == Qt.MouseButton.MiddleButton and self.is_panning:
                        self.is_panning = False
                        self.last_mouse_pos = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                
                def wheelEvent(self, event):
                    if not self.pixmap_original:
                        return
                    
                    delta = event.angleDelta().y()
                    
                    if delta > 0:
                        new_zoom = self.zoom_factor * 1.1
                    else:
                        new_zoom = self.zoom_factor / 1.1
                    
                    new_zoom = max(0.5, min(new_zoom, 5.0))
                    
                    if new_zoom != self.zoom_factor:
                        self.zoom_factor = new_zoom
                        self.update_display()
                
                def resizeEvent(self, event):
                    super().resizeEvent(event)
                    self.update_display()
            
            # 获取设备已有的XY坐标（如果有）
            existing_x = self.UI_X_lineedit.text().strip()
            existing_y = self.UI_Y_lineedit.text().strip()
            existing_pos = None
            if existing_x and existing_y:
                try:
                    # 支持浮点数坐标（如 '432.0'）
                    existing_pos = (int(float(existing_x)), int(float(existing_y)))
                except ValueError:
                    existing_pos = None
            
            # 创建并显示对话框，传入已有位置
            dialog = ImageLocationDialog(full_image_path, existing_pos, self)
            dialog.signal_location_confirmed.connect(self.on_location_confirmed)
            dialog.exec()
            _log.debug("定位对话框已关闭")
            
        except Exception as e:
            _log.error(f"打开定位对话框失败: {e}")
            import traceback
            traceback.print_exc()

    def on_location_confirmed(self, location_data):
        """定位区域对话框确认信号-槽函数 - 保存相对坐标"""
        # 保存相对坐标到relx和rely字段（通过信号传递）
        x = str(location_data.get("x", 0))
        y = str( location_data.get("y", 0))
        self.UI_X_lineedit.setText(x)
        self.UI_Y_lineedit.setText(y)
        _log.debug(f"设备定位确认: 相对坐标 ({x}, {y})")
        
        # 可以在这里显示坐标信息
        QtWidgets.QMessageBox.information(self, "定位成功", f"已设置设备位置: ({x}, {y})\n\n坐标将保存到数据库的relx和rely字段。")

    # 关闭时自动销毁
    def close_and_destroy(self):
        # 先关闭，再销毁
        _log.debug(f"关闭单个导入界面")
        self.close()
        self.deleteLater()



if __name__ == "__main__":
    import sys
    area_list =[{'level': 1, 'name': 'a', 'children': [{'level': 2, 'name': 'vvv', 'children': [{'level': 3, 'name': '啊啊啊啊'}, {'level': 3, 'name': 'nnn'}]}, {'level': 2, 'name': 'mmm', 'children': []}]}, {'level': 1, 'name': 'baaaa', 'children': [{'level': 2, 'name': 'asdasd', 'children': []}]}]
    app = QtWidgets.QApplication(sys.argv)
    dialog = SingleAddDialog(area_list)
    dialog.exec()
