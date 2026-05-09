import json
from tkinter import N
from PyQt6.QtGui import QStandardItem
from PyQt6.QtCore import Qt,QDateTime
from datetime import datetime, date, timedelta
from functools import partial
import traceback
from datetime import UTC
from configparser import ConfigParser



from log_save import Logger
_log = Logger(True).logger


from PIL import Image, ImageEnhance

def clean_process_image(input_path, output_path):
    # 打开图片（保留透明）
    img = Image.open(input_path).convert("RGBA")
    pixels = img.load()
    width, height = img.size

    # 逐像素处理（最清晰、最精准，不会模糊）
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            # --------------------------
            # 规则1：红色 → 强制青色（高饱和度）
            # --------------------------
            if r > 100 and g < 180 and b < 180 and r > g + 30 and r > b + 30:
                pixels[x, y] = (0, 255, 255, a)
                continue

            # --------------------------
            # 规则2：黑白颠倒（保持锐利）
            # --------------------------
            # 白色 → 黑
            if r > 200 and g > 200 and b > 200:
                pixels[x, y] = (0, 0, 0, a)
            # 黑色 → 白
            elif r < 50 and g < 50 and b < 50:
                pixels[x, y] = (255, 255, 255, a)
            # 灰色线条 → 反转保持清晰
            else:
                pixels[x, y] = (255 - r, 255 - g, 255 - b, a)

    # 增强清晰度和对比度
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)  # 提高对比度
    
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)  # 提高锐度

    return img



def get_err_config(path):
    """
    获取错误对应信息
    """
    get_dict = dict()
    conf = ConfigParser()  # 需要实例化一个ConfigParser对象
    conf.read(path, encoding='utf-8')  # 需要添加上config.ini的路径，不需要open打开，直接给文件路径就读取，也可以指定encoding='utf-8'
    for key,v in conf["error_list"].items():
        get_dict[int(key)] = v.strip()


    return get_dict,conf["set_flg"]["rti_flg"]
    

def get_area_dict(usr, db_pool):
    """从数据库中获取区域字典"""
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 区域信息 FROM sys_user WHERE 用户名 = %s", (usr,))
            return json.loads(cursor.fetchone()['区域信息']) 

# def update_device_mode_config(usr, db_pool,proxy):
#     """
#         从数据库中获取数据，更新设备配置表格模型数据
#     """
#     with db_pool.connection() as conn:
#         with conn.cursor() as cursor:
#             cursor.execute("SELECT 设备名称, 设备号, 日期, 区域1, 区域2, 区域3,经度,纬度,时区,地址, 工作计划 FROM device_info WHERE 账户 = %s", (usr,))
#             rows = cursor.fetchall()
#             for row in rows:
#                 add_device_mode_config(proxy, row['设备号'], row['设备名称'], row['日期'].strftime("%Y-%m-%d %H:%M:%S"), row['区域1'], row['区域2'], row['区域3'], row['工作计划'])

def get_col_apply(db_pool):
    """
    获取数据库应用列信息
    """
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            config = {} # 用于获取MQTT接收数据时的列名以及数据类型
            key_cols = {}  # 用于获取MQTT接收数据时的key值以及数据类型
            FLOAT_cols = []  # 用于获取MQTT接收数据时的整型数据列名
            DATETIME_cols = []  # 用于获取MQTT接收数据时的日期时间列名

            query_sql = "SELECT `列名`,`数据类型`,`键名`,`小数位`,`单位` FROM config "
            cursor.execute(query_sql)
            results = cursor.fetchall()
            for row in results:
                # print(row["列名"])
                key = ""
                if row["单位"] is not None:
                    key = row["列名"] + "(" + row["单位"] + ")"
                else:
                    key = row["列名"]
                if "INT" in row["数据类型"] or "FLOAT" in row["数据类型"]:
                    FLOAT_cols.append(row["列名"])
                elif "DATETIME" in row["数据类型"]:
                    DATETIME_cols.append(row["列名"])

                if row["键名"] is not None:
                    keys = []
                    for msg_key in row["键名"].split(" "):
                        try:
                            keys.append(int(msg_key))
                        except ValueError:
                            keys.append(msg_key)

                    config.setdefault(key, [keys, row["数据类型"], row["小数位"]])
                    key_cols.setdefault(key, [keys, row["数据类型"], row["小数位"]])

                else:
                    config.setdefault(key, [[], row["数据类型"], row["小数位"]])
                    key_cols.setdefault(key, [[], row["数据类型"], row["小数位"]])

            config.setdefault("当前时间", [])
            # config.setdefault("老化状态", [])

            key_cols.pop("原始数据")
            config.pop("原始数据")

            return config, key_cols, FLOAT_cols, DATETIME_cols
    return None, None, None, None



def add_device_default_row(proxy, apply_col_config,device):
    """添加设备行到统一模型"""
    data = []
    # 应用勾选（第一列，应用视图使用）
    app_check_item = QStandardItem()
    app_check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
    app_check_item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    data.append(app_check_item)

    # 管理勾选（第二列，设备管理视图使用）
    check_item = QStandardItem()
    check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
    check_item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    data.append(check_item)

    # 设备号
    item = QStandardItem(device.get("设备号", ""))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)

    # 设备名称
    item = QStandardItem(device.get("设备名称", ""))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)

    # 区域1、2、3
    for area_col in ["区域1", "区域2", "区域3"]:
        item = QStandardItem(device.get(area_col, ""))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        data.append(item)

    # X坐标
    item = QStandardItem(str(device.get("相对x", "")))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)
    # Y坐标
    item = QStandardItem(str(device.get("相对y", "")))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)


    # 添加日期
    add_date = device.get("日期", "")
    # 将 datetime 转换为字符串
    if hasattr(add_date, 'strftime'):
        add_date = add_date.strftime("%Y-%m-%d %H:%M:%S")
    item = QStandardItem(str(add_date))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)

    # 工作计划
    work_plan = device.get("工作计划", "{}")
    item = QStandardItem(json.dumps(json.loads(work_plan or "{}"), ensure_ascii=False, indent=2))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    data.append(item)

    # 编辑、删除占位
    for _ in range(2):
        item = QStandardItem("")
        data.append(item)
    
    # 动态列（调光值等）
    for col_name in apply_col_config.keys():
        item = QStandardItem("-")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        data.append(item)
    
    # 历史数据
    item = QStandardItem("")
    data.append(item)
    
    proxy.appendRow(data)


def is_in_item(proxy, sub_index, target_str):
    """
        检查指定字符串是否在子列表的第指定个元素中
    """
    row_count = proxy.rowCount()
    if row_count == 0:
        return False
    # 遍历每个子列表
    for row in range(row_count):
        item = proxy.item(row, sub_index)
        if item and item.text() == target_str:
            return True
    return False


def get_device_data_count(db_pool, dev_id, date_day):
    """
        获取指定设备在指定日期内的数据库对应数据表内条数数
    """
    next_day = datetime.strptime(date_day, "%Y-%m-%d") + timedelta(days=1)
    next_day = next_day.strftime("%Y-%m-%d")
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            # 优化：使用 LIMIT 1 替代 COUNT(*)，找到第一条即返回
            cursor.execute(f"SELECT 1 FROM `{dev_id}` WHERE datetime >= %s AND datetime <= %s LIMIT 1", (date_day, next_day))
            result = cursor.fetchone()
            return 1 if result else 0
    

def get_device_Ec_value(db_pool,dev_id,date_day):
    """
        获取指定设备在指定日期内的EC列表差值
        逻辑：当天最晚的累计电能 - 当天最早的累计电能
    """
    order = f"""
    SELECT
    -- 最早时间：没有数据则返回 NULL
    MIN(datetime) AS earliest_time,
    -- 最早 tEc：无数据则返回 [0]
    IFNULL(
        JSON_UNQUOTE(MIN(data->'$.DT.EleInfo.tEc')),
        '[0]'
    ) AS earliest_tEc,

    -- 最晚时间
    MAX(datetime) AS latest_time,
    -- 最晚 tEc：无数据则返回 [0]
    IFNULL(
        JSON_UNQUOTE(MAX(data->'$.DT.EleInfo.tEc')),
        '[0]'
    ) AS latest_tEc

    FROM `{dev_id}` 
    WHERE 
        DATE(datetime) = '{date_day}'
        AND data->'$.DT.EleInfo.tEc' IS NOT NULL;
    """
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(order)
            row = cursor.fetchone()
            earliest_tEc = row["earliest_tEc"]
            latest_tEc = row["latest_tEc"]
            # 计算差值：最晚 - 最早（确保非负）
            try:
                earliest_val = eval(earliest_tEc)[0]
                latest_val = eval(latest_tEc)[0]
                diff = latest_val - earliest_val
                return diff if diff >= 0 else 0  # 确保非负
            except (SyntaxError, IndexError, TypeError):
                return 0


def get_real_time_online_flg(db_pool, dev_id,time_diff):
    """
        获取指定设备的最新数据时间与当前时间差值
    """
    order = f"SELECT datetime FROM `{dev_id}`ORDER BY datetime DESC LIMIT 1;"
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(order)
            row = cursor.fetchone()
            if row != None:
                newest_time = row['datetime']
            else:
                newest_time = None
                return False  # 离线
    # _log.debug(f"最新数据时间：{newest_time}")
    # _log.debug(f"当前时间：{datetime.now()}")
    # _log.debug(f"差值：{datetime.now() - newest_time}")
    # _log.debug(f"时间差：{timedelta(seconds=time_diff)}")

    if datetime.now() - newest_time < timedelta(seconds=time_diff):  # 最新数据时间在当前时间之前
        return True  # 在线
    else:
        return False  # 离线


# ===================== 从 _parsed 表获取数据的新函数 =====================

def get_parsed_online_status(db_pool, dev_id, date_day):
    """
        从 _parsed 表获取指定设备在指定日期的在线状态
        返回：1 表示在线，0 表示离线
    """
    table_name = f"{dev_id}_parsed"
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                # 查询指定日期的在线情况
                cursor.execute(
                    f"SELECT `在线情况` FROM `{table_name}` WHERE DATE(`时间`) = %s LIMIT 1",
                    (date_day,)
                )
                row = cursor.fetchone()
                if row and row['在线情况']:
                    return 1
                return 0
    except Exception as e:
        # 表不存在或其他错误，返回离线
        return 0


def get_parsed_electricity(db_pool, dev_id, date_day):
    """
        从 _parsed 表获取指定设备在指定日期的累计电能
        返回：当天累计电能（最高 - 最低）
    """
    table_name = f"{dev_id}_parsed"
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                # 查询指定日期的当天累计电能
                cursor.execute(
                    f"SELECT `当天累计电能` FROM `{table_name}` WHERE DATE(`时间`) = %s LIMIT 1",
                    (date_day,)
                )
                row = cursor.fetchone()
                if row and row['当天累计电能'] is not None:
                    return int(row['当天累计电能'])
                return 0
    except Exception as e:
        # 表不存在或其他错误，返回0
        return 0


def get_parsed_realtime_online(db_pool, dev_id, time_diff):
    """
        从 _parsed 表获取设备的实时在线状态
        根据最新一条记录的在线情况判断
    """
    table_name = f"{dev_id}_parsed"
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                # 查询最新一条记录的时间和在线情况
                cursor.execute(
                    f"SELECT `时间`, `在线情况` FROM `{table_name}` ORDER BY `时间` DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    newest_time = row['时间']
                    online_status = row['在线情况']
                    # 检查时间差
                    if datetime.now() - newest_time < timedelta(seconds=time_diff):
                        return bool(online_status)
                return False
    except Exception as e:
        return False


def get_parsed_data_batch(db_pool, dev_id, date_day):
    """
        从 _parsed 表批量获取指定设备在指定日期的在线状态和累计电能
        返回：(is_online, electricity) 元组
        - is_online: 1 表示在线，0 表示离线
        - electricity: 当天累计电能
    """
    table_name = f"{dev_id}_parsed"
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT `在线情况`, `当天累计电能` FROM `{table_name}` WHERE DATE(`日期`) = %s LIMIT 1",
                    (date_day,)
                )
                row = cursor.fetchone()
                if row:
                    is_online = 1 if row['在线情况'] else 0
                    electricity = int(row['当天累计电能']) if row['当天累计电能'] is not None else 0
                    return (is_online, electricity)
                return (0, 0)
    except Exception as e:
        return (0, 0)


def get_parsed_all_data(db_pool, dev_id, date_day, time_diff, is_today=False):
    """
        从 _parsed 表统一获取设备的所有图表数据（优化为单次查询）
        参数：
            is_today: 是否查询今天数据，如果是则需要判断实时在线状态
        返回：(is_online_day, electricity, is_realtime_online, power, power_time) 元组
        - is_online_day: 指定日期是否在线（1/0）
        - electricity: 指定日期累计电能
        - is_realtime_online: 实时在线状态（仅当 is_today=True 时有效）
        - power: 功率值
        - power_time: 功率时间
    """
    table_name = f"{dev_id}_parsed"
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                # 单次查询获取：在线情况、当天累计电能、最新时间、功率、功率时间
                cursor.execute(
                    f"SELECT `在线情况`, `当天累计电能`, `最新时间`, `功率`, `功率时间` "
                    f"FROM `{table_name}` WHERE `日期` = %s LIMIT 1",
                    (date_day,)
                )
                row = cursor.fetchone()

                if not row:
                    return (0, 0, False, 0, None)

                is_online_day = 1 if row['在线情况'] else 0
                electricity = int(row['当天累计电能']) if row['当天累计电能'] is not None else 0
                power = int(row['功率']) if row['功率'] is not None else 0
                power_time = row['功率时间']

                # 只有查询今天数据时才判断实时在线状态
                is_realtime_online = False
                if is_today and row['最新时间']:
                    if datetime.now() - row['最新时间'] < timedelta(seconds=time_diff):
                        is_realtime_online = bool(row['在线情况'])

                return (is_online_day, electricity, is_realtime_online, power, power_time)
    except Exception as e:
        return (0, 0, False, 0, None)


def get_total_power_within_minutes(db_pool, devices_info, minutes=60):
    """
    计算指定时间内（默认60分钟）所有在线设备的有效功率之和
    优化：使用单连接批量查询，减少连接池开销
    参数：
        db_pool: 数据库连接池
        devices_info: 设备信息列表 [(dev_id, add_datetime), ...]
        minutes: 时间窗口（分钟），默认60分钟
    返回：
        total_power: 有效功率之和（只统计功率时间在指定时间内的设备）
        valid_device_count: 有效设备数量
    """
    total_power = 0
    valid_device_count = 0
    time_threshold = datetime.now() - timedelta(minutes=minutes)
    today = datetime.now().strftime("%Y-%m-%d")

    # 使用单连接批量查询所有设备
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cursor:
                for dev_id, _ in devices_info:
                    table_name = f"{dev_id}_parsed"
                    try:
                        cursor.execute(
                            f"SELECT `功率`, `功率时间` FROM `{table_name}` WHERE `日期` = %s LIMIT 1",
                            (today,)
                        )
                        row = cursor.fetchone()

                        if row and row['功率时间']:
                            power_time = row['功率时间']
                            # 检查功率时间是否在指定时间内
                            if power_time >= time_threshold:
                                power = int(row['功率']) if row['功率'] is not None else 0
                                total_power += power
                                valid_device_count += 1
                    except Exception:
                        # 忽略单个设备查询失败的情况
                        continue
    except Exception as e:
        _log.error(f"批量查询功率数据失败: {e}")

    return total_power, valid_device_count


def get_time(flg):
    """
    获取当前时间
    """
    if flg == "now":  # 当前时间
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif flg == "UTC":  # UTC时间
        time = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    elif flg == "name":  # 当前时间下划线格式
        time = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    elif flg == "timestamp":  # 当前时间戳
        time = int(datetime.now().timestamp())
    return time


def list_before_deadline(model, datetime_str,dev_index,dete_index):
    """
    统计 QStandardItemModel 中日期 ≤ 指定时间的数据条数
    :param model: 数据模型（必须包含“日期”列）
    :param datetime_str: 截止时间字符串，格式：yyyy-MM-dd HH:mm:ss
    :param dev_index: 对应设备号列下标
    :param dete_index: 对应日期列下标
    :return: 符合条件的列表
    """
    DATE_COLUMN = dete_index
    
    # 把传入的字符串转为 QDateTime
    deadline = QDateTime.fromString(datetime_str, "yyyy-MM-dd HH:mm:ss")

    if not deadline.isValid():
        _log.error(f"截止时间：{datetime_str} 格式错误格式错误")
        return []   

    devices = []
    row_count = model.rowCount()

    # 遍历每一行判断
    for row in range(row_count):
        index = model.index(row, DATE_COLUMN)
        date_str = index.data(Qt.ItemDataRole.DisplayRole)

        if not date_str:
            continue

        # 解析当前行的时间
        item_dt = QDateTime.fromString(date_str, "yyyy-MM-dd HH:mm:ss")
        if item_dt.isValid() and item_dt <= deadline:
            text = model.item(row, dev_index).text()
            devices.append(text)
    return devices



if __name__ == '__main__':
    from dbutils.pooled_db import PooledDB
    import pymysql
    from pymysql.cursors import DictCursor
    pool1 = PooledDB(
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
    config, key_cols, history_cols, FLOAT_cols, DATETIME_cols = get_col_apply(pool1)
    # print(config)
    print(key_cols)
    # print(history_cols)
    # print(FLOAT_cols)
    # print(DATETIME_cols)

