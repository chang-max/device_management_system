"""
设备详情弹窗对话框
类似map_display.html中的设备详情弹窗
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QFrame, QScrollArea, QWidget, QSlider, QGridLayout,
    QSizePolicy
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from datetime import datetime


class DeviceDetailDialog(QDialog):
    """设备详情弹窗"""
    
    signal_control_command = pyqtSignal(str, str)  # 设备ID, 命令(on/off/dimming/read)
    signal_request_data = pyqtSignal(str)  # 请求设备实时数据
    
    # 基础数据列（排除实时数据列）
    BASE_DATA_COLS = ['设备号', '设备名称', '区域1', '区域2', '区域3', 
                      '相对X', '相对Y', '添加日期']
    
    # 实时数据中需要排除的列
    EXCLUDE_REALTIME_COLS = ['工作计划', '在线状态', 'isOnline', 'latestTime']

    # 单行格式显示的列
    SINGLE_LINE_COLS = ['当前时间', '设备时间']
    
    def __init__(self, device_id, device_model, device_cols_index, parent=None):
        super().__init__(parent)
        
        self.device_id = device_id
        self.device_model = device_model
        self.device_cols_index = device_cols_index
        self.device_data = {}  # 设备完整数据
        self.update_timer = None
        
        # 调光控制相关
        self.has_dimming = False
        self.dimming_key = None  # 调光字段名
        self.user_adjusting_slider = False  # 用户是否正在调整滑块
        
        self.setWindowTitle("设备详情")
        self.setFixedSize(450, 600)
        # 隐藏系统标题栏，使用自定义头部
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 8px;
            }
        """)
        
        self.init_ui()
        self.load_device_data()
        self.start_auto_update()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 头部 - 蓝色背景
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("""
            QFrame {
                background-color: #409eff;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        self.title_label = QLabel("设备详情")
        self.title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                font-size: 20px;
                border: none;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(header)
        
        # 内容区域 - 可滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: white; }")
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(16)
        
        # 基础信息区域
        base_section = self.create_section("基础信息")
        
        # 基础信息行
        base_grid = QGridLayout()
        base_grid.setColumnStretch(1, 1)
        base_grid.setVerticalSpacing(8)
        base_grid.setHorizontalSpacing(16)
        
        row = 0
        self.modal_device_id = self.add_info_row(base_grid, row, "设备号", "-")
        row += 1
        self.modal_device_name = self.add_info_row(base_grid, row, "设备名称", "-")
        row += 1
        self.modal_device_status = self.add_info_row(base_grid, row, "在线状态", "-", is_status=True)
        row += 1
        self.modal_device_area = self.add_info_row(base_grid, row, "所属区域", "-")
        row += 1
        self.modal_device_adddate = self.add_info_row(base_grid, row, "添加日期", "-")
        
        base_section.layout().addLayout(base_grid)
        content_layout.addWidget(base_section)
        
        # 实时数据区域
        self.realtime_section = self.create_section("实时数据")
        self.realtime_grid = QGridLayout()
        self.realtime_grid.setColumnStretch(1, 1)
        self.realtime_grid.setColumnStretch(3, 1)
        self.realtime_grid.setVerticalSpacing(8)
        self.realtime_grid.setHorizontalSpacing(16)
        
        self.realtime_labels = {}  # 存储实时数据的标签
        self.realtime_section.layout().addLayout(self.realtime_grid)
        content_layout.addWidget(self.realtime_section)
        
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
        # 底部控制区域（调光控制 + 按钮）
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background-color: #f5f7fa;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.setSpacing(10)
        
        # 调光控制区域（默认隐藏，与控制按钮同层级）
        self.dimming_container = QWidget()
        dimming_layout = QVBoxLayout(self.dimming_container)
        dimming_layout.setContentsMargins(0, 0, 0, 0)
        dimming_layout.setSpacing(5)
        
        # 当前亮度显示
        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("当前亮度:"))
        self.modal_brightness = QLabel("-")
        self.modal_brightness.setStyleSheet("font-weight: bold; color: #409eff;")
        brightness_layout.addWidget(self.modal_brightness)
        brightness_layout.addStretch()
        dimming_layout.addLayout(brightness_layout)
        
        # 亮度滑块
        slider_layout = QHBoxLayout()
        self.dimming_slider = QSlider(Qt.Orientation.Horizontal)
        self.dimming_slider.setRange(0, 100)
        self.dimming_slider.setValue(50)
        self.dimming_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                background: #409eff;
                border-radius: 9px;
                margin: -5px 0;
            }
            QSlider::sub-page:horizontal {
                background: #409eff;
                border-radius: 4px;
            }
        """)
        self.dimming_slider.valueChanged.connect(self.on_slider_changed)
        self.dimming_slider.sliderPressed.connect(self.on_slider_pressed)
        self.dimming_slider.sliderReleased.connect(self.on_slider_released)
        slider_layout.addWidget(self.dimming_slider)
        
        self.dimming_value_label = QLabel("50%")
        self.dimming_value_label.setFixedWidth(40)
        slider_layout.addWidget(self.dimming_value_label)
        
        dimming_layout.addLayout(slider_layout)
        footer_layout.addWidget(self.dimming_container)
        self.dimming_container.hide()
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_style_on = "background-color: #67c23a; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        btn_style_off = "background-color: #f56c6c; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        btn_style_dim = "background-color: #e6a23c; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        btn_style_read = "background-color: #909399; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        
        self.btn_on = QPushButton("开灯")
        self.btn_on.setStyleSheet(btn_style_on)
        self.btn_on.clicked.connect(lambda: self.send_control('on'))
        btn_layout.addWidget(self.btn_on)
        
        self.btn_off = QPushButton("关灯")
        self.btn_off.setStyleSheet(btn_style_off)
        self.btn_off.clicked.connect(lambda: self.send_control('off'))
        btn_layout.addWidget(self.btn_off)
        
        self.btn_dim = QPushButton("调光")
        self.btn_dim.setStyleSheet(btn_style_dim)
        self.btn_dim.clicked.connect(lambda: self.send_control('dimming'))
        btn_layout.addWidget(self.btn_dim)
        
        self.btn_read = QPushButton("读取")
        self.btn_read.setStyleSheet(btn_style_read)
        self.btn_read.clicked.connect(lambda: self.send_control('read'))
        btn_layout.addWidget(self.btn_read)
        
        footer_layout.addLayout(btn_layout)
        layout.addWidget(footer)
    
    def create_section(self, title):
        """创建信息区域"""
        section = QFrame()
        section.setStyleSheet("""
            QFrame {
                background-color: white;
            }
        """)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 13px;
            color: #666;
            border-bottom: 1px solid #eee;
            padding-bottom: 4px;
            font-weight: bold;
        """)
        layout.addWidget(title_label)
        
        return section
    
    def add_info_row(self, grid, row, label_text, value_text, is_status=False):
        """添加信息行到网格布局"""
        label = QLabel(label_text + ":")
        label.setStyleSheet("color: #666; font-size: 12px;")
        grid.addWidget(label, row, 0)
        
        value_label = QLabel(value_text)
        value_label.setStyleSheet("color: #333; font-size: 12px; font-weight: bold;")
        if is_status:
            value_label.setObjectName("status_label")
        grid.addWidget(value_label, row, 1)
        
        return value_label
    
    def load_device_data(self):
        """从device_model加载设备数据"""
        self._reload_device_data()
    
    def _reload_device_data(self):
        """重新加载设备数据（用于定时刷新）"""
        device_id_col = self.device_cols_index.get("设备号", -1)
        
        for row in range(self.device_model.rowCount()):
            item = self.device_model.item(row, device_id_col)
            if item and item.text() == self.device_id:
                # 找到设备，读取所有列数据
                # print(f"找到设备 {self.device_data}")
                for col_name, col_idx in self.device_cols_index.items():
                    if col_idx >= 0:
                        col_item = self.device_model.item(row, col_idx)
                        if col_item:
                            self.device_data[col_name] = col_item.text()
                        else:
                            self.device_data[col_name] = ""
                self.device_data['_row'] = row
                break
        
        self.update_display()
    
    def update_display(self):
        """更新显示"""
        if not self.device_data:
            return
        
        # 基础信息
        self.modal_device_id.setText(self.device_data.get('设备号', '-'))
        self.modal_device_name.setText(self.device_data.get('设备名称', '-'))
        
        # 在线状态 - 实时更新
        is_online = self.check_online_status()
        if is_online:
            self.modal_device_status.setText("在线")
            self.modal_device_status.setStyleSheet("color: #67c23a; font-size: 12px; font-weight: bold;")
        else:
            self.modal_device_status.setText("离线")
            self.modal_device_status.setStyleSheet("color: #f56c6c; font-size: 12px; font-weight: bold;")
        
        # 区域信息
        area_parts = []
        for key in ['区域1', '区域2', '区域3']:
            val = self.device_data.get(key, '')
            if val:
                area_parts.append(val)
        self.modal_device_area.setText('/'.join(area_parts) if area_parts else '-')
        
        # 位置信息（经度、纬度、时区）
        # location_parts = []
        # lng = self.device_data.get('经度', '')
        # lat = self.device_data.get('纬度', '')
        # if lng and lat:
        #     location_parts.append(f"{lng}, {lat}")
        # tz = self.device_data.get('时区', '')
        # if tz:
        #     location_parts.append(f"TZ:{tz}")
        # self.modal_device_location.setText(' | '.join(location_parts) if location_parts else '-')
        
        # 地址和添加日期
        # self.modal_device_address.setText(self.device_data.get('地址', '-'))
        self.modal_device_adddate.setText(self.device_data.get('添加日期', '-'))
        
        # 实时数据 - 排除基础数据列和特定排除列
        self.update_realtime_data()
        
        # 检查是否有调光相关字段
        self._check_dimming_field()
        
        # 更新调光显示（仅在用户未调整滑块时更新）
        # if self.has_dimming and not self.user_adjusting_slider:
        #     brightness_val = self.device_data.get(self.dimming_key, '')
        #     if brightness_val:
        #         try:
        #             brightness_num = int(float(brightness_val))
        #             self.modal_brightness.setText(str(brightness_num))
        #             # 更新滑块位置（不触发valueChanged信号）
        #             self.dimming_slider.blockSignals(True)
        #             self.dimming_slider.setValue(brightness_num)
        #             self.dimming_slider.blockSignals(False)
        #         except:
        #             pass
    
    def _check_dimming_field(self):
        """检查是否有调光相关字段"""
        if self.dimming_key:
            return  # 已经找到过
        
        for key in self.device_data.keys():
            if '调光' in key or 'bri' in key.lower() or 'dim' in key.lower() or '亮度' in key:
                self.has_dimming = True
                self.dimming_key = key
                self.dimming_container.show()
                return
        
        self.has_dimming = False
        self.dimming_key = None
        self.dimming_container.hide()
    
    def update_realtime_data(self):
        """更新实时数据显示"""
        # 清空现有实时数据
        for i in reversed(range(self.realtime_grid.count())):
            widget = self.realtime_grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.realtime_labels.clear()
        
        # 添加实时数据（排除基础数据列和排除列）
        row = 0
        col = 0
        has_realtime = False
        
        for key, value in self.device_data.items():
            if key in self.SINGLE_LINE_COLS:
                col = 0
                row += 1

            # 排除基础数据列
            if key.startswith('_') or key in self.BASE_DATA_COLS:
                continue
            # 排除特定列（工作计划、在线状态等）
            if key in self.EXCLUDE_REALTIME_COLS:
                continue
            # 排除调光字段（单独显示）
            if key == self.dimming_key:
                continue
            if not value or value == '-':
                continue
            
            has_realtime = True
            
            # 标签
            label = QLabel(key + ":")
            label.setStyleSheet("color: #666; font-size: 12px;")
            self.realtime_grid.addWidget(label, row, col * 2)
            
            # 值
            value_label = QLabel(str(value))
            value_label.setStyleSheet("color: #333; font-size: 12px; font-weight: bold;")
            self.realtime_grid.addWidget(value_label, row, col * 2 + 1)
            
            self.realtime_labels[key] = value_label
            
            # 两列布局
            col += 1
            if col >= 2:
                col = 0
                row += 1
        
        if not has_realtime:
            no_data_label = QLabel("暂无实时数据")
            no_data_label.setStyleSheet("color: #999; text-align: center;")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.realtime_grid.addWidget(no_data_label, 0, 0, 1, 4)
    
    def check_online_status(self):
        """检查设备在线状态 - 直接使用数据模型中的'在线状态'字段"""
        # 直接使用数据模型中的"在线状态"字段
        is_online_str = self.device_data.get('在线状态', '')
        if is_online_str:
            return is_online_str == '在线'
        
        return False
    
    def on_slider_pressed(self):
        """滑块被按下 - 用户开始调整"""
        self.user_adjusting_slider = True
    
    def on_slider_released(self):
        """滑块被释放 - 用户结束调整"""
        self.user_adjusting_slider = False
    
    def on_slider_changed(self, value):
        """滑块值改变"""
        self.dimming_value_label.setText(f"{value}%")
    
    def send_control(self, command):
        """发送控制命令"""
        if command == 'dimming':
            value = self.dimming_slider.value()
            self.signal_control_command.emit(self.device_id, f"dimming:{value}")
        else:
            self.signal_control_command.emit(self.device_id, command)
    
    def start_auto_update(self):
        """启动自动更新定时器"""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.request_update)
        self.update_timer.start(3000)  # 每3秒更新一次
        
        # 立即请求一次数据
        self.request_update()
    
    def request_update(self):
        """请求更新数据 - 从device_model重新加载"""
        # 从数据模型重新加载数据
        self._reload_device_data()
        # 发送信号请求MQTT数据更新
        self.signal_request_data.emit(self.device_id)
    
    def update_realtime_from_mqtt(self, mqtt_data):
        """从MQTT数据更新实时数据"""
        # 更新device_data
        for key, value in mqtt_data.items():
            self.device_data[key] = value
        
        # 刷新显示
        self.update_display()
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.update_timer:
            self.update_timer.stop()
        event.accept()
