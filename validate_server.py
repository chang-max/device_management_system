import os
import time
import datetime
import json
import logging
import pymysql
from pymysql.cursors import DictCursor

# ====================== 配置 ======================
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "123456"
DB_NAME = "device_management"

# 设备列表文件
DEVICE_LIST_FILE = "device_list.txt"

# 验证时间范围（默认当天）
VALIDATE_DATE = datetime.date.today()

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('validate_server.log', encoding='utf-8'),
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
        logger.info(f"成功加载 {len(sn_list)} 个设备")
    else:
        logger.error(f"设备列表文件不存在: {DEVICE_LIST_FILE}")
    return sn_list

def get_table_count(cursor, table_name):
    """获取表记录数"""
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM `{table_name}`")
        result = cursor.fetchone()
        return result.get('count', 0)
    except Exception as e:
        logger.error(f"查询表 {table_name} 失败: {e}")
        return -1

def get_parsed_data(cursor, table_name, date):
    """获取解析表指定日期的数据"""
    try:
        cursor.execute(
            f"SELECT * FROM `{table_name}` WHERE `日期` = %s",
            (date,)
        )
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"查询解析表 {table_name} 失败: {e}")
        return None

def get_raw_data_stats(cursor, table_name, date):
    """获取原始表指定日期的统计信息"""
    try:
        # 统计记录数
        cursor.execute(
            f"SELECT COUNT(*) as count FROM `{table_name}` WHERE DATE(`datetime`) = %s",
            (date,)
        )
        count = cursor.fetchone().get('count', 0)
        
        # 统计告警数
        cursor.execute(
            f"SELECT COUNT(*) as alarm_count FROM `{table_name}` WHERE DATE(`datetime`) = %s AND JSON_EXTRACT(`data`, '$.CT') = 'A'",
            (date,)
        )
        alarm_count = cursor.fetchone().get('alarm_count', 0)
        
        return {
            'count': count,
            'alarm_count': alarm_count
        }
    except Exception as e:
        logger.error(f"统计原始表 {table_name} 失败: {e}")
        return {'count': 0, 'alarm_count': 0}

# ====================== 验证函数 ======================
def validate_raw_tables(sn_list, date):
    """验证原始数据表"""
    logger.info("开始验证原始数据表...")
    
    total_devices = len(sn_list)
    success_devices = 0
    total_records = 0
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for sn in sn_list:
                table_name = sn
                count = get_table_count(cursor, table_name)
                
                if count >= 0:
                    success_devices += 1
                    total_records += count
                    logger.info(f"设备 {sn} 原始表记录数: {count}")
                else:
                    logger.error(f"设备 {sn} 原始表不存在或查询失败")
    
    logger.info(f"原始表验证完成: 成功 {success_devices}/{total_devices} 设备，总记录数 {total_records}")
    return success_devices, total_records

def validate_parsed_tables(sn_list, date):
    """验证解析数据表"""
    logger.info("开始验证解析数据表...")
    
    total_devices = len(sn_list)
    success_devices = 0
    parsed_data_list = []
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for sn in sn_list:
                table_name = f"{sn}_parsed"
                parsed_data = get_parsed_data(cursor, table_name, date)
                
                if parsed_data:
                    success_devices += 1
                    
                    # 同时获取原始表统计
                    raw_stats = get_raw_data_stats(cursor, sn, date)
                    
                    parsed_data_list.append({
                        'sn': sn,
                        'parsed': parsed_data,
                        'raw_stats': raw_stats
                    })
                    
                    logger.info(f"设备 {sn} 解析表数据: 在线={parsed_data['在线情况']}, 电能={parsed_data['当天累计电能']}, 告警={parsed_data['告警条数']}")
                else:
                    logger.error(f"设备 {sn} 解析表不存在或查询失败")
    
    logger.info(f"解析表验证完成: 成功 {success_devices}/{total_devices} 设备")
    return success_devices, parsed_data_list

def validate_data_consistency(parsed_data_list):
    """验证数据一致性"""
    logger.info("开始验证数据一致性...")
    
    consistency_issues = []
    
    for item in parsed_data_list:
        sn = item['sn']
        parsed = item['parsed']
        raw_stats = item['raw_stats']
        
        # 验证告警条数
        if parsed['告警条数'] != raw_stats['alarm_count']:
            consistency_issues.append({
                'sn': sn,
                'issue': f"告警条数不一致: 解析表={parsed['告警条数']}, 原始表统计={raw_stats['alarm_count']}"
            })
        
        # 验证在线情况
        if parsed['在线情况'] != 1 and raw_stats['count'] > 0:
            consistency_issues.append({
                'sn': sn,
                'issue': f"在线情况异常: 解析表={parsed['在线情况']}, 原始表有{raw_stats['count']}条记录"
            })
        
        # 验证电能数据
        if parsed['最低累计电能'] > parsed['最高累计电能']:
            consistency_issues.append({
                'sn': sn,
                'issue': f"电能数据异常: 最低={parsed['最低累计电能']} > 最高={parsed['最高累计电能']}"
            })
    
    if consistency_issues:
        logger.warning(f"发现 {len(consistency_issues)} 个一致性问题:")
        for issue in consistency_issues:
            logger.warning(f"设备 {issue['sn']}: {issue['issue']}")
    else:
        logger.info("数据一致性验证通过，未发现问题")
    
    return len(consistency_issues) == 0

# ====================== 主函数 ======================
def main():
    logger.info("=" * 60)
    logger.info("开始验证 server.py 数据处理")
    logger.info("=" * 60)
    
    # 1. 加载设备列表
    sn_list = load_device_list()
    if not sn_list:
        logger.error("未找到设备列表，验证失败")
        return
    
    # 2. 验证原始数据表
    raw_success, total_records = validate_raw_tables(sn_list, VALIDATE_DATE)
    
    # 3. 验证解析数据表
    parsed_success, parsed_data_list = validate_parsed_tables(sn_list, VALIDATE_DATE)
    
    # 4. 验证数据一致性
    consistency_ok = validate_data_consistency(parsed_data_list)
    
    # 5. 生成验证报告
    logger.info("\n" + "=" * 60)
    logger.info("验证报告")
    logger.info("=" * 60)
    logger.info(f"验证日期: {VALIDATE_DATE}")
    logger.info(f"设备总数: {len(sn_list)}")
    logger.info(f"原始表验证: {raw_success}/{len(sn_list)} 设备成功")
    logger.info(f"解析表验证: {parsed_success}/{len(sn_list)} 设备成功")
    logger.info(f"总原始记录: {total_records}")
    logger.info(f"数据一致性: {'通过' if consistency_ok else '失败'}")
    
    if raw_success == len(sn_list) and parsed_success == len(sn_list) and consistency_ok:
        logger.info("✅ 所有验证通过！server.py 运行正常")
    else:
        logger.warning("⚠️  验证发现问题，需要检查 server.py")
    
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
