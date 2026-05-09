import os
import time
import datetime
import pymysql
from pymysql.cursors import DictCursor

# ====================== 配置 ======================
DB_HOST = "112.64.32.181"
DB_PORT = 3311
DB_USER = "root"
DB_PASSWORD = "MST@2026!"
DB_NAME = "MST_SQL"

# 设备列表文件
DEVICE_LIST_FILE = "device_list.txt"
MAX_DEVICE_COUNT = 996

# 用户名配置


PRIMARY_USER = "常芝南"
PRIMARY_USER_RATIO = 1  # 四分之一用户名为常芝南

# 其他用户前缀
ROBOT_PREFIX = "机器人"

# 日志配置
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('insert_device_info.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================== 数据库连接 ======================
def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset='utf8mb4',
        cursorclass=DictCursor
    )

# ====================== 工具函数 ======================
def load_device_list():
    """加载设备列表"""
    sn_list = []
    if os.path.exists(DEVICE_LIST_FILE):
        logger.info(f"加载设备列表文件: {DEVICE_LIST_FILE}")
        with open(DEVICE_LIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "| SN：" in line:
                    sn = line.split("| SN：")[1].strip()
                    sn_list.append(sn)
                    if len(sn_list)>= MAX_DEVICE_COUNT:
                        break
        logger.info(f"成功加载 {len(sn_list)} 个设备")
    else:
        logger.error(f"设备列表文件不存在: {DEVICE_LIST_FILE}")
    return sn_list

def get_device_info(cursor, sn):
    """检查设备是否已存在"""
    try:
        cursor.execute("SELECT * FROM device_info WHERE 设备号 = %s", (sn,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"查询设备 {sn} 失败: {e}")
        return None

def insert_device_info(cursor, sn, username, add_time,index):
    """插入设备信息"""
    try:
        # 插入设备信息（使用实际表字段）
        sql = """
            INSERT INTO device_info (
                `设备号`, `设备名称`, `账户`, `日期`, `区域1`, `区域2`, `区域3`, `工作计划`,`经度`,`纬度`,`时区`
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            sn,                          # 设备号
            f"设备-{f"{index+1:03d}"}",            # 设备名称（使用索引编号）
            username,                    # 账户
            add_time,                    # 日期
            None,                        # 区域1
            None,                        # 区域2
            None,                        # 区域3
            '{}',                        # 工作计划（空JSON对象）
            121.473700,                        # 经度
            31.230400,                        # 纬度
            8                         # 时区
        ))
        return True
    except Exception as e:
        logger.error(f"插入设备 {sn} 失败: {e}")
        return False

# ====================== 主函数 ======================
def main():
    logger.info("=" * 60)
    logger.info("开始插入设备信息到 device_info 表")
    logger.info("=" * 60)
    
    # 1. 加载设备列表
    sn_list = load_device_list()
    if not sn_list:
        logger.error("未找到设备列表，插入失败")
        return
    
    # 2. 计算四分之一设备数量
    total_devices = len(sn_list)
    primary_count = 996
    logger.info(f"总设备数: {total_devices}")
    logger.info(f"常芝南设备数: {primary_count}")
    logger.info(f"机器人数: {total_devices - primary_count}")
    
    # 3. 插入数据
    success_count = 0
    skip_count = 0
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for i, sn in enumerate(sn_list):
                # 检查设备是否已存在
                existing = get_device_info(cursor, sn)
                if existing:
                    logger.info(f"设备 {sn} 已存在，跳过")
                    skip_count += 1
                    continue
                
                # 确定用户名
                # if i < primary_count:
                username = PRIMARY_USER
                # else:
                #     username = f"{ROBOT_PREFIX}{i - primary_count + 1}"
                
                # 生成添加时间（当前时间）
                add_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 插入数据
                if insert_device_info(cursor, sn, username, add_time,i):
                    success_count += 1
                    logger.info(f"成功插入设备 {sn} (账户: {username})")
                
                # 每10条提交一次
                if (i + 1) % 10 == 0:
                    conn.commit()
                    logger.info(f"已提交 {i + 1} 条记录")
            
            # 最后提交
            conn.commit()
    
    # 4. 生成插入报告
    logger.info("\n" + "=" * 60)
    logger.info("插入报告")
    logger.info("=" * 60)
    logger.info(f"总设备数: {total_devices}")
    logger.info(f"成功插入: {success_count}")
    logger.info(f"已存在跳过: {skip_count}")
    logger.info(f"插入失败: {total_devices - success_count - skip_count}")
    
    if success_count > 0:
        logger.info("✅ 插入完成！")
    else:
        logger.warning("⚠️  无新设备插入")
    
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
