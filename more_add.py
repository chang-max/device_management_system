"""
    多设备添加界面
"""
import os
from re import S
import PyQt6.QtWidgets as QtWidgets
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import pyqtSignal, Qt,QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from datetime import datetime
import pandas as pd
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

from generalfunction import add_device_default_row
from UI.more_add_ui import Ui_Dialog



from log_save import Logger
_log = Logger(True).logger


class MoreAddDialog(QtWidgets.QDialog, Ui_Dialog):
    # signal_add = pyqtSignal() # 信号槽：添加设备：行-设备名称-设备号-区域1-区域2-区域3
    
    def __init__(self,current_account,db_pool,proxy,apply_col_config,area_list, parent=None):
        super(MoreAddDialog, self).__init__(parent)
        self.setupUi(self)
        
        self.current_account = current_account #账户
        self.db_pool = db_pool # 数据库连接池
        self.proxy = proxy # 代理对象
        self.apply_col_config = apply_col_config # 应用列配置
        self.area_list = area_list # 区域列表


        self.UI_more_path_btn.clicked.connect(self.get_devs_path)
        self.UI_more_add_btn.clicked.connect(self.add_devs)
        self.UI_cancel_btn.clicked.connect(self.close) # 取消按钮点击信号槽



    def get_devs_path(self):
        """获取多设备文件路径"""
        # 创建一个隐藏的主窗口（仅用于提供文件对话框的父窗口）
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口

        # 打开文件选择对话框，限制只能选择TXT文件
        file_path = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        else:
            self.UI_more_path_lineedit.setText(file_path)
    
    
    def add_devs(self):
        """添加多设备"""
        # 0. 获取execl内容
        file_path = self.UI_more_path_lineedit.text()
        if not file_path:
            _log.error("请先选择Excel文件")
            return
        # 读取Excel文件
        df = pd.read_excel(file_path, skiprows=1)
        if df is None:
            return
        # 1. 检查列名是否正确
        required_cols = ["设备号", "设备名称", "一级区域", "二级区域", "三级区域","经度","纬度","时区","备注"]
        _log.debug(f"Excel文件列名：{df.columns}")
        if not all(col in df.columns for col in required_cols):
            QMessageBox.critical(self, "列名错误", f"Excel文件列名错误，需要包含：{', '.join(required_cols)}")
            _log.error(f"Excel文件列名错误，需要包含：{', '.join(required_cols)}")
            return
        # 2. 清空原有备注
        if "备注" in df.columns:
            df["备注"] = pd.NA
        else:
            df["备注"] = pd.NA

        # 3. 清理空行
        df = df.dropna(subset=[df.columns[0], df.columns[1]]).copy()
        df = df.reset_index(drop=True)
        if df.empty:
            QMessageBox.warning(self, "提示", "Excel无有效数据")
            return
        
        # 4. 提取设备号
        device_ids = df.iloc[:, 0].astype(str).str.strip().tolist()
        
        # 5. 批量查询数据库
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    placeholders = ",".join(["%s"] * len(device_ids))
                    sql_check = f"SELECT 设备号, 账户 FROM device_info WHERE 设备号 IN ({placeholders})"
                    cursor.execute(sql_check, device_ids)
                    db_rows = cursor.fetchall()

            exist_map = {str(row["设备号"]).strip(): row["账户"] for row in db_rows}
        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"检查设备失败：{str(e)}")
            _log.error(f"批量检查设备失败: {e}")
            return

        # 6. 逐行检查，写入备注
        insert_values = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        has_error = False
        for idx, row in df.iterrows():
            error_remarks = ""


            device_id = str(row.iloc[0]).strip()
            device_name = str(row.iloc[1]).strip()
            area1 = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ""
            area2 = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ""
            area3 = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ""
            try:
                lng = float(row.iloc[5])
                lat = float(row.iloc[6])
                zone_time = int(row.iloc[7])
            except ValueError:
                _log.error(f"经度、纬度或时区格式错误：{lng},{lat},{zone_time}")
                error_remarks += "经度、纬度或时区格式错误\n"
                continue

            insert_values.append((
                device_name, device_id, self.current_account, now, area1, area2, area3,lng,lat,zone_time
            ))
            
            if not self.is_valid_area_path(self.area_list, [area1, area2, area3]):
                error_remarks += "区域路径错误，需要符合父子结构\n"
                continue
        


            device_id = str(row.iloc[0]).strip()
            excel_row = idx + 2

            if device_id not in exist_map:
                continue

            db_account = exist_map[device_id]

            # 空账户允许更新
            if db_account is None or db_account == "":
                continue

            # 自己账户
            if db_account == self.current_account:
                df.at[idx, "备注"] = error_remarks + "导入失败：设备已存在于本账户"
            else:
                df.at[idx, "备注"] = error_remarks + f"导入失败：设备已被 {db_account} 占用"
            has_error = True

        # 6. 报错时写入Excel，被打开则自动另存
        if has_error:
            try:
                df.to_excel(file_path, index=False, engine="openpyxl")
                tip_path = file_path
            except PermissionError:
                path_no_ext, ext = os.path.splitext(file_path)
                new_path = f"{path_no_ext}_错误结果{ext}"
                df.to_excel(new_path, index=False, engine="openpyxl")
                tip_path = new_path
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"无法写入错误信息：{str(e)}")
                return

            QMessageBox.warning(
                self,
                "导入终止",
                f"数据存在冲突，错误已写入：\n\n{tip_path}"
            )
            _log.error(f"导入失败，错误已保存至：{tip_path}")
            return
        
        # 8. 无错误 → 批量插入/更新
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    for values in insert_values:
                        device_name, device_id, account, date_val, area1, area2, area3, lng, lat, zone = values
                        
                        # 先检查设备是否存在
                        cursor.execute("SELECT 设备号 FROM device_info WHERE 设备号 = %s", (device_id,))
                        existing = cursor.fetchone()
                        
                        if existing:
                            # 设备存在，UPDATE
                            update_sql = """
                                UPDATE device_info 
                                SET 设备名称 = %s, 账户 = %s, 日期 = %s, 
                                    区域1 = %s, 区域2 = %s, 区域3 = %s,
                                    经度 = %s, 纬度 = %s, 时区 = %s
                                WHERE 设备号 = %s
                            """
                            cursor.execute(update_sql, (device_name, account, date_val, area1, area2, area3, lng, lat, zone, device_id))
                        else:
                            # 设备不存在，INSERT
                            insert_sql = """
                                INSERT INTO device_info (设备名称, 设备号, 账户, 日期, 区域1, 区域2, 区域3, 经度, 纬度, 时区)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
                            cursor.execute(insert_sql, values)
                    
                    conn.commit()

            QMessageBox.information(self, "成功", f"批量导入完成：{len(insert_values)} 台")
            _log.debug(f"批量导入成功：{len(insert_values)} 条")

            for _, row in df.iterrows():
                device_id = str(row.iloc[0]).strip()
                device_name = str(row.iloc[1]).strip()
                area1 = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ""
                area2 = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ""
                area3 = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ""
                device = {
                        "设备号": device_id,
                        "设备名称": device_name,
                        "区域1": area1,
                        "区域2": area2,
                        "区域3": area3,
                        "日期": now,
                        "工作计划": "{}",
                        "经度": lng,
                        "纬度": lat,
                        "时区": zone_time
                    }
                
                add_device_default_row(self.proxy,self.apply_col_config,device)

        except Exception as e:
            QMessageBox.critical(self, "失败", f"数据库写入失败：{str(e)}")
            _log.error(f"批量导入异常：{e}")


    def is_valid_area_path(self,area_tree, path):
        """
        校验区域路径是否符合父子结构
        :param area_tree: 你的完整区域树（list）
        :param path: ["上海市","青浦区",""]
        :return: True/False
        """
        # 过滤空字符串
        path = [p.strip() for p in path if p.strip()]
        if not path:
            return False

        current_level_nodes = area_tree
        depth = 0

        for name in path:
            found = False
            for node in current_level_nodes:
                if node.get("name") == name:
                    current_level_nodes = node.get("children", [])
                    depth += 1
                    found = True
                    break
            if not found:
                return False

        return True

    def close(self):
        """关闭对话框"""
        self.accept()

if __name__ == "__main__":
    import sys
    import tkinter as tk
    from tkinter import filedialog
    from tkinter import ttk
    app = QtWidgets.QApplication(sys.argv)

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




    area_list = [{'area': {'type': '未知', 'coords': [], 'area_name': '上海市'}, 'name': '上海市', 'level': 1, 'children': [{'area': {'type': '未知', 'coords': [], 'area_name': '闵行区'}, 'name': '闵行区', 'level': 2, 'children': [{'area': {'type': 'Overlay.Polygon', 'coords': [[116.583059, 39.924421], [116.583198, 39.922757], [116.586118, 39.922978], [116.585794, 39.924589], [116.584444, 39.924138]], 'area_name': '申滨南路'}, 'name': '申滨南路', 'level': 3}, {'area': {'type': '', 'coords': [], 'area_name': '申长路'}, 'name': '申长路', 'level': 3}]}, {'area': {'type': '未知', 'coords': [], 'area_name': '浦东新区'}, 'name': '浦东新区', 'level': 2, 'children': []}]}, {'area': {'type': '未知', 'coords': [], 'area_name': '深圳市'}, 'name': '深圳市', 'level': 1, 'children': [{'area': {'type': '未知', 'coords': [], 'area_name': '南山区'}, 'name': '南山区', 'level': 2, 'children': []}]}]
    row = 0
    default_config = {}
    dialog = MoreAddDialog(current_account,pool,proxy,area_list)
    dialog.exec()
    sys.exit(app.exec())