"""
图表区域管理模块
管理图表的区域树组件、区域选择、数据筛选等功能
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTreeWidget, QTreeWidgetItem, QGroupBox, QLabel,
                             QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from datetime import datetime
import json
import logging

_log = logging.getLogger(__name__)


class ChartAreaManager(QWidget):
    """图表区域管理器 - 为每个图表提供区域树和确认按钮"""
    
    # 信号：区域选择确认时发射
    area_confirmed = pyqtSignal(str, list)  # (chart_name, selected_areas)
    
    def __init__(self, chart_name, parent=None):
        super().__init__(parent)
        self.chart_name = chart_name
        self.current_user = None
        self.area_config = []
        self.selected_area_path = "ALL"  # 当前选中的区域路径
        self.area_tree_map = {}  # 区域路径到树节点的映射
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 区域树标题
        title_label = QLabel("区域筛选")
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        
        # 区域树
        self.area_tree = QTreeWidget()
        self.area_tree.setHeaderHidden(True)
        self.area_tree.setMaximumHeight(150)
        self.area_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QTreeWidget::item {
                padding: 2px;
            }
            QTreeWidget::item:selected {
                background-color: #2D7DF6;
                color: white;
            }
        """)
        # 启用多选
        self.area_tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.area_tree)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        # 确认按钮
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7DF6;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1a6ad4;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.confirm_btn)
        
        # 重置按钮
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(self.reset_btn)
        
        layout.addLayout(btn_layout)
        
        # 当前选择显示
        self.current_label = QLabel("当前: 全部区域")
        self.current_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.current_label)
        
        self.setLayout(layout)
    
    def set_current_user(self, username, area_config_json):
        """设置当前用户和区域配置"""
        self.current_user = username
        try:
            if isinstance(area_config_json, str):
                self.area_config = json.loads(area_config_json)
            else:
                self.area_config = area_config_json or []
        except Exception as e:
            _log.error(f"解析区域配置失败: {e}")
            self.area_config = []
        
        self._refresh_area_tree()
    
    def _refresh_area_tree(self):
        """刷新区域树"""
        self.area_tree.clear()
        self.area_tree_map = {}
        
        # 添加"全部区域"节点
        all_item = QTreeWidgetItem(self.area_tree)
        all_item.setText(0, "全部区域")
        all_item.setData(0, Qt.ItemDataRole.UserRole, "ALL")
        all_item.setSelected(True)  # 默认选中
        self.area_tree_map["ALL"] = all_item
        
        # 递归添加区域节点
        if self.area_config:
            self._add_area_nodes(self.area_tree, self.area_config, "")
        
        self.area_tree.expandAll()
    
    def _add_area_nodes(self, parent, area_list, parent_path):
        """递归添加区域节点"""
        for area in area_list:
            name = area.get('name', '')
            if not name:
                continue
            
            # 构建完整路径
            if parent_path:
                full_path = f"{parent_path}/{name}"
            else:
                full_path = name
            
            # 创建节点
            if isinstance(parent, QTreeWidget):
                item = QTreeWidgetItem(parent)
            else:
                item = QTreeWidgetItem(parent)
            
            item.setText(0, name)
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            self.area_tree_map[full_path] = item
            
            # 递归添加子区域
            children = area.get('children', [])
            if children:
                self._add_area_nodes(item, children, full_path)
    
    def _on_confirm(self):
        """确认按钮点击"""
        selected_items = self.area_tree.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "提示", "请至少选择一个区域")
            return
        
        # 获取选中的区域路径
        selected_areas = []
        for item in selected_items:
            area_path = item.data(0, Qt.ItemDataRole.UserRole)
            selected_areas.append(area_path)
        
        # 如果选了"全部区域"，忽略其他选择
        if "ALL" in selected_areas:
            selected_areas = ["ALL"]
            self.selected_area_path = "ALL"
            display_text = "全部区域"
        else:
            # 多个区域选择，用逗号分隔
            self.selected_area_path = selected_areas[0] if selected_areas else "ALL"
            display_text = ", ".join([path.split('/')[-1] for path in selected_areas[:3]])
            if len(selected_areas) > 3:
                display_text += f" 等{len(selected_areas)}个区域"
        
        self.current_label.setText(f"当前: {display_text}")
        
        # 发射信号
        self.area_confirmed.emit(self.chart_name, selected_areas)
        
        _log.info(f"图表[{self.chart_name}]选择区域: {selected_areas}")
    
    def _on_reset(self):
        """重置按钮点击"""
        self.area_tree.clearSelection()
        all_item = self.area_tree_map.get("ALL")
        if all_item:
            all_item.setSelected(True)
        self.selected_area_path = "ALL"
        self.current_label.setText("当前: 全部区域")
        self.area_confirmed.emit(self.chart_name, ["ALL"])
    
    def get_selected_area(self):
        """获取当前选中的区域"""
        return self.selected_area_path
    
    def update_area_config(self, new_config_json):
        """更新区域配置（当设备管理界面增删改区域时调用）"""
        try:
            if isinstance(new_config_json, str):
                new_config = json.loads(new_config_json)
            else:
                new_config = new_config_json or []
        except Exception as e:
            _log.error(f"解析新区域配置失败: {e}")
            return
        
        # 检查之前选中的区域是否还存在
        old_selected = self.selected_area_path
        
        # 刷新区域树
        self.area_config = new_config
        self._refresh_area_tree()
        
        # 处理选中区域的变更
        if old_selected != "ALL":
            if old_selected in self.area_tree_map:
                # 区域还存在，保持选中
                item = self.area_tree_map[old_selected]
                item.setSelected(True)
                self.current_label.setText(f"当前: {old_selected.split('/')[-1]}")
            else:
                # 区域被删除，退回上一级
                parent_path = self._get_parent_path(old_selected)
                if parent_path and parent_path in self.area_tree_map:
                    self.selected_area_path = parent_path
                    item = self.area_tree_map[parent_path]
                    item.setSelected(True)
                    self.current_label.setText(f"当前: {parent_path.split('/')[-1]} (子区域已删除)")
                    _log.info(f"区域[{old_selected}]已删除，退回到[{parent_path}]")
                else:
                    # 退回全部区域
                    self.selected_area_path = "ALL"
                    all_item = self.area_tree_map.get("ALL")
                    if all_item:
                        all_item.setSelected(True)
                    self.current_label.setText("当前: 全部区域 (原区域已删除)")
                    _log.info(f"区域[{old_selected}]已删除，退回到[全部区域]")
                
                # 触发数据更新
                self.area_confirmed.emit(self.chart_name, [self.selected_area_path])
    
    def _get_parent_path(self, area_path):
        """获取父区域路径"""
        if '/' not in area_path:
            return None
        return area_path.rsplit('/', 1)[0]
    
    def rename_area(self, old_path, new_name):
        """区域重命名时更新"""
        if old_path in self.area_tree_map:
            item = self.area_tree_map[old_path]
            
            # 获取新路径
            parent_path = self._get_parent_path(old_path)
            if parent_path:
                new_path = f"{parent_path}/{new_name}"
            else:
                new_path = new_name
            
            # 更新节点文本和数据
            item.setText(0, new_name)
            item.setData(0, Qt.ItemDataRole.UserRole, new_path)
            
            # 更新映射
            del self.area_tree_map[old_path]
            self.area_tree_map[new_path] = item
            
            # 如果当前选中的是这个区域，更新选中路径
            if self.selected_area_path == old_path:
                self.selected_area_path = new_path
                self.current_label.setText(f"当前: {new_name}")
                self.area_confirmed.emit(self.chart_name, [new_path])
            
            _log.info(f"区域重命名: {old_path} -> {new_path}")
