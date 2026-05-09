"""
图表区域筛选组件
为每个图表提供区域combobox和确认按钮
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QComboBox, QLabel, QGroupBox)
from PyQt6.QtCore import pyqtSignal
import json
import logging

_log = logging.getLogger(__name__)


class ChartAreaFilter(QWidget):
    """图表区域筛选组件"""
    
    # 信号：区域选择确认时发射 (chart_name, selected_area_path)
    area_confirmed = pyqtSignal(str, str)
    
    def __init__(self, chart_name, parent=None):
        super().__init__(parent)
        self.chart_name = chart_name
        self.current_user = None
        self.area_list = []
        self.selected_area_path = "ALL"
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        
        # 区域标签
        area_label = QLabel("区域:")
        layout.addWidget(area_label)
        
        # 区域combobox
        self.area_combobox = QComboBox()
        self.area_combobox.setMinimumWidth(150)
        self.area_combobox.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox:hover {
                border-color: #2D7DF6;
            }
        """)
        layout.addWidget(self.area_combobox)
        
        # 确认按钮
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7DF6;
                color: white;
                border: none;
                padding: 3px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1a6ad4;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self.confirm_btn)
        
        # 重置按钮
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 3px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self.reset_btn)
        
        layout.addStretch()
        
        self.setLayout(layout)
    
    def set_area_list(self, area_list):
        """设置区域列表"""
        self.area_list = area_list or []
        self._refresh_combobox()
    
    def _refresh_combobox(self):
        """刷新combobox"""
        self.area_combobox.clear()
        
        # 添加"全部区域"
        self.area_combobox.addItem("全部区域", "ALL")
        
        # 递归添加区域
        if self.area_list:
            self._add_area_to_combobox(self.area_list, "")
    
    def _add_area_to_combobox(self, area_list, parent_path):
        """递归添加区域到combobox"""
        for area in area_list:
            name = area.get('name', '')
            if not name:
                continue
            
            # 构建完整路径
            if parent_path:
                full_path = f"{parent_path}/{name}"
            else:
                full_path = name
            
            # 构建显示名称（带缩进）
            level = full_path.count('/') + 1
            indent = "  " * (level - 1)
            display_name = f"{indent}{name}"
            
            self.area_combobox.addItem(display_name, full_path)
            
            # 递归添加子区域
            children = area.get('children', [])
            if children:
                self._add_area_to_combobox(children, full_path)
    
    def _on_confirm(self):
        """确认按钮点击"""
        self.selected_area_path = self.area_combobox.currentData()
        area_name = self.area_combobox.currentText().strip()
        
        _log.info(f"图表[{self.chart_name}]选择区域: {self.selected_area_path}")
        self.area_confirmed.emit(self.chart_name, self.selected_area_path)
    
    def _on_reset(self):
        """重置按钮点击"""
        self.area_combobox.setCurrentIndex(0)  # 选中"全部区域"
        self.selected_area_path = "ALL"
        self.area_confirmed.emit(self.chart_name, "ALL")
    
    def get_selected_area(self):
        """获取当前选中的区域"""
        return self.selected_area_path
    
    def update_area_list(self, new_area_list):
        """更新区域列表（当设备管理界面增删改区域时调用）"""
        old_selected = self.selected_area_path
        
        # 刷新combobox
        self.area_list = new_area_list or []
        self._refresh_combobox()
        
        # 尝试恢复之前的选择
        if old_selected != "ALL":
            index = self.area_combobox.findData(old_selected)
            if index >= 0:
                # 区域还存在，恢复选择
                self.area_combobox.setCurrentIndex(index)
                self.selected_area_path = old_selected
            else:
                # 区域被删除，退回上一级
                parent_path = self._get_parent_path(old_selected)
                if parent_path:
                    index = self.area_combobox.findData(parent_path)
                    if index >= 0:
                        self.area_combobox.setCurrentIndex(index)
                        self.selected_area_path = parent_path
                        _log.info(f"区域[{old_selected}]已删除，退回到[{parent_path}]")
                        self.area_confirmed.emit(self.chart_name, parent_path)
                        return
                
                # 退回到全部区域
                self.area_combobox.setCurrentIndex(0)
                self.selected_area_path = "ALL"
                _log.info(f"区域[{old_selected}]已删除，退回到[全部区域]")
                self.area_confirmed.emit(self.chart_name, "ALL")
    
    def _get_parent_path(self, area_path):
        """获取父区域路径"""
        if '/' not in area_path:
            return None
        return area_path.rsplit('/', 1)[0]
    
    def rename_area(self, old_path, new_name):
        """区域重命名时更新"""
        # 重新加载区域列表
        self._refresh_combobox()
        
        # 如果当前选中的是被重命名的区域，更新选中
        if self.selected_area_path == old_path:
            parent_path = self._get_parent_path(old_path)
            if parent_path:
                new_path = f"{parent_path}/{new_name}"
            else:
                new_path = new_name
            
            self.selected_area_path = new_path
            index = self.area_combobox.findData(new_path)
            if index >= 0:
                self.area_combobox.setCurrentIndex(index)
