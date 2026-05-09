from math import e
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QStandardItemModel, QStandardItem,QColor,QPainter,QBrush,QPen,QFont
from PyQt6.QtCore import pyqtSignal,QSortFilterProxyModel,QRect,QPoint,Qt,QEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib
import matplotlib.dates as mdates
from datetime import datetime

# 设置matplotlib中文字体
matplotlib.rcParams['font.family'] = ['SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# 导入日志
from log_save import Logger
_log = Logger(True).logger

# ==============================
# 自定义 TreeView 控件：独立封装:区域划分树
# ==============================
class AreaTreeView(QTreeView):
    signal_area_change = pyqtSignal() # 区域被更改信号
    signal_area_renamed = pyqtSignal(str, str, int) # 区域重命名信号(旧名称, 新名称, 级别)
    def __init__(self, parent=None):
        super().__init__(parent)
        # 模型
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["区域"])
        self.setModel(self.model)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        self.setStyleSheet("""
            QTreeView::item:selected {
                background-color: #90EE90;  /* 浅绿色 */
                color: black;
            }
        """)

        # 固定一级根节点
        self.root_item = QStandardItem("区域划分")
        self.model.appendRow(self.root_item)
        self.expandAll()

    # 获取当前项 & 层级
    def get_current_item_level(self):
        index = self.currentIndex()
        if not index.isValid():
            return None, 0

        item = self.model.itemFromIndex(index)
        level = 1
        p = item
        while p.parent():
            level += 1
            p = p.parent()
        return item, level

    # 新增下级（外部按钮调用）
    def add_child(self):
        item, level = self.get_current_item_level()
        if not item:
            QMessageBox.warning(self, "提示", "请选择节点")
            return

        if level >= 4:
            QMessageBox.warning(self, "提示", "已到4级，无法继续新增")
            return

        name, ok = QInputDialog.getText(self, f"新增{level}级区域", "名称：")
        if ok and name.strip():
            child_item = QStandardItem(name.strip())
            child_item.setData({"area_name": name.strip(), "type": "未知", "coords": []}, Qt.ItemDataRole.UserRole)  # 绑定区域属性
            item.appendRow(child_item)
            self.expand(item.index())
            self.signal_area_change.emit()

    # 编辑（外部按钮调用）
    def edit_current(self):
        item, level = self.get_current_item_level()
        if not item:
            QMessageBox.warning(self, "提示", "请选择节点")
            return
        if level == 1:
            QMessageBox.warning(self, "提示", "区域划分不可编辑")
            return

        old_name = item.text()
        name, ok = QInputDialog.getText(self, "编辑", "新名称：", text=old_name)
        if ok and name.strip():
            new_name = name.strip()
            item.setText(new_name)
            # 获取现有区域属性，更新名称
            area_data = item.data(Qt.ItemDataRole.UserRole) or {}
            area_data["area_name"] = new_name
            item.setData(area_data, Qt.ItemDataRole.UserRole)
            # 发送重命名信号
            self.signal_area_renamed.emit(old_name, new_name, level)
            self.signal_area_change.emit()

    # 删除（外部按钮调用）
    def delete_current(self):
        item, level = self.get_current_item_level()
        if not item:
            QMessageBox.warning(self, "提示", "请选择节点")
            return
        if level == 1:
            QMessageBox.warning(self, "提示", "区域划分不可删除")
            return

        parent = item.parent()
        if parent:
            parent.removeRow(item.row())
            self.signal_area_change.emit()

    # 获取所有 二、三、四级区域（返回结构化数据）
    def get_all_sub_areas(self):
        """
        获取所有二级、三级、四级区域
        返回格式：
        [
            {
                "level": 1,
                "name": "xxx",
                "area": {
                    "area_name": "xxx", "type": "未知", "coords": [], "image_path": "", "path": ""},
                "children": [
                    {
                        "level": 2,
                        "name": "yyy",
                        "area": {"area_name": "yyy", "type": "未知", "coords": []},
                        "children": [{"level": 3, "name": "zzz", "area": {"area_name": "zzz", "type": "未知", "coords": []}}]
                    }
                ]
            }
        ]
        """
        result = []

        # 遍历二级区域（一级区域）
        for row in range(self.root_item.rowCount()):
            level2_item = self.root_item.child(row)
            if not level2_item:
                continue

            # 从节点数据中获取区域属性，如果没有则使用默认值
            level2_area = level2_item.data(Qt.ItemDataRole.UserRole) or {}
            _log.debug(f"get_all_sub_areas: 一级区域 '{level2_item.text()}' 的节点数据: {level2_area}")
            level2_data = {
                "level": 1,
                "name": level2_item.text(),
                "area": {
                    "area_name": level2_area.get("area_name", level2_item.text()),
                    "type": level2_area.get("type", "未知"),
                    "coords": level2_area.get("coords", []),
                    "image_path": level2_area.get("image_path", ""),
                    "path": level2_area.get("path", "")
                },
                "children": []
            }

            # 遍历三级区域（二级区域）
            for r2 in range(level2_item.rowCount()):
                level3_item = level2_item.child(r2)
                if not level3_item:
                    continue

                # 从节点数据中获取区域属性，如果没有则使用默认值
                level3_area = level3_item.data(Qt.ItemDataRole.UserRole) or {}
                level3_data = {
                    "level": 2,
                    "name": level3_item.text(),
                    "area": {
                        "area_name": level3_area.get("area_name", level3_item.text()),
                        "type": level3_area.get("type", "未知"),
                        "coords": level3_area.get("coords", [])
                    },
                    "children": []
                }

                # 遍历四级区域（三级区域）
                for r3 in range(level3_item.rowCount()):
                    level4_item = level3_item.child(r3)
                    if level4_item:
                        # 从节点数据中获取区域属性，如果没有则使用默认值
                        level4_area = level4_item.data(Qt.ItemDataRole.UserRole) or {}
                        level3_data["children"].append({
                            "level": 3,
                            "name": level4_item.text(),
                            "area": {
                                "area_name": level4_area.get("area_name", level4_item.text()),
                                "type": level4_area.get("type", "未知"),
                                "coords": level4_area.get("coords", [])
                            }
                        })

                level2_data["children"].append(level3_data)
            result.append(level2_data)

        return result

    def treeview_init(self, area_list):
        """
        根据get_all_sub_areas返回的列表重新添加至TreeView中
        :param area_list: get_all_sub_areas返回的列表，格式如:
            [
                {
                    "level": 1,
                    "name": "xxx",
                    "area": {"area_name": "xxx", "type": "未知", "coords": []},
                    "children": [
                        {
                            "level": 2,
                            "name": "yyy",
                            "area": {"area_name": "yyy", "type": "未知", "coords": []},
                            "children": [{"level": 3, "name": "zzz", "area": {"area_name": "zzz", "type": "未知", "coords": []}}]
                        }
                    ]
                }
            ]
        """
        # 清除现有的所有二级及以下节点
        while self.root_item.rowCount() > 0:
            self.root_item.removeRow(0)

        # 遍历传入的列表，添加节点
        for level2_data in area_list:
            # 创建二级区域节点
            level2_item = QStandardItem(level2_data.get("name", ""))
            level2_item.setData(level2_data.get("area", {}), Qt.ItemDataRole.UserRole)  # 绑定区域属性
            self.root_item.appendRow(level2_item)

            # 添加三级区域节点
            for level3_data in level2_data.get("children", []):
                level3_item = QStandardItem(level3_data.get("name", ""))
                level3_item.setData(level3_data.get("area", {}), Qt.ItemDataRole.UserRole)  # 绑定区域属性
                level2_item.appendRow(level3_item)

                # 添加四级区域节点
                for level4_data in level3_data.get("children", []):
                    level4_item = QStandardItem(level4_data.get("name", ""))
                    level4_item.setData(level4_data.get("area", {}), Qt.ItemDataRole.UserRole)  # 绑定区域属性
                    level3_item.appendRow(level4_item)

        # 展开所有节点
        self.expandAll()





# ==============================
# 自定义 TableView 控件：独立封装:多设备展示表
# ==============================
class MyTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # self.setItemDelegateForColumn(0, CheckBoxDelegate(self))  # 勾选
        # self.setItemDelegateForColumn(22, OptimizedButtonDelegate(self,button_column=22))  # 历史数据
        # self.clicked.connect(self.on_cell_clicked)

        self.last_found_row = -1  # 保存最后查找的行，用于重置颜色

    def set_item_delegate(self, column, delegate):
        self.setItemDelegateForColumn(column, delegate)

# ==============================
# 自定义排序代理模型：独立封装:设备配置表格排序
# 支持三级排序：升序 -> 降序 -> 恢复默认
# ==============================
class ConfigurableSortProxy(QSortFilterProxyModel):
    def __init__(self, number_columns=None, date_columns=None, parent=None):
        super().__init__(parent)
        # 数字列名列表，默认为空
        self.number_columns = number_columns if number_columns else []
        # 日期列名列表，默认为空
        self.date_columns = date_columns if date_columns else []
        # 自定义过滤行集合
        self._filter_rows = None
        # 排序状态管理：记录每列的排序状态 0:默认, 1:升序, 2:降序
        self._sort_states = {}
        # 当前排序列
        self._current_sort_column = -1
        # 是否使用默认顺序（不排序）
        self._use_default_order = True

    def set_filter_rows(self, rows):
        """设置允许显示的行集合，None表示显示所有行"""
        self._filter_rows = rows
        self.invalidateFilter()

    def clear_filter_rows(self):
        """清除行过滤"""
        self._filter_rows = None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        """自定义行过滤"""
        # 如果有自定义行过滤集合，检查当前行是否在集合中
        if self._filter_rows is not None:
            return source_row in self._filter_rows
        # 否则使用默认的过滤逻辑
        return super().filterAcceptsRow(source_row, source_parent)

    def sort(self, column, order=None):
        """重写排序方法，实现三级排序：升序 -> 降序 -> 恢复默认"""
        if column < 0:
            super().sort(column, order)
            return

        # 获取当前列的排序状态
        current_state = self._sort_states.get(column, 0)

        # 如果点击的是新列，重置之前列的状态
        if column != self._current_sort_column and self._current_sort_column >= 0:
            self._sort_states[self._current_sort_column] = 0

        # 循环切换状态：0(默认) -> 1(升序) -> 2(降序) -> 0(默认)
        new_state = (current_state + 1) % 3
        self._sort_states[column] = new_state
        self._current_sort_column = column

        if new_state == 0:
            # 恢复默认排序：使用源模型原始顺序
            self._use_default_order = True
            self._current_sort_column = -1
            # 触发重新排序，使用默认顺序
            # 调用 sort 并传入当前列，让 lessThan 接管排序
            super().sort(column, Qt.SortOrder.AscendingOrder)
        elif new_state == 1:
            # 升序
            self._use_default_order = False
            super().sort(column, Qt.SortOrder.AscendingOrder)
        else:
            # 降序
            self._use_default_order = False
            super().sort(column, Qt.SortOrder.DescendingOrder)

    def _clear_sort_indicator(self):
        """清除排序指示器（需要在视图中调用）"""
        # 发送信号通知视图清除排序指示器
        self.layoutChanged.emit()

    def get_sort_state(self, column):
        """获取指定列的排序状态：0=默认, 1=升序, 2=降序"""
        return self._sort_states.get(column, 0)

    def lessThan(self, left_index, right_index):
        # 如果使用默认顺序，按源模型行号比较（保持原始顺序）
        # 注意：lessThan 接收的索引是源模型的索引（QModelIndex）
        # 返回 True 表示 left 应该排在 right 前面
        if self._use_default_order:
            # left_index 和 right_index 已经是源模型的索引
            # 直接比较行号即可保持原始顺序
            return left_index.row() < right_index.row()

        # 获取列标题名称
        left_col_name = self.sourceModel().headerData(left_index.column(), Qt.Orientation.Horizontal)
        # 数字列排序
        if left_col_name in self.number_columns:
            try:
                left_data = float(self.sourceModel().data(left_index))
                right_data = float(self.sourceModel().data(right_index))
                return left_data < right_data
            except (ValueError, TypeError):
                pass

        # 日期列排序
        if left_col_name in self.date_columns:
            try:
                left_date_str = self.sourceModel().data(left_index)
                right_date_str = self.sourceModel().data(right_index)

                left_date = datetime.strptime(left_date_str, "%Y-%m-%d %H:%M:%S")
                right_date = datetime.strptime(right_date_str, "%Y-%m-%d %H:%M:%S")

                return left_date < right_date
            except (ValueError, TypeError):
                pass

        # 其他列使用默认比较
        return super().lessThan(left_index, right_index)


# ==============================
# 自定义按钮代理：独立封装:设备配置表格按钮代理
# ==============================
class OptimizedButtonDelegate(QStyledItemDelegate):
    """优化的按钮代理，通过绘制实现按钮，而非创建Widget"""
    signal_button_click = pyqtSignal(object)
    def __init__(self, button_column,text, parent=None):
        super().__init__(parent)
        self.button_column = button_column
        self.hover_index = None  # 跟踪鼠标悬停的索引
        self.button_text = text
        # 按钮样式配置
        self.normal_bg = QColor(76, 175, 80)  # #4CAF50
        self.hover_bg = QColor(69, 160, 73)  # #45a049
        self.text_color = QColor(255, 255, 255)  # 白色
        self.border_radius = 4

    def paint(self, painter, option, index):
        """直接绘制按钮，不创建Widget"""
        if index.column() != self.button_column:
            super().paint(painter, option, index)
            return

        # 绘制按钮背景
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 抗锯齿

        # 确定按钮颜色（是否悬停）
        bg_color = self.hover_bg if (self.hover_index == index) else self.normal_bg

        # 绘制按钮圆角矩形
        rect = option.rect.adjusted(4, 4, -4, -4)  # 边距
        painter.fillRect(rect, bg_color)
        painter.setPen(Qt.PenStyle.NoPen)

        # 绘制按钮文本
        painter.setPen(QPen(self.text_color))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)

        # 文本居中
        text_rect = painter.boundingRect(rect, Qt.AlignmentFlag.AlignCenter, self.button_text)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.button_text)

        painter.restore()

    def sizeHint(self, option, index):
        """按钮尺寸提示"""
        if index.column() == self.button_column:
            return QRect(0, 0, 80, 30).size()  # 固定按钮大小
        return super().sizeHint(option, index)

    def editorEvent(self, event, model, option, index):
        """处理鼠标事件"""
        if index.column() != self.button_column:
            return super().editorEvent(event, model, option, index)

        # 鼠标释放事件 - 处理点击
        if event.type() == QEvent.Type.MouseButtonRelease:
            if option.rect.contains(event.pos()):
                # 点击事件 - 发送信号通知主窗口处理
                self.signal_button_click.emit(index)
                return True

        return False


# ==============================
# 自定义复选框代理：独立封装:多设备展示表复选框代理
# ==============================
class CheckBoxDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        # 计算复选框大小并确保为整数
        box_size = int(min(rect.width(), rect.height()) - 12)
        if box_size < 12:
            box_size = 12

        # 计算居中位置（确保为整数坐标）
        center_x = rect.center().x()
        center_y = rect.center().y()
        box_rect = QRect(
            center_x - box_size // 2,
            center_y - box_size // 2,
            box_size,
            box_size
        )

        # 绘制背景
        if option.state & QStyle.StateFlag.State_Enabled:
            bg_color = QColor(255, 255, 255)
        else:
            bg_color = QColor(240, 240, 240)
        painter.fillRect(box_rect, QBrush(bg_color))

        # 绘制边框
        border_pen = QPen(QColor(180, 180, 180), 2)
        painter.setPen(border_pen)
        painter.drawRect(box_rect)

        # 绘制勾选标记（修复坐标类型错误）
        try:
            if index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked:
                # 设置√符号的字体
                font = QFont()
                font.setFamily("SimHei")  # 使用黑体确保√符号显示正常
                font.setPointSize(box_size // 2)  # 根据复选框大小调整字体
                font.setBold(True)
                painter.setFont(font)

                # 设置√符号颜色
                painter.setPen(QPen(QColor(49, 132, 253), 2))

                # 计算√符号位置（居中显示）
                text_rect = box_rect.adjusted(1, 1, -1, -1)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "√")

        except Exception as e:
            print(f"绘制勾选标记时出错: {e}")

        painter.restore()

    def editorEvent(self, event, model, option, index):
        # 仅当点击在复选框区域内才响应
        if event.type() == QEvent.Type.MouseButtonRelease and option.rect.contains(event.pos()):
            try:
                current_state = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
            except Exception as e:
                print(f"处理点击事件时出错: {e}")
                return False
        return super().editorEvent(event, model, option, index)


# ==============================
# 自定义24小时功率折线图：显示144个数据点（24小时*6），X轴显示24个时间标签
# ==============================
class Power24hCanvas(FigureCanvas):
    """24小时功率折线图 - 显示144个10分钟间隔数据点，X轴显示24个小时标签"""
    
    def __init__(self, x_list, y_list, parent=None):
        self.fig = Figure(figsize=(10, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        # 修复边距，确保X轴标签显示完整
        self.fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.15)
        
        super().__init__(self.fig)
        
        # 存储数据（144个点）
        self.x_data = x_list if x_list else []
        self.y_data = y_list if y_list else []
        
        # 画线（所有数据点）
        self.line, = self.ax.plot(
            range(len(self.x_data)),  # 使用数字索引作为X轴（0-143）
            self.y_data,
            linestyle='-',
            color='#2D7DF6',
            linewidth=2,
            marker='o',
            markersize=3
        )
        
        # 自动计算Y轴范围
        if self.y_data and max(self.y_data) > 0:
            max_y = max(self.y_data) * 1.1
            self.ax.set_ylim(0, max_y)
        else:
            self.ax.set_ylim(0, 1)
        
        # X轴设置：只显示24个小时标签（每6个点显示一个，即每小时）
        self._setup_x_axis()
        
        # 网格和样式
        self.ax.grid(alpha=0.3)
        # self.ax.set_xlabel('时间', fontsize=10)
        # self.ax.set_ylabel('功率 (W)', fontsize=10)
        
        # 鼠标悬浮提示框
        self.tooltip = None
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
    
    def _setup_x_axis(self):
        """设置X轴：显示24个小时标签"""
        if not self.x_data:
            return
        
        # 计算要显示的刻度位置（每6个点显示一个，即每小时）
        total_points = len(self.x_data)
        tick_positions = list(range(0, total_points, 6))  # 0, 6, 12, 18, ...
        
        # 确保最后一个点也被包含
        if tick_positions[-1] != total_points - 1:
            tick_positions.append(total_points - 1)
        
        # 获取对应的标签（只取小时部分）
        tick_labels = []
        for pos in tick_positions:
            if pos < len(self.x_data):
                time_str = self.x_data[pos]
                # 提取小时部分（格式如 "13:20" -> "13"）
                if ':' in time_str:
                    hour = time_str.split(':')[0]
                    tick_labels.append(f"{hour}:00")
                else:
                    tick_labels.append(time_str)
            else:
                tick_labels.append('')
        
        # 设置X轴刻度和标签
        self.ax.set_xticks(tick_positions)
        self.ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)
        
        # 设置X轴范围
        self.ax.set_xlim(-0.5, total_points - 0.5)
    
    def on_mouse_move(self, event):
        """鼠标移动事件处理：显示悬浮提示框"""
        if event.inaxes != self.ax:
            self._hide_tooltip()
            return
        
        # 检查数据是否有效
        if not self.x_data or not self.y_data or len(self.x_data) != len(self.y_data):
            self._hide_tooltip()
            return
        
        # 查找最近的点（基于X轴索引）
        min_dist = float('inf')
        nearest_idx = -1
        
        for i in range(len(self.x_data)):
            # 将数据坐标转换为显示坐标
            try:
                y_val = float(self.y_data[i])
            except (ValueError, TypeError):
                continue
            x_display, y_display = self.ax.transData.transform((i, y_val))
            # 计算鼠标到点的距离
            dist = ((event.x - x_display) ** 2 + (event.y - y_display) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        
        # 如果距离小于阈值（20像素），显示提示框
        if nearest_idx >= 0 and min_dist < 20:
            self._show_tooltip(nearest_idx, event.x, event.y)
        else:
            self._hide_tooltip()
    
    def _show_tooltip(self, idx, mouse_x, mouse_y):
        """显示提示框"""
        x_val = self.x_data[idx]
        y_val = self.y_data[idx]
        
        # 格式化显示文本
        try:
            y_num = float(y_val)
            y_str = f'{y_num:.0f}'
        except (ValueError, TypeError):
            y_str = str(y_val)
        
        # 隐藏之前的提示框
        self._hide_tooltip()
        
        # 获取当前点的显示位置
        try:
            y_num = float(y_val)
        except (ValueError, TypeError):
            return
        x_display, y_display = self.ax.transData.transform((idx, y_num))
        
        # 获取图表尺寸
        bbox = self.ax.get_window_extent()
        width = bbox.width
        height = bbox.height
        
        # 计算偏移量（避免超出边界）
        x_offset = 10
        y_offset = 15
        if x_display > width * 0.7:
            x_offset = -80
        if y_display > height * 0.7:
            y_offset = -40
        
        # 创建新的提示框
        self.tooltip = self.ax.annotate(
            f'时间: {x_val}\n功率: {y_str} W',
            xy=(idx, y_num),
            xytext=(x_offset, y_offset),
            textcoords='offset points',
            bbox=dict(
                boxstyle='round,pad=0.5',
                facecolor='yellow',
                edgecolor='black',
                alpha=0.9
            ),
            fontsize=9,
            arrowprops=dict(
                arrowstyle='->',
                connectionstyle='arc3,rad=0',
                color='black'
            )
        )
        self.fig.canvas.draw_idle()
    
    def _hide_tooltip(self):
        """隐藏提示框"""
        if self.tooltip is not None:
            self.tooltip.remove()
            self.tooltip = None
            self.fig.canvas.draw_idle()
    
    def update_data(self, x_list, y_list):
        """更新数据"""
        try:
            _ = self.fig
        except RuntimeError:
            return
        
        # 检查数据有效性
        if not x_list or not y_list or len(x_list) == 0 or len(y_list) == 0:
            self.x_data = []
            self.y_data = []
            self.line.set_data([], [])
            self.ax.set_ylim(0, 1)
            self.draw()
            return
        
        # 过滤无效值
        import numpy as np
        valid_data = [(x, y) for x, y in zip(x_list, y_list)
                      if y is not None and not np.isnan(y) and not np.isinf(y)]
        
        if not valid_data:
            self.x_data = []
            self.y_data = []
            self.line.set_data([], [])
            self.ax.set_ylim(0, 1)
            self.draw()
            return
        
        self.x_data = [d[0] for d in valid_data]
        self.y_data = [d[1] for d in valid_data]
        
        # 更新线条数据（使用数字索引）
        self.line.set_data(range(len(self.y_data)), self.y_data)
        
        # 更新Y轴范围
        if self.y_data and max(self.y_data) > 0:
            max_y = max(self.y_data) * 1.1
            self.ax.set_ylim(0, max_y)
        else:
            self.ax.set_ylim(0, 1)
        
        # 更新X轴刻度和标签（只显示24个小时标签）
        self._setup_x_axis()
        
        # 调整布局以适应新标签
        self.fig.tight_layout()
        
        self.draw()


# ==============================
# 自定义折线图：独立封装:在线率图表折线图代理
# ==============================
class BrokenLineCanvas(FigureCanvas):
    def __init__(self, x_list, y_list, parent=None):
        self.fig = Figure(figsize=(10, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)

        # 修复边距，Y轴显示完整
        self.fig.subplots_adjust(left=0.12, right=0.95, top=0.9, bottom=0.2)

        super().__init__(self.fig)

        # 初始化x_list个点
        # 将字符串格式的日期转换为datetime对象
        if x_list and isinstance(x_list[0], str):
            try:
                self.x_data = [datetime.strptime(date_str, '%Y-%m-%d') for date_str in x_list]
            except ValueError:
                # 如果转换失败，使用原始数据
                self.x_data = x_list
        else:
            self.x_data = x_list
        # print(self.x_data)
        self.y_data = y_list

        # 画线
        self.line, = self.ax.plot(
            self.x_data, self.y_data,
            linestyle='-',
            color='#2D7DF6',
            linewidth=2,
            marker='o',
            markersize=4
        )
        # 自动计算Y轴范围：从0开始，上限自适应数据
        max_y = max(self.y_data) * 1.1  # 比最大值大10%，更美观
        if max_y > 0:
            self.ax.set_ylim(0, max_y)      # 强制底部0，顶部自适应
        else:
            self.ax.set_ylim(0, 1)


        # X轴时间格式
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y\n%m-%d'))

        # self.ax.set_title("设备实时数据曲线", fontsize=14)
        # self.ax.set_xlabel("时间", fontsize=12)
        # self.ax.set_ylabel("数值", fontsize=12)
        self.ax.grid(alpha=0.3)
        self.ax.tick_params(axis='x', labelsize=10)

        # 鼠标悬浮提示框
        self.tooltip = None
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)

    def on_mouse_move(self, event):
        """鼠标移动事件处理：显示悬浮提示框"""
        if event.inaxes != self.ax:
            self._hide_tooltip()
            return

        # 检查数据是否有效
        if not self.x_data or not self.y_data or len(self.x_data) != len(self.y_data):
            self._hide_tooltip()
            return

        # 查找最近的点
        min_dist = float('inf')
        nearest_idx = -1

        for i, (x, y) in enumerate(zip(self.x_data, self.y_data)):
            # 将datetime转换为matplotlib日期数字格式
            if hasattr(x, 'strftime'):
                x_num = mdates.date2num(x)
            else:
                x_num = x
            
            # 确保y是数值类型
            try:
                y_num = float(y)
            except (ValueError, TypeError):
                continue  # 跳过非数值数据
            
            # 将数据坐标转换为显示坐标
            x_display, y_display = self.ax.transData.transform((x_num, y_num))
            # 计算鼠标到点的距离
            dist = ((event.x - x_display) ** 2 + (event.y - y_display) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i

        # 如果距离小于阈值（20像素），显示提示框
        if nearest_idx >= 0 and min_dist < 20:
            self._show_tooltip(nearest_idx, event.x, event.y)
        else:
            self._hide_tooltip()

    def _show_tooltip(self, idx, mouse_x, mouse_y):
        """显示提示框（自动调整位置避免超出边界）"""
        x_val = self.x_data[idx]
        y_val = self.y_data[idx]

        # 格式化显示文本
        if hasattr(x_val, 'strftime'):
            x_str = x_val.strftime('%Y-%m-%d')
        else:
            x_str = str(x_val)

        # 移除旧的提示框
        self._hide_tooltip()

        # 获取图表边界（像素坐标）
        bbox = self.ax.get_window_extent()
        width = bbox.width
        height = bbox.height

        # 计算数据点在屏幕上的位置
        if hasattr(x_val, 'strftime'):
            x_num = mdates.date2num(x_val)
        else:
            x_num = x_val
        x_display, y_display = self.ax.transData.transform((x_num, y_val))

        # 根据点的位置决定提示框偏移方向
        # 默认向右上方显示，如果靠近右边界则向左显示，靠近上边界则向下显示
        x_offset = 15
        y_offset = 15
        if x_display > width * 0.7:  # 靠近右边界
            x_offset = -80
        if y_display > height * 0.7:  # 靠近上边界
            y_offset = -40

        # 创建新的提示框
        self.tooltip = self.ax.annotate(
            f'时间: {x_str}\n数值: {y_val:.2f}',
            xy=(x_val, y_val),
            xytext=(x_offset, y_offset),
            textcoords='offset points',
            bbox=dict(
                boxstyle='round,pad=0.5',
                facecolor='yellow',
                edgecolor='black',
                alpha=0.9
            ),
            fontsize=9,
            arrowprops=dict(
                arrowstyle='->',
                connectionstyle='arc3,rad=0',
                color='black'
            )
        )
        self.fig.canvas.draw_idle()

    def _hide_tooltip(self):
        """隐藏提示框"""
        if self.tooltip is not None:
            self.tooltip.remove()
            self.tooltip = None
            self.fig.canvas.draw_idle()

    def update_data(self,x_list,y_list):
        # 检查对象是否已被删除
        try:
            # 尝试访问 self 的属性，如果对象被删除会抛出 RuntimeError
            _ = self.fig
        except RuntimeError:
            return

        # 检查数据有效性
        if not x_list or not y_list or len(x_list) == 0 or len(y_list) == 0:
            # 数据为空，显示空图表
            self.x_data = []
            self.y_data = []
            self.line.set_data([], [])
            self.ax.set_ylim(0, 1)
            self.draw()
            return

        # 过滤掉无效值（NaN, Inf）
        import numpy as np
        valid_data = [(x, y) for x, y in zip(x_list, y_list) 
                      if y is not None and not np.isnan(y) and not np.isinf(y)]
        
        if not valid_data:
            # 没有有效数据
            self.x_data = []
            self.y_data = []
            self.line.set_data([], [])
            self.ax.set_ylim(0, 1)
            self.draw()
            return

        x_list = [d[0] for d in valid_data]
        y_list = [d[1] for d in valid_data]

        # 新数据（你可以换成数据库读取）
        # 将字符串格式的日期转换为datetime对象
        if x_list and isinstance(x_list[0], str):
            try:
                self.x_data = [datetime.strptime(date_str, '%Y-%m-%d') for date_str in x_list]
            except ValueError:
                # 如果转换失败，使用原始数据
                self.x_data = x_list
        else:
            self.x_data = x_list
        self.y_data = y_list

        # 刷新
        self.line.set_data(self.x_data, self.y_data)
        # 只有当x_data是datetime对象时才设置日期格式化器
        if self.x_data and hasattr(self.x_data[0], 'strftime'):
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y\n%m-%d'))
        self.ax.relim()
        # 自动计算Y轴范围：从0开始，上限自适应数据
        if self.y_data:
            max_y = max(self.y_data) * 1.1  # 比最大值大10%，更美观
            if max_y > 0:
                self.ax.set_ylim(0, max_y)      # 强制底部0，顶部自适应
            else:
                self.ax.set_ylim(0, 1)
        else:
            self.ax.set_ylim(0, 1)
        self.ax.autoscale_view()
        self.draw()

class PieCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)

        # 初始数据
        labels = ['在线', '离线']
        sizes = [0, 100]
        colors = ['#4CAF50', '#F44336']
        explode = (0.1, 0)

        # 绘制饼图
        self.pie = self.ax.pie(
            sizes, explode=explode, labels=labels, colors=colors,
            autopct='%1.1f%%', shadow=True, startangle=90
        )

        # self.ax.set_title('实时在线率', fontsize=14)
        self.fig.tight_layout()

    def update_data(self, online_percent, offline_percent):
        # 检查对象是否已被删除
        try:
            _ = self.fig
        except RuntimeError:
            return

        # 清除当前图表
        self.ax.clear()

        # 新数据
        labels = ['在线', '离线']
        sizes = [online_percent, offline_percent]
        colors = ['#4CAF50', '#F44336']
        explode = (0.1, 0)

        # 检查数据有效性：如果总和为0，显示空状态
        total = sum(sizes)
        if total == 0:
            # 显示无数据状态
            sizes = [0, 1]  # 显示全部离线
            colors = ['#E0E0E0', '#F44336']
            autopct_fmt = lambda pct: '无数据' if pct > 50 else ''
        else:
            autopct_fmt = '%1.1f%%'

        # 重新绘制饼图
        try:
            self.pie = self.ax.pie(
                sizes, explode=explode, labels=labels, colors=colors,
                autopct=autopct_fmt, shadow=True, startangle=90
            )
        except Exception as e:
            print(f"绘制饼图失败: {e}")
            return

        # self.ax.set_title('实时在线率', fontsize=14)
        self.fig.tight_layout()
        self.draw()

class DateTimeTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        # 将单元格文本转换为 datetime 对象
        try:
            self_dt = datetime.datetime.strptime(self.text(), "%Y-%m-%d %H:%M:%S")
            other_dt = datetime.datetime.strptime(other.text(), "%Y-%m-%d %H:%M:%S")
            return self_dt < other_dt  # 按 datetime 比较
        except ValueError:
            # 转换失败时用默认字符串比较
            return super().__lt__(other)


class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        # 尝试将单元格内容转换为浮点数进行比较
        try:
            return float(self.text()) < float(other.text())
        except ValueError:
            # 如果转换失败，使用默认的字符串比较
            return super().__lt__(other)



class MplCanvas(FigureCanvas):
    """ 带滚轮缩放和鼠标悬停提示的matplotlib画布类 """

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super(MplCanvas, self).__init__(self.fig)
        self.setParent(parent)
        self.fig.tight_layout()

        # 存储绘图数据
        self.raw_data = {}  # {标签: (x数据, y数据, x_num)}
        self.pixel_cache = {}  # 缓存像素坐标
        self.data_processed = False  # 标记数据是否已预处理

        # 创建提示框
        self.tooltip = self.fig.text(0.5, 0.5, '',
                                     bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.9),
                                     fontsize=9)
        self.tooltip.set_visible(False)

        # 连接鼠标事件
        self.cid_motion = self.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.cid_leave = self.mpl_connect('figure_leave_event', self.on_leave_figure)
        self.cid_draw = self.mpl_connect('draw_event', self.on_draw)  # 绘图后更新缓存
        # 新增滚轮事件处理
        self.cid_scroll = self.mpl_connect('scroll_event', self.on_scroll)
        # 检测参数
        self.distance_threshold = 5  # 像素距离阈值
        self.last_closest = None  # 上一次的最近点
        self.transform = None  # 坐标转换对象
        self.update_counter = 0  # 控制更新频率
        self.zoom_factor = 1.1  # 缩放因子


        # 启用缩放功能
        self.axes.set_navigate(True)
        self.axes.set_navigate_mode('zoom')

    def preprocess_data(self):
        """ 预处理数据，缓存像素坐标 """
        if not self.raw_data or self.data_processed:
            return

        # 缓存像素坐标
        self.update_pixel_cache()
        self.data_processed = True

    def update_pixel_cache(self):
        """ 更新像素坐标缓存，缩放后会自动更新 """
        if not self.raw_data or not self.transform:
            return

        self.pixel_cache.clear()
        for label, (x_data, y_data, x_num) in self.raw_data.items():
            coords = np.column_stack((x_num, y_data))
            self.pixel_cache[label] = self.transform.transform(coords)

    def on_draw(self, event):
        """ 绘图或缩放后更新坐标转换和缓存 """
        self.transform = self.axes.transData
        self.update_pixel_cache()

    def on_leave_figure(self, event):
        """ 鼠标离开图表时隐藏提示 """
        if self.tooltip.get_visible():
            self.tooltip.set_visible(False)
            self.last_closest = None
            self.draw_idle()

    def on_mouse_move(self, event):
        """ 鼠标移动事件处理 """
        # 快速检查
        if not self.raw_data or event.x is None or event.y is None:
            return

        # 确保数据已预处理
        if not self.data_processed:
            self.preprocess_data()

        # 检查鼠标是否在绘图区域内
        if not self.axes.contains(event)[0]:
            if self.tooltip.get_visible():
                self.tooltip.set_visible(False)
                self.last_closest = None
                self.draw_idle()
            return

        # 限制更新频率，平衡性能和实时性
        self.update_counter = (self.update_counter + 1) % 2
        if self.update_counter != 0:
            return

        # 获取鼠标像素坐标
        x_pix, y_pix = event.x, event.y
        min_dist = float('inf')
        closest_point = None
        closest_label = None

        # 遍历所有数据系列（使用缓存的像素坐标）
        for label, pixels in self.pixel_cache.items():
            # 计算所有点到鼠标的距离
            distances = np.hypot(pixels[:, 0] - x_pix, pixels[:, 1] - y_pix)
            min_idx = np.argmin(distances)

            if distances[min_idx] < min_dist and distances[min_idx] < self.distance_threshold:
                min_dist = distances[min_idx]
                # 获取原始数据点
                x_data, y_data, _ = self.raw_data[label]
                closest_point = (x_data[min_idx], y_data[min_idx])
                closest_label = label

        # 更新提示框（只有变化时才更新）
        if closest_point != self.last_closest:
            self.last_closest = closest_point

            if closest_point:
                # 更新提示框内容
                time_str = closest_point[0].strftime('%Y-%m-%d %H:%M')
                value_str = f'{closest_point[1]:.2f}'
                self.tooltip.set_text(f'{closest_label}\n时间: {time_str}\n值: {value_str}')

                # 设置提示框位置
                self.tooltip.set_x(x_pix / self.fig.bbox.width)
                self.tooltip.set_y(y_pix / self.fig.bbox.height)

                if not self.tooltip.get_visible():
                    self.tooltip.set_visible(True)
                self.draw_idle()
            else:
                if self.tooltip.get_visible():
                    self.tooltip.set_visible(False)
                    self.draw_idle()

    def on_scroll(self, event):
        """ 处理鼠标滚轮事件，实现缩放功能 """
        # 检查事件有效性和鼠标是否在绘图区域内
        if event.inaxes != self.axes:
            return

        # 获取当前鼠标位置的坐标
        x = event.xdata
        y = event.ydata

        # 确定缩放方向
        if event.button == 'up':
            # 向前滚动 - 放大
            scale_factor = 1.0 / self.zoom_factor
        elif event.button == 'down':
            # 向后滚动 - 缩小
            scale_factor = self.zoom_factor
        else:
            return

        # 获取当前坐标轴范围
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()

        # 计算新的坐标轴范围（以鼠标位置为中心缩放）
        new_xlim = [
            x - (x - xlim[0]) * scale_factor,
            x + (xlim[1] - x) * scale_factor
        ]
        new_ylim = [
            y - (y - ylim[0]) * scale_factor,
            y + (ylim[1] - y) * scale_factor
        ]

        # 设置新的坐标轴范围
        self.axes.set_xlim(new_xlim)
        self.axes.set_ylim(new_ylim)

        # 刷新图表
        self.draw_idle()