import logging
import os

from configparser import ConfigParser
from platform import system
import urllib.request
from Crypto.Util.Padding import pad
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import pyqtSignal, Qt
from threading import Thread
import ntplib
from datetime import datetime, timezone
from time import strptime, localtime, mktime, strftime, sleep
import requests
import psutil
import socket
from re import compile

from UI.log_in_UI import Ui_Dialog
from log_save import Logger
_log = Logger(True).logger


class LogIn(QtWidgets.QDialog, Ui_Dialog):
    signal_main_exit = pyqtSignal()  # 登录手动退出信息--用户不进行登录--退出所有程序
    signal_text_change = pyqtSignal(object)  # 用于登录界面显示错误信息
    signal_login_success = pyqtSignal(object)  # 用于登录成功

    def __init__(self,db_pool, parent=None):
        super(LogIn, self).__init__(parent)
        self.setupUi(self)
        # self.setWindowFlags(Qt.FramelessWindowHint)

        self.setWindowFlags(
            Qt.WindowType.Dialog| Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint
        )
        self.setModal(True)
        self.db_pool = db_pool

        self.mac = self.get_all_macs_with_netifaces()
        self.ini_path = ""

        self.old_usr_passwd = ""

        self.get_default()
        self.UI_login_btn.clicked.connect(self.login)
        self.UI_cancel_btn.clicked.connect(self.exit_ui)
        self.signal_text_change.connect(self.text_show)
        self.signal_login_success.connect(self.UI_login_btn.setEnabled)
        # self.UI_stauts.setHidden(True)

        # 获取LineEdit并禁用复制功能
        self.UI_passwd_btn.setDragEnabled(False)  # 禁用拖选
        self.UI_passwd_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)  # 禁用右键菜单

        # 正确处理键盘事件（保留原有功能，仅拦截复制操作）
        original_keyPressEvent = self.UI_passwd_btn.keyPressEvent

        def new_keyPressEvent(event):
            # 禁用Ctrl+C/Ctrl+X
            if event.modifiers() & Qt.ControlModifier and event.key() in (Qt.Key_C, Qt.Key_X):
                return
            # 其他事件交给原始处理函数
            original_keyPressEvent(event)

        self.UI_passwd_btn.keyPressEvent = new_keyPressEvent

    def disable_copy_shortcut(self, event):
        # 禁用Ctrl+C/Ctrl+X
        if event.modifiers() & Qt.ControlModifier and event.key() in (Qt.Key_C, Qt.Key_X):
            return
        super().keyPressEvent(event)

    def text_show(self, text_list):
        self.UI_stauts.clear()
        # _log.debug(f"text_show  {text_list} -- {type(text_list)}--{text_list == ""} --{self.isVisible()}")
        if type(text_list) == int or text_list == "":
            # _log.debug("登录成功")
            self.hide()
            # 登录成功
        else:  # 登录失败，有错误信息
            for text in text_list:
                _log.error(text)
                self.UI_stauts.append(text)
            if self.isHidden():
                _log.debug("登录失败，显示错误信息")
                self.exec()

    def login(self):
        self.UI_login_btn.setEnabled(False)
        usr = self.get_lineedit_text(self.UI_usr_btn)
        pwd = self.get_lineedit_text(self.UI_passwd_btn)
        self.usr_passwd = usr + " " + pwd
        _log.info(f"登录信息：{self.usr_passwd}")
        # self.get_url_content()
        thread = Thread(target=self.period_of_validity, daemon=True)  # 后台线程,防止界面卡死
        thread.start()

    def get_lineedit_text(self, widget):
        text = widget.text()
        if text == '':
            text = widget.placeholderText()
        return text

    def exit_ui(self):
        # self.hide()
        _log.debug("退出信号发送")
        self.close()
        self.signal_main_exit.emit()


    def get_default(self):
        """ Get default user and password"""
        self.ini_path = os.path.join("config", "config.ini")
        if system() == "Windows":
            # Windows系统：用户目录通常在C:\Users\<用户名>
            user_dir = os.path.expanduser("~")

            # 1. 获取用户目录
            target_folder = os.path.join(user_dir, "MOSO_TOOL")

            # 2. 创建文件夹（如果不存在）
            if not os.path.exists(target_folder):
                os.makedirs(target_folder)
                _log.info(f"已创建文件夹: {target_folder}")
            else:
                _log.info(f"文件夹已存在: {target_folder}")

            # 3. 生成ini配置文件路径
            self.ini_path = os.path.join(target_folder, "config.ini")

        # 4. 创建默认ini配置（如果文件不存在）
        if not os.path.exists(self.ini_path):
            config = ConfigParser()

            # 添加默认配置项
            config["LOGIN"] = {
                "usr": "",
                "pwd": "",
            }

            # 写入配置文件
            with open(self.ini_path, "w", encoding="utf-8") as configfile:
                config.write(configfile)
            _log.info(f"已创建默认配置文件: {self.ini_path}")
        else:
            _log.info(f"配置文件已存在: {self.ini_path}")

        try:
            conf = ConfigParser()  # 需要实例化一个ConfigParser对象
            conf.read(self.ini_path, encoding='gbk')  # 需要添加上config.ini的路径，不需要open打开，直接给文件路径就读取，也可以指定encoding='utf-8'
            # 读取配置文件中的config.ini文件
            usr = self.implicittext_to_plaintext(conf.get("LOGIN", "usr"))
            pwd = self.implicittext_to_plaintext(conf.get("LOGIN", "pwd"))
        except Exception as e:
            _log.error(e)
            self.hide()
        else:
            self.UI_usr_btn.setText(usr)
            self.UI_passwd_btn.setText(pwd)

    def implicittext_to_plaintext(self, text):
        """暗文转明文"""
        BLOCK_SIZE = 16
        key = "MOSOMOSOMOSOMOSO"
        decipher = AES.new(key.encode('utf8'), AES.MODE_ECB)
        msg_dec = decipher.decrypt(bytes.fromhex(text))
        return str(unpad(msg_dec, BLOCK_SIZE), encoding='utf-8')

    def plaintext_to_implicittext(self, text):
        """明文转暗文"""
        BLOCK_SIZE = 16  # Bytes
        key = "MOSOMOSOMOSOMOSO"
        data = []
        cipher = AES.new(key.encode('utf8'), AES.MODE_ECB)
        # print(time_data)
        # time_data = "1627622400"
        msg = cipher.encrypt(pad(bytes(text, encoding="utf8"), BLOCK_SIZE))
        return msg.hex()

    def save_config(self, usr_passwd):
        """ 本地保存用户名密码"""
        # _log.error(flg)
        try:
            usr = self.plaintext_to_implicittext(usr_passwd.split(" ")[0])
            pwd = self.plaintext_to_implicittext(usr_passwd.split(" ")[1])
            conf = ConfigParser()
            conf.read(self.ini_path, encoding='gbk')
            conf.set("LOGIN", "usr", usr)
            conf.set("LOGIN", "pwd", pwd)
            with open(self.ini_path, "w", encoding='gbk') as f:
                conf.write(f)
        except Exception as e:
            _log.error(f"用户名密码保存失败：{e}")

    def period_of_validity(self):
        err_count = 1  # 循环次数 #首次登录时，默认循环1次
        err_sleep = 1  # 错误时 多次校验 循环休眠间隔
        success_sleep = 10  # 成功时 循环休眠间隔
        while_flg = True  # 循环标记
        while while_flg:
            # _log.info(f"第{err_count}次校验")
            for i in range(err_count):  # 错误时 多次校验
                msg_list = []  # 错误信息列表
                try:  # 获取网络时间
                    local_time = self.get_webtime()
                    # _log.debug(f"网络时间：{local_time}")
                except Exception as e:
                    # _log.error(f"获取网络时间失败：{e}")
                    msg_list.append(f"获取网络时间失败：{e}")
                    while_flg = False  # 主循环退出
                else:
                    try:  # 获取服务器 用户数据
                        usrs_dict = self.get_mysql_usr()
                        # _log.info(f"获取数据库:{usrs_dict}")
                        if not usrs_dict:
                            _log.error("服务器用户数据为空！！")
                            msg_list.append("服务器用户数据为空！！")
                            while_flg = False  # 主循环退出
                            continue
                        # _log.debug(f"服务器用户数据：{usrs_dict}")
                    except Exception as e:
                        _log.error(f"获取服务器用户数据失败：{e}")
                        msg_list.append(f"获取服务器用户数据失败：{e}")
                        while_flg = False  # 主循环退出
                    else:
                        # 进行校验用户数据
                        # _log.debug("校验用户数据")
                        if self.usr_passwd in usrs_dict:
                            # _log.debug(f"{usrs_dict[self.usr_passwd][1] == ["FF:FF:FF:FF:FF:FF"] }  { bool(set(usrs_dict[self.usr_passwd][1]) & set(self.mac))}")
                            if usrs_dict[self.usr_passwd][1] == ["FF:FF:FF:FF:FF:FF"] or bool(set(usrs_dict[self.usr_passwd][1]) & set(self.mac)):  # 校验MAC地址
                                # 获取服务器用户名对应时间戳
                                date_obj = datetime.strptime(usrs_dict[self.usr_passwd][0], "%Y-%m-%d")
                                # 转换为时间戳（UTC 时区）
                                time_key = date_obj.timestamp()
                                timeArray = localtime(time_key)
                                otherStyleTime = strftime("%Y-%m-%d %H:%M:%S", timeArray)
                                # _log.debug(f"服务器时间：{otherStyleTime}")
                                if local_time >= time_key:  # 本地时间大于服务器时间
                                    # self.mqtt.client.loop_stop()
                                    msg_list.append("该工具有效期至：")
                                    msg_list.append(otherStyleTime)
                                    msg_list.append("已过有效期，请联系美斯特光电,并提供用户名！")
                                    # _log.debug("有效期已过！！")
                                    while_flg = False  # 主循环退出
                                else:
                                    while_flg = True  # 主循环继续
                                    if self.old_usr_passwd != self.usr_passwd:  # 登录成功，本地保存用户名密码
                                        _log.debug(f"登录成功，保存用户名密码：{self.usr_passwd}")
                                        self.save_config(self.usr_passwd)
                                        self.old_usr_passwd = self.usr_passwd
                                    self.signal_text_change.emit("")  # 返回空，登录成功，关闭登录界面

                                    if usrs_dict[self.usr_passwd][1] == "FF:FF:FF:FF:FF:FF" or usrs_dict[self.usr_passwd][1] != self.mac:
                                        msg = self.bind_mac(self.usr_passwd, self.mac) #绑定MAC
                                        _log.error(type(msg))
                                        msg_list.append(msg)

                                    sleep(success_sleep)  # 休眠，防止频繁访问服务器
                                    break  # 跳出错误循环
                            else:
                                # _log.debug("MAC地址已绑定！！")
                                msg_list.append("MAC地址已绑定，请联系美斯特光电,并提供用户名")
                        else:
                            # _log.debug("用户名或密码错误！！")
                            msg_list.append("用户名或密码错误！！")
                            _log.debug("用户名或密码错误！！")
                            while_flg = False  # 主循环退出
                        if i == err_count - 1:  # 最后一次校验
                            _log.debug("最后一次校验,主循环退出")
                            while_flg = False  # 主循环退出

                sleep(err_sleep)  # 错误休眠间隔
                # print(f"第{i+1}次校验，休眠{err_sleep}秒")
            if err_count == 1:  # 首次登录结束
                err_count = 3  # 循环次数

        self.signal_text_change.emit(msg_list)  # 显示错误信息
        self.signal_login_success.emit(True)  # 登录按钮使能

    def get_mysql_usr(self):
        """从数据库中获取数据"""
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    order ="""
                            SELECT `用户名`, `密码`, `有效期`, `mac绑定` 
                            FROM sys_user
                            """
                    cursor.execute(order)
                    rows = cursor.fetchall()
            usr_dicts = dict()
            for row in rows:
                # _log.debug(f"数据库用户数据：{row}")
                mac_list = row['mac绑定'].split(',')
                usr_dicts[row['用户名']+" "+row['密码']] = [row['有效期'].strftime("%Y-%m-%d"), mac_list] # usr_dicts[用户名 密码] = [有效期,[mac1,mac2]]
            return usr_dicts
        except Exception as e:
            _log.error(f"从数据库中获取用户数据失败：{str(e)}")
            import traceback
            traceback.print_exc()



    def bind_mac(self, usr_passwd, mac_addresses):
        """更新数据库中MAC地址"""
        try:
            mac_address = ','.join(str(item) for item in mac_addresses)
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    order ="UPDATE sys_user SET MAC绑定 = %s  WHERE 用户名 =%s  AND 密码 = %s;"
                    # 执行
                    cursor.execute(order, (mac_address, usr_passwd.split(" ")[0], usr_passwd.split(" ")[1]))
                    conn.commit()
                    # 受影响行数
                    affect_rows = cursor.rowcount
            if affect_rows != 1:
                _log.error("数据库MAC更新失败")
                return "数据库MAC更新失败"
            else:
                return ""
        except Exception as e:
            _log.error(f"数据库中MAC更新报错：{str(e)}")
            return f"数据库中MAC更新报错：{str(e)}"

    def get_webtime(self):
        """获取网络时间"""
        """从指定NTP服务器获取时间"""

        servers = [
            'ntp.aliyun.com',  # 阿里云NTP服务器
            'time1.cloud.tencent.com',  # 腾讯云NTP服务器
            'cn.ntp.org.cn',  # 中国NTP公共服务器
            "ntp.ntsc.ac.cn",
        ]
        client = ntplib.NTPClient()
        # 发送请求并获取响应
        for server in servers:
            try:
                response = client.request(server, timeout=10)
                # NTP时间是从1900年1月1日开始的秒数，转换为Unix时间戳（1970年开始）
                ntp_timestamp = int(str(response.tx_time).split(".")[0])
                return ntp_timestamp
            except ntplib.NTPException:
                _log.error(f"连接{server}失败")
                continue
            else:
                break

    def get_all_macs_with_netifaces(self):
        mac_addresses = []
        # 获取所有网络接口名称
        interfaces = psutil.net_if_addrs()
        for interface_name, interface_addresses in interfaces.items():
            for address in interface_addresses:
                # 找到物理网卡的 MAC 地址（排除虚拟网卡）
                if address.family == -1 and address.address != "00:00:00:00:00:00":
                    # 过滤掉虚拟网卡、VMware、Loopback
                    if "virtual" in interface_name.lower() or "loop" in interface_name.lower():
                        continue
                    mac_addresses.append(address.address.upper())
        return mac_addresses

    def is_physical_mac(self,mac_address):
        """
        判断一个MAC地址是否为物理地址（非虚拟/无效地址）

        Args:
            mac_address: MAC地址字符串

        Returns:
            bool: 是否为物理地址
        """
        if not mac_address:
            return False

        # 1. 检查MAC地址格式是否合法
        mac_pattern = compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
        if not mac_pattern.match(mac_address):
            return False

        # 2. 排除全零MAC地址
        if mac_address.replace(':', '').replace('-', '').lower() == '000000000000':
            return False

        # 3. 排除常见的虚拟/保留MAC地址前缀
        virtual_prefixes = [
            '00:05:69',  # VMware
            '00:0C:29',  # VMware
            '00:50:56',  # VMware
            '00:1C:42',  # Parallels
            '00:15:5D',  # Hyper-V
            '00:03:FF',  # Microsoft VPN
            '02:00:00',  # VPN
            'FE:ED:FA',  # VirtualBox
            '00:1A:79',  # VirtualBox
        ]

        mac_lower = mac_address.lower()
        for prefix in virtual_prefixes:
            if mac_lower.startswith(prefix.lower()):
                return False

        # 4. 检查管理位和广播位（可选）
        # 第一个字节的第二位为0表示是全局唯一的物理地址
        first_byte = int(mac_lower.split(':')[0], 16)
        if (first_byte & 0x02) == 0x02:  # 本地管理地址（通常是虚拟地址）
            return False

        return True


if __name__ == "__main__":
    # """暗文转明文"""
    # text = "1de431c8ffb2b1be60f569f0d97aeb340fce1a4c870a6153098059f8366d51724f2eb7b348048efb5e00aade466693e5"
    # BLOCK_SIZE = 16
    # key = "MOSOMOSOMOSOMOSO"
    # decipher = AES.new(key.encode('utf8'), AES.MODE_ECB)
    # msg_dec = decipher.decrypt(bytes.fromhex(text))
    # print(str(unpad(msg_dec, BLOCK_SIZE), encoding='utf-8'))
    # # 追踪print打印位置
    # old_f = sys.stdout
    # import traceback
    # class F:
    #     def write(self, x):
    #         old_f.write(x.replace("\n", " [%s]\n" % str(traceback.extract_stack())))
    # sys.stdout = F()
    # def except_hook(cls, exception, ttraceback):
    #     """重写UI闪退导致无法日志输出问题"""
    #     import traceback
    #     err_msg = ""
    #     for index, msg_list in enumerate(traceback.format_exception(cls, exception, ttraceback)):
    #         if index != 0:
    #             for index, v in enumerate(msg_list.split("\n")):
    #                 if index != len(msg_list.split("\n")):
    #                     if v != "":
    #                         err_msg += "                            " + v + "\n"
    #         else:
    #             err_msg += msg_list
    #     _log.error(err_msg)

    # url = "127.0.0.1:81/licenses.txt"
    # print(url)
    # get_url_content()
    import sys
    # old_f = sys.stdout
    # import traceback
    # class F:
    #     def write(self, x):
    #         old_f.write(x.replace("\n", " [%s]\n" % str(traceback.extract_stack())))
    # sys.stdout = F()
    from PyQt6.QtCore import QCoreApplication, Qt
    from PyQt6.QtWidgets import QApplication


    def except_hook(cls, exception, traceback):
        """重写UI闪退导致无法日志输出问题"""
        sys.__excepthook__(cls, exception, traceback)


    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)

    myWin = LogIn()
    myWin.show()

    sys.excepthook = except_hook
    sys.exit(app.exec())