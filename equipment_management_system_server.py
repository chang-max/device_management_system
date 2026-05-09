#!/usr/bin/env python3
"""
设备数据接收服务端 - 万级设备高并发优化版
基于 Redis 内存队列 + MySQL Executemany 批量入库 + 统一分区大表
"""
import os
import sys
import json
import signal
import traceback
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta
from time import sleep
import random

import pymysql
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
import paho.mqtt.client as mqtt
from redis import Redis

# ===================== 配置管理 (保留您原有的配置项) =====================
class Config:
    host = 'localhost'
    DB_HOST = os.getenv('DB_HOST', host)
    DB_PORT = int(os.getenv('DB_PORT', '3311'))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'MST@2026!')
    DB_NAME = os.getenv('DB_NAME', 'MST_SQL')
    DB_CHARSET = 'utf8mb4'
    DB_MAX_CONNECTIONS = 50
    DB_MIN_CACHED = 10
    DB_MAX_CACHED = 20
    
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'MST@2026!')
    REDIS_DB = 0

    MQTT_HOST = os.getenv('MQTT_HOST', 'broker.emqx.io')
    MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
    MQTT_CLIENT_ID = f'MST_SERVER_{random.randint(1000, 9999)}'
    MQTT_QOS = 1

    THREAD_SLEEP_INTERVAL = 1
    DB_INSERTER_BATCH_SIZE = 1000  # 每次从 Redis 批量取出的最大条数
    PARSED_KEYS = {"电能": ["DT", "EleInfo", "tEc", 0], "功率": ["DT", "EleInfo", "p", 0]}

# ===================== 日志类 =====================
class SimpleLogger:
    def __init__(self):
        self.log_file = './server_optimized.log'
    def _write(self, level, msg):
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {level} - {msg}"
        print(line)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    def info(self, msg): self._write('INFO', msg)
    def debug(self, msg): self._write('DEBUG', msg)
    def warning(self, msg): self._write('WARNING', msg)
    def error(self, msg): self._write('ERROR', msg)

_log = SimpleLogger()

# ===================== MQTT 客户端 =====================
class MqttClient:
    def __init__(self, config, message_callback=None):
        self.broker, self.port, self.client_id, self.qos = config
        self.message_callback = message_callback
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._is_running = True

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            _log.info("MQTT 连接成功")
            # 使用通配符接收所有设备数据，在回调中判断
            # + 是单级通配符，匹配 MS/{device_id}/dev2plt 格式
            self.client.subscribe("MS/+/dev2plt", self.qos)

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload)
            if self.message_callback:
                self.message_callback(msg.topic, data)
        except Exception:
            pass

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def stop(self):
        self._is_running = False
        self.client.disconnect()
        self.client.loop_stop()

# ===================== 服务端主类 =====================
class Server:
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.shutdown_event = Event()
        
        self._init_db_pool()
        self._init_redis()
        self._init_mqtt()
        _log.info("服务端高并发优化版初始化完成")

    def _init_db_pool(self):
        self.db_pool = PooledDB(
            creator=pymysql, maxconnections=Config.DB_MAX_CONNECTIONS,
            mincached=Config.DB_MIN_CACHED, maxcached=Config.DB_MAX_CACHED,
            host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER,
            password=Config.DB_PASSWORD, database=Config.DB_NAME,
            charset=Config.DB_CHARSET, cursorclass=DictCursor, autocommit=False
        )

    def _init_redis(self):
        self.redis_client = Redis(
            host=Config.REDIS_HOST, port=Config.REDIS_PORT, 
            password=Config.REDIS_PASSWORD, db=Config.REDIS_DB, decode_responses=True
        )
        self.redis_client.ping()

    def _init_mqtt(self):
        self.client = MqttClient(
            [Config.MQTT_HOST, Config.MQTT_PORT, Config.MQTT_CLIENT_ID, Config.MQTT_QOS],
            message_callback=self._handle_message
        )
        self.client.start()

    def _handle_message(self, topic, data):
        """【优化】纯内存操作：极速压入 Redis 队列，彻底废弃 writing.log 文件"""
        try:
            dev_id = data.get("SN")
            if not dev_id: return
            
            packet = {
                "dev_id": dev_id,
                "sv": data.get("SV", ""),
                "ct": data.get("CT", ""),
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "payload": json.dumps(data)
            }
            # 推入 Redis 高速缓冲队列
            self.redis_client.rpush("queue:device_raw_data", json.dumps(packet))
            # 更新设备最新在线心跳 (TTL 3分钟)
            self.redis_client.setex(f"device:online:{dev_id}", 180, "1")
        except Exception as e:
            _log.error(f"处理 MQTT 消息入队失败: {e}")

    def _db_inserter_worker(self):
        """【优化】批量入库流水线：消费 Redis 队列，使用 executemany 批量插入统一大表"""
        _log.info("数据库批量入库线程已启动...")
        
        # 使用统一大表 device_data_raw (废弃原先的 {dev_id} 单表)
        sql_raw = """
            INSERT INTO device_data_raw (dev_id, sv, ct, report_time, data) 
            VALUES (%s, %s, %s, %s, %s)
        """
        # 使用统一大表 device_data_parsed
        sql_parsed = """
            INSERT INTO device_data_parsed 
            (dev_id, `日期`, `最新时间`, `在线情况`, `功率`, `功率时间`)
            VALUES (%s, %s, %s, 1, %s, %s)
            ON DUPLICATE KEY UPDATE 
            `最新时间` = VALUES(`最新时间`), `在线情况` = 1, 
            `功率` = IF(VALUES(`功率`) IS NOT NULL, VALUES(`功率`), `功率`),
            `功率时间` = IF(VALUES(`功率时间`) IS NOT NULL, VALUES(`功率时间`), `功率时间`)
        """
        
        while not self.shutdown_event.is_set():
            try:
                # 管道原子取出并修剪队列
                pipe = self.redis_client.pipeline()
                pipe.lrange("queue:device_raw_data", 0, Config.DB_INSERTER_BATCH_SIZE - 1)
                pipe.ltrim("queue:device_raw_data", Config.DB_INSERTER_BATCH_SIZE, -1)
                raw_items = pipe.execute()[0]

                if not raw_items:
                    sleep(0.5)
                    continue

                raw_params = []
                parsed_params = []
                
                for item_str in raw_items:
                    item = json.loads(item_str)
                    dev_id = item['dev_id']
                    rpt_time = item['time']
                    payload_json = json.loads(item['payload'])
                    
                    raw_params.append((dev_id, item['sv'], item['ct'], rpt_time, item['payload']))
                    
                    # 尝试解析功率
                    power = None
                    if item['ct'] not in ["A", "W"]:
                        try:
                            # 依据配置提取功率
                            p_data = payload_json
                            for k in Config.PARSED_KEYS["功率"]:
                                p_data = p_data[k]
                            power = p_data
                        except:
                            power = None
                            
                    parsed_params.append((dev_id, rpt_time[:10], rpt_time, power, rpt_time if power is not None else None))

                # 批量事务插入
                conn = self.db_pool.connection()
                with conn.cursor() as cursor:
                    cursor.executemany(sql_raw, raw_params)
                    cursor.executemany(sql_parsed, parsed_params)
                conn.commit()
                conn.close()
                _log.info(f"成功批量落库 {len(raw_params)} 条记录")

            except Exception as e:
                _log.error(f"批量入库失败: {e}")
                sleep(2)

    def _aggregate_account_daily_stats(self, account, target_date):
        """【优化】彻底废弃 UNION ALL 循环百张表，采用统一大表 device_data_parsed 查询"""
        try:
            date_str = target_date.strftime("%Y-%m-%d")
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 关联查询设备表和解析大表
                    sql = """
                        SELECT d.`设备号`, d.`区域1`, d.`区域2`, d.`区域3`, 
                               p.`在线情况` as `在线`, p.`当天累计电能` as `用电量`
                        FROM `device_info` d
                        LEFT JOIN `device_data_parsed` p 
                        ON d.`设备号` = p.dev_id AND p.`日期` = %s
                        WHERE d.`账户` = %s
                    """
                    cursor.execute(sql, (date_str, account))
                    devices = cursor.fetchall()

            # 内存中执行区域聚合（速度极快）
            area_stats = {"ALL": {"total": 0, "online": 0, "electricity": 0}}
            
            for dev in devices:
                online = 1 if dev['在线'] else 0
                elec = dev['用电量'] or 0
                
                area_stats["ALL"]["total"] += 1
                area_stats["ALL"]["online"] += online
                area_stats["ALL"]["electricity"] += elec
                
                # 组装区域路径
                paths = []
                if dev['区域1']:
                    paths.append(dev['区域1'])
                    if dev['区域2']:
                        paths.append(f"{dev['区域1']}/{dev['区域2']}")
                        if dev['区域3']:
                            paths.append(f"{dev['区域1']}/{dev['区域2']}/{dev['区域3']}")
                
                for path in paths:
                    if path not in area_stats:
                        area_stats[path] = {"total": 0, "online": 0, "electricity": 0}
                    area_stats[path]["total"] += 1
                    area_stats[path]["online"] += online
                    area_stats[path]["electricity"] += elec

            # 将 area_stats 写回 MySQL 汇总表...
            # (省略原有的 INSERT INTO summary_daily_online_by_area 写入逻辑，与原版一致即可)
            _log.info(f"账户[{account}] {date_str} 聚合完成，共处理 {len(devices)} 台设备")
            
        except Exception as e:
            _log.error(f"聚合失败: {e}")

    def start(self):
        _log.info("服务端启动")
        # 启动多个批量入库线程
        self.workers = []
        for i in range(3):
            t = Thread(target=self._db_inserter_worker, daemon=True)
            t.start()
            self.workers.append(t)

        while not self.shutdown_event.is_set():
            sleep(1)

    def stop(self):
        self.shutdown_event.set()
        self.client.stop()

if __name__ == "__main__":
    server = Server()
    def sig_handler(sig, frame): server.stop(); sys.exit(0)
    signal.signal(signal.SIGINT, sig_handler)
    server.start()