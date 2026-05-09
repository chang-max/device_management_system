from log_save import Logger
_log = Logger(True).logger

import sys
import json
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor
import traceback
import pymysql

from UI.History import Ui_Dialog
from PyQt6.QtWidgets import QApplication, QDialog,QMessageBox,QTableWidgetItem,QVBoxLayout,QCheckBox,QHBoxLayout,QGroupBox,QTableWidget
from PyQt6.QtCore import QDateTime,QTimer,pyqtSignal,Qt
from PyQt6.QtGui import QStandardItem
from functools import partial
from MyWidget import DateTimeTableWidgetItem,NumericTableWidgetItem,MplCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from messbox import Messbox
from threading import Thread
import matplotlib.dates as mdates
import matplotlib
import pandas as pd

import numpy as np
from matplotlib import cm
matplotlib.use('Qt5Agg')

# 精简字体配置，只保留系统中更常见的中文字体
matplotlib.rcParams["font.family"] = [
    "SimHei",          # 黑体，Windows和Linux系统广泛支持
    "Microsoft YaHei", # 微软雅黑，Windows系统默认安装
]
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# Matplotlib 画布嵌入PyQt
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=12, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)


class History(QDialog, Ui_Dialog):
    signal_mess_show = pyqtSignal(object, object)  # 显示提示信息
    signal_update_table = pyqtSignal(list)  # 更新表格信号（后台线程传递数据到主线程）
    def __init__(self,history_cols,db_pool,parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog
        self.setupUi(self)
        self.history_cols = history_cols.copy()
        self.history_cols.pop("设备时间")
        self.history_cols.pop("电流配置(0.01%)")

        # self.history_cols.pop("设备时间")

        self.color_map = self.list_to_color_dict(self.history_cols.keys())

        # 缓存真实原始数据
        self.df_original = None
        self.uniform_x = None
        self._hover_cid = None  # 鼠标悬浮事件连接ID

        self.UI_other_flg.setHidden(True)

        self.mess_ui = Messbox(self)
        self.signal_mess_show.connect(self.mess_ui.show_message)
        self.signal_update_table.connect(self._update_table_ui)  # 连接表格更新信号
        self.mess_time = QTimer()
        self.mess_time.timeout.connect(self.mess_ui.mess_ui_btn_true)

        # 设置表列名
        cols = ["上报时间"]
        for name in self.history_cols.keys():
            cols.append(name)
           

        self.UI_table_data.setColumnCount(len(cols))
        self.UI_table_data.setHorizontalHeaderLabels(cols)

        self.UI_start_time.clearFocus()

        self.table_name = ""

        # 测试
        self.db_pool = db_pool  # 数据库连接池

        self.UI_search_btn.clicked.connect(self.text_search)
        self.show_widget()
        #创建对应列勾选折线
        self.verticalLayout_3 = QVBoxLayout(self.tab_2)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.UI_cols_in_2 = QGroupBox(self.tab_2)
        self.UI_cols_in_2.setTitle("")
        self.UI_cols_in_2.setObjectName("UI_cols_in_2")
        self.UI_cols_in_2.setMaximumSize(16777215, 40)
        self.horizontalLayout_3 = QHBoxLayout(self.UI_cols_in_2)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.checkBoxs = []
        for col in self.history_cols:
            if col != "上报时间":
                checkBox = QCheckBox(self.UI_cols_in_2)
                checkBox.setChecked(False)
                checkBox.setText(col)
                checkBox.stateChanged.connect(self.redraw_plot)
                self.checkBoxs.append(checkBox)
                self.horizontalLayout_3.addWidget(checkBox)
        self.verticalLayout_3.addWidget(self.UI_cols_in_2)
        # 创建画布
        # 添加导航工具栏（包含缩放、平移等按钮）
        self.canvas = MplCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas,self)
        self.verticalLayout_3.addWidget(self.toolbar)
        self.verticalLayout_3.addWidget(self.canvas)
        self.tabWidget.addTab(self.tab_2, "")
        self.verticalLayout_2.addWidget(self.tabWidget)
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), "曲线数据")


    def get_checked_params(self):
        res = []
        for checkBox in self.checkBoxs:
            if checkBox.isChecked():
                res.append(checkBox.text())
        return res


    def show(self):
        self.UI_table_data.setRowCount(0)
        self.canvas.axes.clear()
        self.setWindowTitle(f"历史数据-{self.table_name}")
        self.showMaximized()#设置最大尺寸
        # super().show()




    def text_search(self):
        """搜索按钮事件"""
        start_time = self.UI_start_time.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        end_time = self.UI_end_time.dateTime().toString("yyyy-MM-dd HH:mm:ss")

        cols = ''
        for k in self.history_cols:
            cols += f"`{k}`,"
        cols = cols[:-1]

        sql = f"""
                SELECT datetime, data
                FROM `{self.table_name}`
                WHERE datetime BETWEEN '{start_time}' AND '{end_time}'
                  AND sv != 'rqst'
                  AND ct NOT IN ('L' ,'H','W')
                ORDER BY datetime ASC
            """

    
        # print("history sql:",sql)
        thread = Thread(target=self.serch_thread, args=(sql,))
        thread.start()


    def serch_thread(self,order):
        """搜索线程 - 后台执行数据库查询和数据解析，UI更新通过信号发送到主线程"""
        with self.db_pool.connection() as conn:
            with conn.cursor() as cursor:
                # print("开始查询",order)
                self.signal_mess_show.emit("start", f"查询中")
                try:
                    cursor.execute(order)
                    rows = cursor.fetchall()
                except Exception as e:
                        self.signal_mess_show.emit("end", f"查询失败: {str(e)}")
                        return
        if len(rows) != 0:
            data_list = []
            table_data_list = []  # 用于传递给主线程更新表格的数据
            for index,row in enumerate(rows):

                try:
                    reporting_time = row["datetime"].strftime('%Y-%m-%d %H:%M:%S')
                    data = json.loads(row["data"])
                except Exception as e:
                    _log.error(f"解析JSON数据失败: {row['data']}，错误信息: {e}")
                    continue
                else:
                    result = [reporting_time]
                    broken_line = {}
                    broken_line["上报时间"] = pd.to_datetime(reporting_time)
                    result_flg = False
                    for col_name, config_list in self.history_cols.items():
                        try:
                            text = data
                            for key in config_list[0]:
                                text = text[key]
                            if type(text).__name__ == "list":
                                text = text[0]
                            if "FLOAT" in config_list[1]:
                                text = float(text)
                                if config_list[2] != 0:
                                    text = text / (10 ** config_list[2])
                                result_flg = True
                            elif "INT" in config_list[1]:
                                text = int(text)
                                if config_list[2] != 0:
                                    text = text / (10 ** config_list[2])
                                result_flg = True

                            elif "VARCHAR" in config_list[1]:
                                text = str(text)
                                result_flg = True

                            elif "DATETIME" in config_list[1]:
                                text = str(text)
                            else:
                                log.error(f"出现非数据库类型数据 {col_name}  {config_list[1]}")
                        except Exception as e:
                            broken_line[col_name] = np.nan
                            result.append("-")
                            # _log.error(f"解析数据 {col_name} 失败：{str(e)}")
                        else:
                            broken_line[col_name] = text
                            result.append(str(text))
                    if result_flg: # 有数据
                        # 收集表格数据，通过信号发送到主线程更新
                        table_data_list.append(result)
                    # _log.debug(f"解析数据 {result}")
    # QMessageBox.information(self, "成功", f"已加载{len(result)}条数据")
                data_list.append(broken_line)

            # 发送信号到主线程更新表格
            self.signal_update_table.emit(table_data_list)

            if not data_list:
                self.df_original = pd.DataFrame()
            else:
                df = pd.DataFrame(data_list)

                df = df.drop_duplicates("上报时间").sort_values("上报时间").reset_index(drop=True)
                self.df_original = df
                self.uniform_x = self.create_uniform_x_axis(self.df_original)
                self.redraw_plot()
            # self.plot_data()
            self.signal_mess_show.emit("end", f"已加载{len(data_list)}条数据")
        else:
            #表格清空 - 通过信号发送到主线程
            self.signal_update_table.emit([])
            #绘图清空
            self.canvas.axes.clear()
            self.canvas.raw_data = {}
            self.canvas.pixel_cache = {}
            self.canvas.data_processed = False
            self.canvas.draw()
            self.signal_mess_show.emit("end", f"该时间区域内无数据")

    def _update_table_ui(self, table_data_list):
        """在主线程中更新表格UI（槽函数）"""
        try:
            if not table_data_list:
                # 清空表格
                self.UI_table_data.setRowCount(0)
                return

            # 设置行数
            self.UI_table_data.setRowCount(len(table_data_list))

            # 填充数据
            for row_idx, row_data in enumerate(table_data_list):
                for col_idx, value in enumerate(row_data):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.UI_table_data.setItem(row_idx, col_idx, item)

        except Exception as e:
            _log.error(f"更新表格UI失败: {e}")
            import traceback
            traceback.print_exc()


    def show_widget(self):
        now_time = QDateTime.currentDateTime()
        self.UI_end_time.setDateTime(now_time)
        now_time = now_time.addDays(-1)
        self.UI_start_time.setDateTime(now_time)

    # def analysis_data(self, data):
    #     """解析数据"""
    #     self.ta

    # ===================== X轴均匀化 =====================
    def create_uniform_x_axis(self, df):
        n = len(df)
        return np.linspace(0, n-1, n)

    def _get_optimal_ticks(self, n_points, max_labels=10):
        """根据数据点数量计算最优的刻度间隔"""
        if n_points <= max_labels:
            step = 1
        else:
            step = max(1, n_points // max_labels)
        return np.arange(0, n_points, step)

    def redraw_plot(self):
        if self.df_original is None or self.uniform_x is None:
            return

        ax = self.canvas.axes
        ax.clear()
        show_params = self.get_checked_params()

        # 如果没有勾选任何参数，显示提示
        if not show_params:
            ax.text(0.5, 0.5, '请勾选要显示的参数',
                   horizontalalignment='center', verticalalignment='center',
                   transform=ax.transAxes, fontsize=14)
            self.canvas.draw()
            return

        n_points = len(self.uniform_x)

        lines = []
        line_info = []  # 存储每条线的信息，用于悬浮提示
        for param in show_params:
            if param not in self.df_original.columns:
                _log.warning(f"参数 {param} 不在数据列中")
                continue

            # 获取数据，处理NaN值
            y_data = self.df_original[param].values

            # 分离有效点和NaN点
            valid_mask = ~np.isnan(y_data)
            valid_x = self.uniform_x[valid_mask]
            valid_y = y_data[valid_mask]
            valid_indices = np.where(valid_mask)[0]  # 原始数据中的有效索引

            if len(valid_y) == 0:
                _log.warning(f"参数 {param} 没有有效数据")
                continue

            # 绘制折线（跳过NaN，连接前后有效点）
            line, = ax.plot(valid_x, valid_y,
                            label=param, color=self.color_map.get(param, '#333333'),
                            linewidth=1.5, marker='o', markersize=3)
            lines.append(line)
            # 存储该线的有效索引映射，用于悬浮提示
            line_info.append({
                'line': line,
                'param': param,
                'valid_indices': valid_indices,
                'valid_y': valid_y
            })

        # 智能选择X轴刻度 - 最多显示10个时间标签
        tick_indices = self._get_optimal_ticks(n_points, max_labels=10)
        tick_positions = self.uniform_x[tick_indices]
        tick_labels = self.df_original["上报时间"].iloc[tick_indices].dt.strftime("%m-%d %H:%M:%S")

        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, fontsize=8)
        # ax.set_title("所有真实数据点 - 均匀时间轴")
        # ax.set_xlabel("时间")
        # ax.set_ylabel("数值")
        if lines:
            ax.legend()
        ax.grid(True, alpha=0.3)
        self.canvas.fig.tight_layout()

        # 断开之前的悬浮事件连接，避免重复
        if self._hover_cid is not None:
            self.canvas.mpl_disconnect(self._hover_cid)
            self._hover_cid = None

        self.bind_hover(line_info)
        self.canvas.draw()

        # ===================== 鼠标悬浮 =====================
    def bind_hover(self, line_info):
        def hover(event):
            # 检查事件是否有效
            if event.inaxes != self.canvas.axes or not event.inaxes:
                return

            # 检查 figure 是否已设置
            if not self.canvas.fig or not self.canvas.axes:
                return

            found = False
            for info in line_info:
                line = info['line']
                param = info['param']
                valid_indices = info['valid_indices']
                valid_y = info['valid_y']

                # 检查 line 是否有 figure
                if not line.figure:
                    continue

                try:
                    cont, idx = line.contains(event)
                    if cont:
                        # idx 是在有效数据中的索引，需要映射回原始数据索引
                        valid_i = idx["ind"][0]
                        original_i = valid_indices[valid_i]
                        time_str = self.df_original["上报时间"].iloc[original_i].strftime("%Y-%m-%d %H:%M:%S")
                        val = valid_y[valid_i]
                        self.canvas.axes.set_title(f"时间：{time_str} | {param} = {val:.2f}")
                        self.canvas.draw()
                        found = True
                        return
                except Exception:
                    # 忽略检查错误
                    continue

            if not found:
                # self.canvas.axes.set_title("所有真实数据点 - 均匀时间轴")
                self.canvas.draw()

        # 保存连接ID以便后续断开
        self._hover_cid = self.canvas.mpl_connect("motion_notify_event", hover)

    def list_to_color_dict(self, lst):
        """
        输入任意长度的列表，返回 元素:颜色 的字典
        """
        if not lst:
            return {}

        # 自动生成均匀分布的颜色（不重复、视觉友好）
        # 使用 matplotlib.colormaps 替代弃用的 cm.get_cmap
        cmap = matplotlib.colormaps.get_cmap('tab20')
        color_dict = {}

        for idx, item in enumerate(lst):
            # 转成十六进制颜色（#ffffff 格式）
            hex_color = mcolors.rgb2hex(cmap(idx / len(lst))[:4])
            color_dict[item] = hex_color

        return color_dict

if __name__ == "__main__":
    def except_hook(cls, exception, ttraceback):
        """重写UI闪退导致无法日志输出问题"""
        import traceback
        err_msg = ""
        for index, msg_list in enumerate(traceback.format_exception(cls, exception, ttraceback)):
            if index != 0:
                for index, v in enumerate(msg_list.split("\n")):
                    if index != len(msg_list.split("\n")):
                        if v != "":
                            err_msg += "                            " + v + "\n"
            else:
                err_msg += msg_list
        log.error(err_msg)

    pool = PooledDB(
            creator=pymysql,
            maxconnections=5,  # 🔥 核心：最大连接数，设5就够500设备
            mincached=2,  # 初始化时连接池中的空闲连接数
            maxcached=3, # 连接池中空闲的最大连接数（0或None表示无限制）
            blocking=True,  # 无可用连接时是否阻塞等待（True=等待，False=抛出异常）
            maxusage=None, # 可共享的最大连接数（0表示所有连接都是专用的）
            setsession=[],
            ping=0,

            # MySQL 配置
            host="112.64.32.181",
            port=3311,
            user="root",
            password="Moso@2024!",
            database="MST_SQL",
            charset="utf8mb4",
            cursorclass=DictCursor
        )

    app = QApplication(sys.argv)
    sys.excepthook = except_hook
    cols ={'调光值': [['DT', 'RunSts', 'bri'], 'INT NULL', 0], '输入电压(V)': [['DT', 'EleInfo', 'v'], 'FLOAT NULL', 1], '输入电流(A)': [['DT', 'EleInfo', 'c'], 'FLOAT NULL', 3], '功率因数': [['DT', 'EleInfo', 'f'], 'FLOAT NULL', 0], '输入功率': [['DT', 'EleInfo', 'p'], 'FLOAT NULL', 0], '输出电压(V)': [['DT', 'EleInfo', 'ov'], 'FLOAT NULL', 1], '输出电流(A)': [['DT', 'EleInfo', 'oc'], 'FLOAT NULL', 3], '输出功率': [['DT', 'EleInfo', 'op'], 'FLOAT NULL', 0], '效率': [['DT', 'EleInfo', 'eff'], 'FLOAT NULL', 1], '运行时间(min)': [['DT', 'RunTm', 'tTime'], 'INT NULL', 0], '本次能耗(kW·h)': [['DT', 'EleInfo', 'rEc'], 'FLOAT NULL', 3], '累计能耗(kW·h)': [['DT', 'EleInfo', 'tEc'], 'FLOAT NULL', 3], '电源温度(℃)': [['DT', 'PerSts', 'temp'], 'FLOAT NULL', 1], '控制版温度(℃)': [['DT', 'PerSts', 'ctrltemp'], 'FLOAT NULL', 1], '信号强度(dbm)': [['DT', 'Signal', 'rsrp'], 'FLOAT NULL', 1], '电流配置(0.01%)': [['DT', 'Dim', 0, 'rti'], 'INT NULL', 0], '设备时间': [['TM'], 'DATETIME NOT NULL', None]}
    myWin = History(cols,pool)
    myWin.table_name = "868292083594477"
    myWin.show()
    sys.excepthook = except_hook
    sys.exit(app.exec())
