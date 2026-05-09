"""
用户管理模块 - 前端UI界面
用于管理sys_user表的用户信息
"""
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QDialog, QFormLayout,
    QDateEdit, QHeaderView, QAbstractItemView, QMenu
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QAction

from user_manager_db import UserManagerDB


class UserEditDialog(QDialog):
    """用户编辑对话框"""

    def __init__(self, parent=None, user_data=None, is_edit=False):
        """
        初始化对话框
        :param parent: 父窗口
        :param user_data: 用户数据（编辑时传入）
        :param is_edit: 是否为编辑模式
        """
        super().__init__(parent)
        self.user_data = user_data
        self.is_edit = is_edit
        self.setWindowTitle("编辑用户" if is_edit else "新增用户")
        self.setMinimumWidth(350)
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QFormLayout(self)

        # 用户名
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("请输入用户名")
        if self.is_edit and self.user_data:
            self.username_edit.setText(self.user_data.get('username', ''))
            self.username_edit.setEnabled(False)  # 编辑时用户名不可修改
        layout.addRow("用户名:", self.username_edit)

        # 密码
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("请输入密码")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if self.is_edit and self.user_data:
            self.password_edit.setText(self.user_data.get('password', ''))
        layout.addRow("密码:", self.password_edit)

        # 有效期
        self.expiry_edit = QDateEdit()
        self.expiry_edit.setCalendarPopup(True)
        self.expiry_edit.setDisplayFormat("yyyy-MM-dd")

        if self.is_edit and self.user_data:
            # 编辑模式：使用现有有效期
            expiry_date = self.user_data.get('expiry_date')
            if expiry_date:
                if isinstance(expiry_date, str):
                    expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d')
                self.expiry_edit.setDate(QDate(expiry_date.year, expiry_date.month, expiry_date.day))
            else:
                self.expiry_edit.setDate(QDate.currentDate().addMonths(3))
        else:
            # 新增模式：默认3个月后
            self.expiry_edit.setDate(QDate.currentDate().addMonths(3))

        layout.addRow("有效期:", self.expiry_edit)

        # MAC绑定
        self.mac_edit = QLineEdit()
        self.mac_edit.setPlaceholderText("FF:FF:FF:FF:FF:FF")
        if self.is_edit and self.user_data:
            self.mac_edit.setText(self.user_data.get('mac_bind', 'FF:FF:FF:FF:FF:FF'))
        else:
            self.mac_edit.setText("FF:FF:FF:FF:FF:FF")
        layout.addRow("MAC绑定:", self.mac_edit)

        # 按钮
        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.cancel_btn = QPushButton("取消")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addRow("", button_layout)

    def get_data(self):
        """获取对话框中的数据"""
        return {
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text().strip(),
            'expiry_date': self.expiry_edit.date().toPyDate(),
            'mac_bind': self.mac_edit.text().strip() or "FF:FF:FF:FF:FF:FF"
        }


class UserManagerWidget(QWidget):
    """用户管理主界面"""

    def __init__(self, db_pool, parent=None):
        """
        初始化
        :param db_pool: 数据库连接池
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.db = UserManagerDB(db_pool)
        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("用户管理")
        self.setMinimumSize(800, 500)

        layout = QVBoxLayout(self)

        # 顶部按钮区域
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("新增用户")
        self.add_btn.clicked.connect(self.on_add_user)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_users)

        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 用户列表表格
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(4)
        self.user_table.setHorizontalHeaderLabels(["用户名", "密码", "有效期", "MAC绑定"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.user_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.user_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_table.customContextMenuRequested.connect(self.show_context_menu)
        self.user_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        layout.addWidget(self.user_table)

        # 状态标签
        self.status_label = QLabel("就绪")
        layout.addWidget(self.status_label)

    def load_users(self):
        """加载用户列表"""
        users = self.db.get_all_users()
        self.user_table.setRowCount(len(users))

        for row, user in enumerate(users):
            # 用户名
            username_item = QTableWidgetItem(user['username'])
            self.user_table.setItem(row, 0, username_item)

            # 密码（显示为星号）
            password_item = QTableWidgetItem("*" * len(user['password']) if user['password'] else "")
            self.user_table.setItem(row, 1, password_item)

            # 有效期
            expiry_date = user['expiry_date']
            if expiry_date:
                if isinstance(expiry_date, str):
                    expiry_str = expiry_date
                else:
                    expiry_str = expiry_date.strftime('%Y-%m-%d')
            else:
                expiry_str = ""
            expiry_item = QTableWidgetItem(expiry_str)
            self.user_table.setItem(row, 2, expiry_item)

            # MAC绑定
            mac_item = QTableWidgetItem(user['mac_bind'])
            self.user_table.setItem(row, 3, mac_item)

        self.status_label.setText(f"共 {len(users)} 个用户")

    def show_context_menu(self, position):
        """显示右键菜单"""
        row = self.user_table.rowAt(position.y())
        if row < 0:
            return

        self.user_table.selectRow(row)
        username = self.user_table.item(row, 0).text()

        menu = QMenu(self)

        # 编辑用户
        edit_action = QAction("编辑", self)
        edit_action.triggered.connect(lambda: self.on_edit_user(username))
        menu.addAction(edit_action)

        # MAC解绑
        unbind_action = QAction("MAC解绑", self)
        unbind_action.triggered.connect(lambda: self.on_unbind_mac(username))
        menu.addAction(unbind_action)

        menu.addSeparator()

        # 删除用户
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self.on_delete_user(username))
        menu.addAction(delete_action)

        menu.exec(self.user_table.viewport().mapToGlobal(position))

    def on_add_user(self):
        """新增用户"""
        dialog = UserEditDialog(self, is_edit=False)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            if not data['username']:
                QMessageBox.warning(self, "警告", "用户名不能为空")
                return

            if not data['password']:
                QMessageBox.warning(self, "警告", "密码不能为空")
                return

            success, msg = self.db.add_user(
                username=data['username'],
                password=data['password'],
                expiry_date=data['expiry_date'],
                mac_bind=data['mac_bind'],
                area_info=data.get('area_info', '{}')
            )

            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_users()
            else:
                QMessageBox.warning(self, "失败", msg)

    def on_edit_user(self, username):
        """编辑用户"""
        user = self.db.get_user_by_username(username)
        if not user:
            QMessageBox.warning(self, "错误", "用户不存在")
            return

        dialog = UserEditDialog(self, user_data=user, is_edit=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            success, msg = self.db.update_user(
                username=username,
                password=data['password'] if data['password'] else None,
                expiry_date=data['expiry_date'],
                mac_bind=data['mac_bind']
            )

            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_users()
            else:
                QMessageBox.warning(self, "失败", msg)

    def on_delete_user(self, username):
        """删除用户"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除用户 '{username}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.db.delete_user(username)
            if success:
                QMessageBox.information(self, "成功", msg)
                self.load_users()
            else:
                QMessageBox.warning(self, "失败", msg)

    def on_unbind_mac(self, username):
        """MAC解绑"""
        reply = QMessageBox.question(
            self, "确认解绑",
            f"确定要将用户 '{username}' 的MAC地址解绑吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.db.unbind_mac(username)
            if success:
                QMessageBox.information(self, "成功", f"用户 '{username}' MAC解绑成功")
                self.load_users()
            else:
                QMessageBox.warning(self, "失败", msg)


class UserManagerWindow(QWidget):
    """用户管理独立窗口（可直接运行）"""

    def __init__(self, db_pool=None):
        super().__init__()
        if db_pool is None:
            # 如果没有传入连接池，创建新的连接
            db_pool = self._create_db_pool()

        if db_pool is None:
            QMessageBox.critical(self, "错误", "无法连接到数据库")
            return

        self.setWindowTitle("用户管理系统")
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        self.user_manager = UserManagerWidget(db_pool, self)
        layout.addWidget(self.user_manager)

    def _create_db_pool(self):
        """创建数据库连接池"""
        try:
            import pymysql
            from pymysql.cursors import DictCursor
            from DBUtils.PooledDB import PooledDB

            pool = PooledDB(
                creator=pymysql,
                maxconnections=5,
                mincached=2,
                maxcached=5,
                blocking=True,
                maxusage=None,
                setsession=[],
                ping=0,
                host="112.64.32.181",
                port=3311,
                user="root",
                password="Moso@2024!",
                database="MST_SQL",
                charset="utf8mb4",
                cursorclass=DictCursor
            )
            return pool
        except Exception as e:
            print(f"数据库连接失败: {e}")
            return None


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = UserManagerWindow()
    window.show()
    sys.exit(app.exec())
