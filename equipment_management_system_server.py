#!/usr/bin/env python3
"""
设备数据接收服务端
纯Python后端服务，无GUI依赖
"""
import os
import sys
import json
import signal
import atexit
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
import redis
from redis import Redis

# ===================== 配置管理 =====================
class Config:
    """配置管理类"""
    # 数据库配置（本地测试环境）
    # DB_HOST = os.getenv('DB_HOST', 'localhost')
    # DB_PORT = int(os.getenv('DB_PORT', '3306'))
    # DB_USER = os.getenv('DB_USER', 'root')
    # DB_PASSWORD = os.getenv('DB_PASSWORD', '123456')
    #数据库配置（生产环境）

    host = 'localhost'
    # host = 'opr.iotdirvers.com'
    DB_HOST = os.getenv('DB_HOST', host)
    DB_PORT = int(os.getenv('DB_PORT', '3311'))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'MST@2026!')

    DB_NAME = os.getenv('DB_NAME', 'MST_SQL')
    DB_CHARSET = 'utf8mb4'
    
    # Unix Socket配置（Windows使用TCP，Linux使用Socket）
    DB_USE_SOCKET = os.getenv('DB_USE_SOCKET', 'False').lower() == 'true'
    DB_SOCKET_PATH = os.getenv('DB_SOCKET_PATH', '/var/run/mysqld/mysqld.sock')
    
    # 连接池配置（优化后）
    DB_MAX_CONNECTIONS = int(os.getenv('DB_MAX_CONNECTIONS', '50'))
    DB_MIN_CACHED = int(os.getenv('DB_MIN_CACHED', '10'))
    DB_MAX_CACHED = int(os.getenv('DB_MAX_CACHED', '20'))
    
    # Redis配置（根据环境自动选择）
    # 检测Redis连接方式优先级：Unix Socket > TCP localhost > TCP remote
    _redis_socket_paths = ['/run/redis.sock', '/var/run/redis/redis-server.sock', '/var/run/redis/redis.sock', '/tmp/redis.sock']
    _redis_socket_exists = any(os.path.exists(p) for p in _redis_socket_paths)
    
    # 默认主机：如果有Socket用localhost（配合Socket），否则优先localhost（小皮面板等本地Redis）
    _default_redis_host = 'localhost' if _redis_socket_exists else 'localhost'
    REDIS_HOST = os.getenv('REDIS_HOST', _default_redis_host)
    REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'MST@2026!')  # 小皮面板默认无密码
    REDIS_DB = int(os.getenv('REDIS_DB', '0'))
    # 默认使用Unix Socket（如果存在），否则使用TCP
    REDIS_USE_SOCKET = os.getenv('REDIS_USE_SOCKET', 'true' if _redis_socket_exists else 'false').lower() == 'true'
    REDIS_SOCKET_PATH = os.getenv('REDIS_SOCKET_PATH', next((p for p in _redis_socket_paths if os.path.exists(p)), '/var/run/redis/redis.sock'))
    
    # MQTT配置
    host = "opr.iotdirvers.com"
    # host = "localhost"
    MQTT_HOST = os.getenv('MQTT_HOST', host)
    MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
    MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', f'MST_IC{random.randint(1000, 9999)}')
    MQTT_QOS = int(os.getenv('MQTT_QOS', '1'))
    
    # 数据目录配置
    DATA_DIR = os.getenv('DATA_DIR', './save')

    # 设备上报间隔配置（基础参数，其他参数基于此计算）
    DEVICE_REPORT_INTERVAL = int(os.getenv('DEVICE_REPORT_INTERVAL', '60'))  # 设备上报间隔(秒)，默认1分钟
    
    # 离线时间 = 3 * 设备上报间隔
    OFFLINE_THRESHOLD = int(os.getenv('OFFLINE_THRESHOLD', str(DEVICE_REPORT_INTERVAL * 3)))  # 默认3倍上报间隔
    
    # 最大回退时间 = 离线时间（与离线时间保持一致）
    FALLBACK_MAX_INTERVAL = int(os.getenv('FALLBACK_MAX_INTERVAL', str(OFFLINE_THRESHOLD)))  # 默认等于离线时间
    
    # 业务配置
    DEVICE_CHECK_INTERVAL = int(os.getenv('DEVICE_CHECK_INTERVAL', '10'))  # 设备检查间隔(秒)
    LOG_ROTATE_INTERVAL = int(os.getenv('LOG_ROTATE_INTERVAL', '5'))  # 日志轮转间隔(秒)
    
    # 预聚合配置
    AGGREGATION_INTERVAL = int(os.getenv('AGGREGATION_INTERVAL', '600'))  # 预聚合间隔(秒)
    AGGREGATION_RETENTION_DAYS = int(os.getenv('AGGREGATION_RETENTION_DAYS', '90'))  # 数据保留天数
    
    # MQTT配置
    MQTT_RECONNECT_INTERVAL = int(os.getenv('MQTT_RECONNECT_INTERVAL', '5'))  # MQTT重连间隔(秒)
    MQTT_STOP_WAIT_TIME = float(os.getenv('MQTT_STOP_WAIT_TIME', '0.5'))  # MQTT停止等待时间(秒)
    MQTT_THREAD_JOIN_TIMEOUT = int(os.getenv('MQTT_THREAD_JOIN_TIMEOUT', '3'))  # MQTT线程等待超时(秒)
    
    # 数据库配置
    DB_CONNECT_TIMEOUT = int(os.getenv('DB_CONNECT_TIMEOUT', '5'))  # 数据库连接超时(秒)
    DB_READ_TIMEOUT = int(os.getenv('DB_READ_TIMEOUT', '30'))  # 数据库读取超时(秒)
    DB_WRITE_TIMEOUT = int(os.getenv('DB_WRITE_TIMEOUT', '30'))  # 数据库写入超时(秒)
    DB_RETRY_DELAY = float(os.getenv('DB_RETRY_DELAY', '0.5'))  # 数据库重试延迟(秒)
    DB_MAX_RETRIES = int(os.getenv('DB_MAX_RETRIES', '3'))  # 数据库最大重试次数
    
    # Redis配置
    REDIS_CONNECT_TIMEOUT = int(os.getenv('REDIS_CONNECT_TIMEOUT', '5'))  # Redis连接超时(秒)
    REDIS_SOCKET_TIMEOUT = int(os.getenv('REDIS_SOCKET_TIMEOUT', '30'))  # Redis套接字超时(秒)
    REDIS_MAX_CONNECTIONS = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))  # Redis最大连接数
    
    # 功率监控配置
    # 功率记录间隔 = 设备上报间隔（与设备上报频率保持一致）
    POWER_RECORD_INTERVAL = int(os.getenv('POWER_RECORD_INTERVAL', str(DEVICE_REPORT_INTERVAL)))
    # 功率聚合延迟 = 功率记录间隔的10%（确保_power表数据已写入）
    POWER_AGGREGATION_DELAY = int(os.getenv('POWER_AGGREGATION_DELAY', str(max(5, POWER_RECORD_INTERVAL // 10))))
    # 功率聚合重试延迟 = 功率记录间隔（与功率记录周期一致）
    POWER_AGGREGATION_RETRY_DELAY = int(os.getenv('POWER_AGGREGATION_RETRY_DELAY', str(POWER_RECORD_INTERVAL)))
    # 功率时间点数量 = 离线时间 / 功率记录间隔（覆盖整个离线周期）
    POWER_TIME_POINTS = int(os.getenv('POWER_TIME_POINTS', str(max(24, OFFLINE_THRESHOLD // POWER_RECORD_INTERVAL))))
    # 注意：功率数据有效时间使用 OFFLINE_THRESHOLD（离线阈值）
    
    # 数据延迟监控配置
    # 数据延迟告警阈值 = 离线时间（超过离线时间才告警）
    DATA_DELAY_THRESHOLD = int(os.getenv('DATA_DELAY_THRESHOLD', str(OFFLINE_THRESHOLD)))
    # 数据延迟检查间隔 = 功率记录间隔（与功率记录周期一致）
    DATA_DELAY_CHECK_INTERVAL = int(os.getenv('DATA_DELAY_CHECK_INTERVAL', str(POWER_RECORD_INTERVAL)))
    
    # 缓存持久化配置
    CACHE_PERSISTENCE_ENABLED = os.getenv('CACHE_PERSISTENCE_ENABLED', 'true').lower() == 'true'  # 是否启用缓存持久化
    CACHE_PERSISTENCE_KEY = os.getenv('CACHE_PERSISTENCE_KEY', 'device_parsed_cache')  # Redis缓存键名
    CACHE_PERSISTENCE_TTL = int(os.getenv('CACHE_PERSISTENCE_TTL', '86400'))  # 缓存持久化TTL(秒)，默认24小时
    
    # 批量查询配置
    BATCH_QUERY_SIZE = int(os.getenv('BATCH_QUERY_SIZE', '100'))  # 批量查询设备数
    BATCH_QUERY_TIMEOUT = int(os.getenv('BATCH_QUERY_TIMEOUT', '30'))  # 批量查询超时(秒)
    
    # 状态感知回退配置
    FALLBACK_STRATEGY = os.getenv('FALLBACK_STRATEGY', 'state_aware')  # 回退策略：none(无回退)/fixed(固定时间)/state_aware(状态感知)
    # 注意：FALLBACK_MAX_INTERVAL 默认等于 OFFLINE_THRESHOLD（离线时间）
    # 固定回退时间(分钟) = 设备上报间隔的1/3（至少1分钟），用于固定时间策略
    FALLBACK_FIXED_MINUTES = int(os.getenv('FALLBACK_FIXED_MINUTES', str(max(1, DEVICE_REPORT_INTERVAL // 60 // 3))))
    
    # 线程配置
    THREAD_SLEEP_INTERVAL = int(os.getenv('THREAD_SLEEP_INTERVAL', '1'))  # 线程睡眠间隔(秒)
    DB_INSERTER_RETRY_DELAY = int(os.getenv('DB_INSERTER_RETRY_DELAY', '2'))  # 数据库插入重试延迟(秒)
    
    # 解析表字段对应键名
    PARSED_KEYS ={"电能": ["DT","EleInfo","tEc",0],"功率": ["DT","EleInfo","p",0]}  # 键名字典
    


# ===================== 简单日志配置（仅用于服务端运行日志）=====================
class SimpleLogger:
    """简单日志记录器 - 控制台只显示INFO及以上级别，DEBUG只写入文件"""
    def __init__(self):
        self.log_file = os.path.join(Config.DATA_DIR, 'server.log')
        os.makedirs(Config.DATA_DIR, exist_ok=True)

    def _write(self, level, msg, console=True):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"{timestamp} - {level} - {msg}"
        # 控制台只输出INFO及以上级别
        if console and level in ('INFO', 'WARNING', 'ERROR'):
            print(line)
        # 所有级别都写入文件
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    def info(self, msg):
        self._write('INFO', msg)

    def debug(self, msg):
        # DEBUG级别只写入文件，不输出到控制台
        self._write('DEBUG', msg, console=False)

    def warning(self, msg):
        self._write('WARNING', msg)

    def error(self, msg):
        self._write('ERROR', msg)


_log = SimpleLogger()


# ===================== MQTT客户端（纯Python，无PyQt依赖）=====================
class MqttClient:
    """纯Python MQTT客户端（替代MqttThread）"""

    def __init__(self, config, message_callback=None):
        """
        :param config: [host, port, client_id, qos]
        :param message_callback: 消息接收回调函数(topic, data)
        """
        self.broker = config[0]
        self.port = config[1]
        self.client_id = config[2]
        self.qos = config[3]
        self.message_callback = message_callback

        self.sub_topic = "MS/#/dev2plt"
        self.devs = []  # 已订阅设备列表

        self._is_running = True
        self._reconnecting = False
        self._reconnect_interval = Config.MQTT_RECONNECT_INTERVAL
        self._mutex = Lock()
        self._first_connect = True

        # 创建MQTT客户端
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id
        )

        # 设置回调
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # 后台线程
        self._thread = None

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """连接成功回调"""
        if rc == 0:
            with self._mutex:
                self._reconnecting = False
            _log.info(f"MQTT连接成功: {self.broker}:{self.port}")
            # 注意：不在此处订阅主题，由上层调用 _update_subscriptions() 进行精确订阅
            # 避免使用通配符#订阅所有主题，只订阅本账户下的设备
            self._first_connect = False
        else:
            _log.error(f"MQTT连接失败，返回码: {rc}")

    def _on_disconnect(self, client, userdata, rc, disconnect_flags, properties=None):
        """断开连接回调"""
        if not self._is_running:
            # 服务正在停止，不进行重连
            return
        if rc != 0:
            _log.warning(f"MQTT异常断开，将在{self._reconnect_interval}秒后重连")
            self._auto_reconnect()

    def _on_message(self, client, userdata, msg):
        """接收消息回调"""
        try:
            data = json.loads(msg.payload)
            if self.message_callback:
                self.message_callback(msg.topic, data)
        except json.JSONDecodeError:
            _log.warning(f"收到非JSON数据: {msg.topic} {msg.payload}")
        except Exception as e:
            _log.error(f"处理消息失败: {e}")

    def _auto_reconnect(self):
        """自动重连"""
        with self._mutex:
            if self._reconnecting or not self._is_running:
                return
            self._reconnecting = True

        retry_count = 0
        while self._is_running:
            try:
                retry_count += 1
                _log.info(f"MQTT第{retry_count}次重连...")
                self.client.reconnect()
                # 重连成功会触发on_connect
                return
            except Exception as e:
                _log.error(f"MQTT重连失败: {e}")
                sleep(self._reconnect_interval)

    def subscribe(self, dev):
        """订阅设备主题，返回是否为新订阅"""
        if dev in self.devs:
            return False  # 已订阅，不是新订阅
        
        topic = self.sub_topic.replace("#", dev)
        result = self.client.subscribe(topic, self.qos)
        if result[0] == 0:
            self.devs.append(dev)
            _log.debug(f"订阅主题: {topic}")
            return True  # 新订阅成功
        else:
            _log.error(f"订阅失败: {topic}")
            return False

    def unsubscribe(self, dev):
        """取消订阅设备主题"""
        if dev in self.devs:
            topic = self.sub_topic.replace("#", dev)
            result = self.client.unsubscribe(topic)
            self.devs.remove(dev)
            return result[0] == 0
        return True

    def publish(self, topic, msg):
        """发布消息"""
        result = self.client.publish(topic, msg, self.qos)
        return result[0] == 0

    def _run(self):
        """后台运行线程"""
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()

            # 保持运行直到停止
            while self._is_running:
                sleep(Config.THREAD_SLEEP_INTERVAL)

        except Exception as e:
            _log.error(f"MQTT运行异常: {e}")
            self._auto_reconnect()

    def start(self):
        """启动MQTT客户端"""
        self._is_running = True
        self._thread = Thread(target=self._run, name="MQTTClient", daemon=True)
        self._thread.start()
        _log.info(f"MQTT客户端启动: {self.client_id}")

    def stop(self):
        """停止MQTT客户端"""
        # 先标记停止状态，防止重连
        self._is_running = False
        self._reconnecting = False

        # 等待重连线程退出
        sleep(Config.MQTT_STOP_WAIT_TIME)

        try:
            # 先断开连接，再停止loop
            self.client.disconnect()
            sleep(Config.MQTT_STOP_WAIT_TIME)
            self.client.loop_stop()
        except Exception as e:
            _log.warning(f"MQTT停止异常: {e}")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=Config.MQTT_THREAD_JOIN_TIMEOUT)

        _log.info("MQTT客户端已停止")


# ===================== 服务端主类 =====================
class Server:
    """设备数据接收服务端"""
    
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.client = None
        self.shutdown_event = Event()
        self.device_count = 0
        self.device_count_lock = Lock()  # 使用线程锁
        self.deivce_parsed_cache = {}
        self.cache_lock = Lock()  # 缓存操作锁
        
        # 数据文件路径（用于缓存待写入数据库的设备数据）
        self.WRITING_LOG = os.path.join(Config.DATA_DIR, "writing.log")
        self.PENDING_PREFIX = "ready_"
        
        # 初始化
        self._init_db_pool()
        self._init_redis()
        self._init_mqtt()
        self._init_tables()
        self._init_aggregation_tables()
        
        # 打印基础参数配置信息
        _log.info("=" * 60)
        _log.info("服务端初始化完成")
        _log.info("基础参数配置:")
        _log.info(f"  设备上报间隔: {Config.DEVICE_REPORT_INTERVAL}秒 ({Config.DEVICE_REPORT_INTERVAL // 60}分钟)")
        _log.info(f"  离线时间阈值: {Config.OFFLINE_THRESHOLD}秒 ({Config.OFFLINE_THRESHOLD // 60}分钟) = 3×上报间隔")
        _log.info(f"  功率记录间隔: {Config.POWER_RECORD_INTERVAL}秒 ({Config.POWER_RECORD_INTERVAL // 60}分钟)")
        _log.info(f"  回退策略: {Config.FALLBACK_STRATEGY}")
        _log.info(f"  最大回退时间: {Config.OFFLINE_THRESHOLD}秒 (等于离线时间)")
        _log.info(f"  数据延迟告警阈值: {Config.DATA_DELAY_THRESHOLD}秒 ({Config.DATA_DELAY_THRESHOLD // 60}分钟)")
        _log.info(f"  功率时间点数量: {Config.POWER_TIME_POINTS}")
        _log.info("=" * 60)
    
    def _init_db_pool(self):
        """初始化数据库连接池（支持Unix Socket优化）"""
        try:
            # 构建连接参数
            pool_kwargs = {
                'creator': pymysql,
                'maxconnections': Config.DB_MAX_CONNECTIONS,
                'mincached': Config.DB_MIN_CACHED,
                'maxcached': Config.DB_MAX_CACHED,
                'blocking': True,
                'maxusage': None,
                'setsession': [],
                'ping': 1,  # 启用ping检查连接有效性
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'database': Config.DB_NAME,
            'charset': Config.DB_CHARSET,
            'cursorclass': DictCursor,
            'connect_timeout': Config.DB_CONNECT_TIMEOUT,
            'read_timeout': Config.DB_READ_TIMEOUT,
            'write_timeout': Config.DB_WRITE_TIMEOUT
            }
            
            # 根据配置选择连接方式
            if Config.DB_USE_SOCKET and os.path.exists(Config.DB_SOCKET_PATH):
                # Linux/Unix使用Unix Socket（性能最优）
                pool_kwargs['unix_socket'] = Config.DB_SOCKET_PATH
                _log.info(f"使用Unix Socket连接MySQL: {Config.DB_SOCKET_PATH}")
            else:
                # Windows或Socket不可用时使用TCP
                pool_kwargs['host'] = Config.DB_HOST
                pool_kwargs['port'] = Config.DB_PORT
                _log.info(f"使用TCP连接MySQL: {Config.DB_HOST}:{Config.DB_PORT}")
            
            self.db_pool = PooledDB(**pool_kwargs)
            _log.info(f"数据库连接池初始化成功 (max={Config.DB_MAX_CONNECTIONS}, min={Config.DB_MIN_CACHED})")
        except Exception as e:
            _log.error(f"数据库连接池初始化失败: {e}")
            traceback.print_exc()
            raise
    
    def _init_redis(self):
        """初始化Redis连接（用于数据缓冲和缓存）"""
        try:
            # 根据配置选择连接方式
            if Config.REDIS_USE_SOCKET and os.path.exists(Config.REDIS_SOCKET_PATH):
                # Linux/Unix使用Unix Socket
                _log.info(f"使用Unix Socket连接Redis: {Config.REDIS_SOCKET_PATH}")
                self.redis_client = Redis(
                    unix_socket_path=Config.REDIS_SOCKET_PATH,
                    password=Config.REDIS_PASSWORD,
                    db=Config.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=Config.REDIS_CONNECT_TIMEOUT,
                    socket_timeout=Config.REDIS_SOCKET_TIMEOUT,
                    max_connections=Config.REDIS_MAX_CONNECTIONS
                )
            else:
                # Windows或Socket不可用时使用TCP
                _log.info(f"使用TCP连接Redis: {Config.REDIS_HOST}:{Config.REDIS_PORT}")
                self.redis_client = Redis(
                    host=Config.REDIS_HOST,
                    port=Config.REDIS_PORT,
                    password=Config.REDIS_PASSWORD,
                    db=Config.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=Config.REDIS_CONNECT_TIMEOUT,
                    socket_timeout=Config.REDIS_SOCKET_TIMEOUT,
                    max_connections=Config.REDIS_MAX_CONNECTIONS
                )
            
            # 测试连接
            self.redis_client.ping()
            _log.info("Redis连接成功")
            
            # 如果启用缓存持久化，从Redis加载缓存
            if Config.CACHE_PERSISTENCE_ENABLED:
                self._load_cache_from_redis()
            
        except Exception as e:
            _log.warning(f"Redis连接失败: {e}，将继续使用文件缓存")
            self.redis_client = None
    
    def _load_cache_from_redis(self):
        """从Redis加载持久化的缓存数据"""
        try:
            if not self.redis_client:
                return
            
            cached_data = self.redis_client.get(Config.CACHE_PERSISTENCE_KEY)
            if cached_data:
                import json
                cache_dict = json.loads(cached_data)
                with self.cache_lock:
                    for dev_id, data in cache_dict.items():
                        # 转换时间字符串为datetime对象
                        if '功率时间' in data and data['功率时间']:
                            data['功率时间'] = datetime.fromisoformat(data['功率时间'])
                        if '电能时间' in data and data['电能时间']:
                            data['电能时间'] = datetime.fromisoformat(data['电能时间'])
                        if '最后数据时间' in data and data['最后数据时间']:
                            data['最后数据时间'] = datetime.fromisoformat(data['最后数据时间'])
                        self.deivce_parsed_cache[dev_id] = data
                _log.info(f"从Redis加载缓存数据: {len(cache_dict)} 个设备")
            else:
                _log.info("Redis中没有持久化的缓存数据")
        except Exception as e:
            _log.warning(f"从Redis加载缓存失败: {e}")
    
    def _save_cache_to_redis(self):
        """保存缓存数据到Redis"""
        try:
            if not self.redis_client or not Config.CACHE_PERSISTENCE_ENABLED:
                return
            
            import json
            with self.cache_lock:
                # 转换datetime对象为ISO格式字符串
                cache_dict = {}
                for dev_id, data in self.deivce_parsed_cache.items():
                    cache_dict[dev_id] = {
                        '最低累计电能': data.get('最低累计电能'),
                        '最高累计电能': data.get('最高累计电能'),
                        '电能': data.get('电能'),
                        '电能时间': data.get('电能时间').isoformat() if data.get('电能时间') else None,
                        '功率': data.get('功率'),
                        '功率时间': data.get('功率时间').isoformat() if data.get('功率时间') else None,
                        '今日用电': data.get('今日用电'),
                        '今日用电时间': data.get('今日用电时间').isoformat() if data.get('今日用电时间') else None,
                        '是否在线': data.get('是否在线'),
                        '在线状态时间': data.get('在线状态时间').isoformat() if data.get('在线状态时间') else None,
                        '最后数据时间': data.get('最后数据时间').isoformat() if data.get('最后数据时间') else None
                    }
                
                self.redis_client.setex(
                    Config.CACHE_PERSISTENCE_KEY,
                    Config.CACHE_PERSISTENCE_TTL,
                    json.dumps(cache_dict)
                )
                _log.debug(f"缓存数据已保存到Redis: {len(cache_dict)} 个设备")
        except Exception as e:
            _log.warning(f"保存缓存到Redis失败: {e}")
    
    def _init_aggregation_tables(self):
        """初始化预聚合表"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. 创建功率汇总表（添加账户字段）
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_power` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `时间点` DATETIME NOT NULL,
                            `设备总数` INT NOT NULL DEFAULT 0,
                            `功率之和` BIGINT NOT NULL DEFAULT 0,
                            `在线设备数` INT NOT NULL DEFAULT 0,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_time` (`账户`, `时间点`) USING BTREE,
                            INDEX `idx_time` (`时间点`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 2. 创建区域功率汇总表（添加账户字段）
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_power_by_area` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `时间点` DATETIME NOT NULL,
                            `区域路径` VARCHAR(255) NOT NULL COMMENT '格式：区域1/区域2/区域3，ALL表示全部',
                            `设备数` INT NOT NULL DEFAULT 0,
                            `功率之和` BIGINT NOT NULL DEFAULT 0,
                            `在线设备数` INT NOT NULL DEFAULT 0,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_area_time` (`账户`, `区域路径`, `时间点`) USING BTREE,
                            INDEX `idx_time` (`时间点`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE,
                            INDEX `idx_area` (`区域路径`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 3. 创建每日在线率汇总表（支持1000-2000台设备场景）
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_daily_online` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `日期` DATE NOT NULL,
                            `设备总数` INT NOT NULL DEFAULT 0,
                            `在线设备数` INT NOT NULL DEFAULT 0,
                            `在线率` DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_date` (`账户`, `日期`) USING BTREE,
                            INDEX `idx_date` (`日期`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 4. 创建区域每日在线率汇总表
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_daily_online_by_area` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `日期` DATE NOT NULL,
                            `区域路径` VARCHAR(255) NOT NULL COMMENT '格式：区域1/区域2/区域3，ALL表示全部',
                            `设备数` INT NOT NULL DEFAULT 0,
                            `在线设备数` INT NOT NULL DEFAULT 0,
                            `在线率` DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_area_date` (`账户`, `区域路径`, `日期`) USING BTREE,
                            INDEX `idx_date` (`日期`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE,
                            INDEX `idx_area` (`区域路径`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 5. 创建每日能耗汇总表
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_daily_electricity` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `日期` DATE NOT NULL,
                            `设备总数` INT NOT NULL DEFAULT 0,
                            `总用电量` BIGINT NOT NULL DEFAULT 0,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_date` (`账户`, `日期`) USING BTREE,
                            INDEX `idx_date` (`日期`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 6. 创建区域每日能耗汇总表
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS `summary_daily_electricity_by_area` (
                            `id` INT AUTO_INCREMENT PRIMARY KEY,
                            `账户` VARCHAR(50) NOT NULL DEFAULT '',
                            `日期` DATE NOT NULL,
                            `区域路径` VARCHAR(255) NOT NULL COMMENT '格式：区域1/区域2/区域3，ALL表示全部',
                            `设备数` INT NOT NULL DEFAULT 0,
                            `总用电量` BIGINT NOT NULL DEFAULT 0,
                            `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE INDEX `idx_account_area_date` (`账户`, `区域路径`, `日期`) USING BTREE,
                            INDEX `idx_date` (`日期`) USING BTREE,
                            INDEX `idx_account` (`账户`) USING BTREE,
                            INDEX `idx_area` (`区域路径`) USING BTREE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """)
                    
                    # 3. 删除旧的device_area_mapping实体表（如果存在）
                    cursor.execute("DROP TABLE IF EXISTS `device_area_mapping`")
                    
                    # 4. 创建设备区域映射视图（替代实体表，自动同步，无需维护）
                    cursor.execute("""
                        CREATE OR REPLACE VIEW `device_area_mapping` AS
                        SELECT 
                            `设备号`,
                            `区域1`,
                            `区域2`,
                            `区域3`,
                            CONCAT_WS('/', 
                                NULLIF(`区域1`, ''), 
                                NULLIF(`区域2`, ''), 
                                NULLIF(`区域3`, '')
                            ) as `区域路径`,
                            `日期` as `更新时间`
                        FROM `device_info`
                        WHERE `账户` != '' AND `账户` IS NOT NULL
                    """)
                    
                    conn.commit()
                    _log.info("预聚合表和视图初始化完成（device_area_mapping已改为视图）")
                    
        except Exception as e:
            _log.error(f"预聚合表初始化失败: {e}")
            traceback.print_exc()
    
    def _sync_device_area_mapping(self):
        """设备区域映射视图无需同步，此方法保留用于兼容"""
        _log.debug("设备区域映射为视图，无需同步")
    
    def _init_mqtt(self):
        """初始化MQTT客户端"""
        try:
            mqtt_config = [
                Config.MQTT_HOST,
                Config.MQTT_PORT,
                Config.MQTT_CLIENT_ID,
                Config.MQTT_QOS
            ]
            # 使用纯Python的MqttClient替代PyQt的MqttThread
            self.client = MqttClient(mqtt_config, message_callback=self._handle_message)
            self.client.start()
            _log.info(f"MQTT客户端启动成功: {Config.MQTT_CLIENT_ID}")
        except Exception as e:
            _log.error(f"MQTT客户端启动失败: {e}")
            traceback.print_exc()
            raise
    
    def _init_tables(self):
        """初始化设备表"""
        try:
            self._sync_device_tables()
        except Exception as e:
            _log.error(f"设备表初始化失败: {e}")
            traceback.print_exc()
    
    def get_db_connection(self, max_retries=3):
        """获取数据库连接"""
        retries = 0
        while retries < max_retries:
            try:
                conn = self.db_pool.connection()
                # 验证连接
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return conn
            except Exception as e:
                retries += 1
                _log.warning(f"数据库连接失败，重试 {retries}/{max_retries}: {e}")
                sleep(Config.DB_RETRY_DELAY)
        
        _log.error("数据库连接池已耗尽")
        raise Exception("数据库连接池已耗尽")
    
    def _sync_device_tables(self):
        """同步设备表结构"""
        # 获取所有设备号
        with self.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 设备号 FROM device_info")
                devices = {row["设备号"] for row in cursor.fetchall()}
        self.device_count = len(devices)
        # 获取所有表名
        with self.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema = %s",
                    (Config.DB_NAME,)
                )
                tables = {row["TABLE_NAME"] for row in cursor.fetchall()}

        # 创建缺失的表
        missing_tables = devices - tables
        _log.info(f"开始创建设备原始数据表，并同步创建设备数据解析表，共 {len(missing_tables)} 个")

        if missing_tables:
            self._batch_create_device_tables(missing_tables)

        _log.info("创建完成")

        # 缓存所有设备最新的解析数据
        self._cache_latest_parsed_data(devices)

    def _batch_create_device_tables(self, missing_tables):
        """批量创建设备表，使用多线程并行处理"""
        from concurrent.futures import ThreadPoolExecutor
        import os

        max_workers = min(32, os.cpu_count() * 4)
        _log.info(f"使用 {max_workers} 个线程批量创建设备表")

        # 分批处理，每批100个设备
        batch_size = 100
        table_list = list(missing_tables)
        total = len(table_list)

        for i in range(0, total, batch_size):
            batch = table_list[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._create_device_table_fast, dev_id) for dev_id in batch]
                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        _log.error(f"创建设备表失败: {e}")
            _log.info(f"已创建 {min(i + batch_size, total)}/{total} 个设备表")
    
    def _create_device_table_fast(self, dev_id):
        """快速创建设备表（仅创建表结构，不查询历史数据）"""
        with self.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. 创建原始数据表
                sql_raw = f"""
                    CREATE TABLE IF NOT EXISTS `{dev_id}` (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        SV VARCHAR(25),
                        CT VARCHAR(25),
                        datetime DATETIME,
                        data JSON,
                        INDEX idx_datetime (datetime),
                        INDEX idx_sv_ct (SV, CT)
                    )
                """
                cursor.execute(sql_raw)

                # 2. 同步创建设备数据解析表
                sql_parsed = f"""
                    CREATE TABLE IF NOT EXISTS `{dev_id}_parsed` (
                        `序号` INT NOT NULL AUTO_INCREMENT,
                        `日期` DATE NOT NULL,
                        `最新时间` DATETIME NOT NULL,
                        `最低累计电能` INT NOT NULL DEFAULT '0',
                        `最高累计电能` INT NOT NULL DEFAULT '0',
                        `当天累计电能` INT NOT NULL DEFAULT '0',
                        `在线情况` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1：在线；0：离线',
                        `告警条数` INT NOT NULL DEFAULT '0',
                        `告警内容` TEXT NOT NULL,
                        `功率` INT NOT NULL DEFAULT '0',
                        `功率时间` DATETIME NULL,
                        PRIMARY KEY (`序号`) USING BTREE,
                        UNIQUE INDEX `日期` (`日期`) USING BTREE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                """
                cursor.execute(sql_parsed)

                # 创建设备功率记录表
                sql_power = f"""
                    CREATE TABLE IF NOT EXISTS `{dev_id}_power` (
                        `序号` INT NOT NULL AUTO_INCREMENT,
                        `时间点` DATETIME NOT NULL,
                        `功率` INT NULL DEFAULT NULL COMMENT 'NULL表示无数据，0表示功率为0',
                        PRIMARY KEY (`序号`) USING BTREE,
                        UNIQUE INDEX `时间点` (`时间点`) USING BTREE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                """
                cursor.execute(sql_power)
                conn.commit()

        # 初始化缓存
        today_date = date.today()
        deivce_parsed_cache = {"日期": today_date, "最低累计电能": 0, "最高累计电能": 0, "当天累计电能": 0,
                               "在线情况": 0, "告警条数": 0, "告警内容": "", "功率": 0, "功率时间": None}

        with self.cache_lock:
            self.deivce_parsed_cache[dev_id] = deivce_parsed_cache

    def _create_device_table(self, dev_id):
        """创建设备原始数据表，并同步创建设备数据解析表（包含历史数据恢复）"""
        # 先快速创建表结构
        self._create_device_table_fast(dev_id)

        # 然后恢复当天历史数据到缓存
        today_date = date.today()
        deivce_parsed_cache = {"日期": today_date, "最低累计电能": 0, "最高累计电能": 0, "当天累计电能": 0,
                               "在线情况": 0, "告警条数": 0, "告警内容": "", "功率": 0, "功率时间": None}

        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 查询当天数据
                    sql = f"""
                        SELECT * 
                        FROM `{dev_id}` 
                        WHERE DATE(`datetime`) = %s
                    """
                    cursor.execute(sql, (today_date,))
                    rows = cursor.fetchall()

            # 处理当天历史数据
            if rows:
                deivce_parsed_cache["在线情况"] = 1
                for row in rows:
                    try:
                        json_date = json.loads(row["data"])
                    except json.JSONDecodeError:
                        _log.error("JSON失败")
                        continue
                    else:
                        if json_date.get("CT") != "A" and json_date.get("CT") != "W":  # 非告警非写返回
                            parsed_data = self._get_parsed_data(json_date)
                            ec = parsed_data.get("电能")
                            if ec is not None:
                                if deivce_parsed_cache["最低累计电能"] == 0 and deivce_parsed_cache["最高累计电能"] == 0:
                                    deivce_parsed_cache["最低累计电能"] = ec
                                    deivce_parsed_cache["最高累计电能"] = ec
                                elif ec < deivce_parsed_cache["最低累计电能"]:
                                    deivce_parsed_cache["最低累计电能"] = ec
                                elif ec > deivce_parsed_cache["最高累计电能"]:
                                    deivce_parsed_cache["最高累计电能"] = ec
                                deivce_parsed_cache["当天累计电能"] = deivce_parsed_cache["最高累计电能"] - \
                                                                        deivce_parsed_cache["最低累计电能"]
                        elif json_date.get("CT") == "A":  # 告警返回
                            deivce_parsed_cache["告警条数"] += 1
                            deivce_parsed_cache["告警内容"] += row["data"] + "\n"

            # 更新缓存
            with self.cache_lock:
                self.deivce_parsed_cache[dev_id] = deivce_parsed_cache

            _log.debug(f"创建设备表并恢复数据: {dev_id}")
        except Exception as e:
            _log.error(f"创建设备表 {dev_id} 失败: {e}")



    def _cache_latest_parsed_data(self, devices):
        """缓存所有设备最新的解析数据"""
        today_date = date.today()  # 当天日期

        # 批量查询，减少数据库连接
        with self.get_db_connection() as conn:
            for dev in devices:
                # 从解析表获取数据，避免解析原始数据
                deivce_parsed_cache = {"日期": today_date, "最低累计电能": 0, "最高累计电能": 0, "当天累计电能": 0,
                                       "在线情况": 0, "告警条数": 0, "告警内容": "", "功率": 0, "功率时间": None}

                try:
                    with conn.cursor() as cursor:
                        # 优先从解析表获取
                        parsed_table = f"{dev}_parsed"
                        sql = f"""
                        SELECT *
                        FROM `{parsed_table}`
                        WHERE `日期` = %s
                        """
                        cursor.execute(sql, (today_date,))
                        row = cursor.fetchone()

                        if row:
                            # 从解析表直接获取数据
                            deivce_parsed_cache = {
                                "日期": row["日期"],
                                "最低累计电能": row["最低累计电能"],
                                "最高累计电能": row["最高累计电能"],
                                "当天累计电能": row["当天累计电能"],
                                "在线情况": row["在线情况"],
                                "告警条数": row["告警条数"],
                                "告警内容": row["告警内容"],
                                "功率": row.get("功率", 0),
                                "功率时间": row.get("功率时间")
                            }
                        else:
                            # 解析表没有数据，从原始表获取
                            sql = f"""
                            SELECT *
                            FROM `{dev}`
                            WHERE DATE(`datetime`) = %s
                            ORDER BY `datetime` ASC
                            """
                            cursor.execute(sql, (today_date,))
                            rows = cursor.fetchall()

                            if rows:
                                deivce_parsed_cache["在线情况"] = 1
                                for row in rows:
                                    try:
                                        json_date = json.loads(row["data"])
                                    except json.JSONDecodeError:
                                        _log.error("JSON失败")
                                        continue
                                    else:
                                        if json_date.get("CT") != "A" and json_date.get("CT") != "W": #非告警非写返回
                                            parsed_data = self._get_parsed_data(json_date)
                                            ec = parsed_data.get("电能")
                                            p = parsed_data.get("功率")
                                            if ec:
                                                if deivce_parsed_cache["最低累计电能"] == 0 and deivce_parsed_cache["最高累计电能"] == 0:
                                                    deivce_parsed_cache["最低累计电能"] = ec
                                                    deivce_parsed_cache["最高累计电能"] = ec

                                                if ec < deivce_parsed_cache["最低累计电能"]:
                                                    deivce_parsed_cache["最低累计电能"] = ec
                                                else:
                                                    deivce_parsed_cache["最高累计电能"] = ec
                                                deivce_parsed_cache["当天累计电能"] = deivce_parsed_cache["最高累计电能"] - deivce_parsed_cache["最低累计电能"]
                                            # 提取功率和功率时间
                                            if p is not None:
                                                deivce_parsed_cache["功率"] = p
                                                deivce_parsed_cache["功率时间"] = row["datetime"]
                                        elif json_date.get("CT") == "A": #告警返回
                                            deivce_parsed_cache["告警条数"] += 1
                                            deivce_parsed_cache["告警内容"] += row["data"]+"\n"
                except Exception as e:
                    _log.error(f"缓存设备 {dev} 数据失败: {e}")

                self.deivce_parsed_cache[dev] = deivce_parsed_cache
                if len(devices) <= 100:  # 只在设备数量少时打印
                    _log.info(f"缓存设备 {dev} 解析数据")






    def _handle_message(self, topic, data):
        """处理接收到的消息"""
        _log.debug(f"接收消息：{topic}")
        # 获取设备号、服务器时间、数据类型
        dev = data["SN"]  # 设备号
        sv = data["SV"]  # 数据类型
        ct = data["CT"]  # 数据类型
        now_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 服务器时间

        line = dev + "," + sv + "," + ct + "," + now_date + "," + str(data).replace("'", "\"")
        # 数据写入
        try:
            # 按分钟分桶写入，避免单个文件过大
            bucket = datetime.now().strftime("%Y%m%d_%H%M")
            bucket_file = os.path.join(Config.DATA_DIR, f"writing_{bucket}.log")
            # 只追加，不读、不删、不移动
            with open(bucket_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            _log.error(f"写入日志失败: {e}")
            traceback.print_exc()
    

    
    def _log_rotator(self):
        """日志滚动线程 每隔 5 秒把 save/writing_*.log 重命名为 ./save/ready_时间戳.log"""
        while not self.shutdown_event.is_set():
            try:
                # 使用可中断的睡眠
                for _ in range(Config.LOG_ROTATE_INTERVAL):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)

                # 查找所有 writing_*.log 文件
                writing_files = [
                    f for f in os.listdir(Config.DATA_DIR)
                    if f.startswith("writing_") and f.endswith(".log")
                ]

                for writing_file in writing_files:
                    writing_path = os.path.join(Config.DATA_DIR, writing_file)
                    if os.path.getsize(writing_path) > 0:
                        # 原子重命名，操作系统保证不损坏、不冲突
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        ready_log = os.path.join(Config.DATA_DIR, f"{self.PENDING_PREFIX}{timestamp}.log")

                        try:
                            os.rename(writing_path, ready_log)
                            _log.info(f"日志滚动成功：{writing_file} -> {ready_log}")
                        except Exception as e:
                            _log.warning(f"日志滚动失败: {e}")

            except Exception as e:
                if not self.shutdown_event.is_set():
                    _log.error(f"日志滚动线程异常: {e}")

    def _process_file(self, file):
        """处理单个文件"""
        try:
            filepath = os.path.join(Config.DATA_DIR, file)

            # 读取全部内容
            with open(filepath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]

            if not lines:
                os.remove(filepath)
                return

            _log.info(f"处理文件：{file} ({len(lines)} 条数据)")

            # 数据分组和聚合
            table_data = {}  # 原始数据: {dev: [(sv, ct, now_date, data_str), ...]}
            parsed_agg = {}  # 解析数据聚合: {(dev, date): agg_data}
            
            for line in lines:
                parts = line.split(",")
                if len(parts) < 5:
                    continue
                
                dev = parts[0]
                sv = parts[1]
                ct = parts[2]
                now_date = parts[3]
                data_str = ",".join(parts[4:])
                
                # 收集原始数据
                table_data.setdefault(dev, [])
                table_data[dev].append((sv, ct, now_date, data_str))
                
                # 解析数据
                try:
                    json_data = json.loads(data_str)
                    dt = datetime.strptime(now_date, "%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    _log.error(f"解析数据失败：{data_str}, 错误：{e}")
                    continue
                
                # 初始化设备缓存（如果不存在）- 使用锁保护
                with self.cache_lock:
                    if dev not in self.deivce_parsed_cache:
                        self.deivce_parsed_cache[dev] = {
                            "日期": date.today(),
                            "最低累计电能": 0,
                            "最高累计电能": 0,
                            "当天累计电能": 0,
                            "在线情况": 1,
                            "告警条数": 0,
                            "告警内容": "",
                            "功率": 0,
                            "功率时间": None
                        }

                cache = self.deivce_parsed_cache[dev]
                data_date = dt.date()

                # 检测跨天：当前日期大于缓存日期，重置缓存 - 使用锁保护
                with self.cache_lock:
                    today = date.today()
                    if today > cache["日期"]:
                        cache["日期"] = today
                        cache["最低累计电能"] = 0
                        cache["最高累计电能"] = 0
                        cache["当天累计电能"] = 0
                        cache["在线情况"] = 1
                        cache["告警条数"] = 0
                        cache["告警内容"] = ""
                        cache["功率"] = 0
                        cache["功率时间"] = None

                    # 检测数据日期变化（跨天重启场景）
                    if data_date > cache["日期"]:
                        # 新日期：重置缓存
                        cache["日期"] = data_date
                        cache["最低累计电能"] = 0
                        cache["最高累计电能"] = 0
                        cache["当天累计电能"] = 0
                        cache["在线情况"] = 1
                        cache["告警条数"] = 0
                        cache["告警内容"] = ""
                        cache["功率"] = 0
                        cache["功率时间"] = None
                
                # 聚合键：(设备, 日期)
                agg_key = (dev, data_date)
                if agg_key not in parsed_agg:
                    parsed_agg[agg_key] = {
                        'min_ec': float('inf'),
                        'max_ec': 0,
                        'alarm_count': 0,
                        'alarm_content': [],
                        'latest_time': dt,
                        'online': 1,
                        'power': 0,
                        'power_time': None
                    }

                agg = parsed_agg[agg_key]

                # 更新聚合数据
                if json_data.get("CT") != "A" and json_data.get("CT") != "W":
                    # 非告警非写返回：累计电能和功率
                    parsed = self._get_parsed_data(json_data)
                    ec = parsed.get("电能")
                    p = parsed.get("功率")
                    if ec is not None:
                        agg['min_ec'] = min(agg['min_ec'], ec)
                        agg['max_ec'] = max(agg['max_ec'], ec)
                        # 同步更新缓存（用于实时查询）- 使用锁保护
                        with self.cache_lock:
                            if data_date == cache["日期"]:
                                if cache["最低累计电能"] == 0:
                                    cache["最低累计电能"] = ec
                                    cache["最高累计电能"] = ec
                                else:
                                    if ec < cache["最低累计电能"]:
                                        cache["最低累计电能"] = ec
                                    if ec > cache["最高累计电能"]:
                                        cache["最高累计电能"] = ec
                                cache["当天累计电能"] = cache["最高累计电能"] - cache["最低累计电能"]
                    # 提取功率和功率时间（取最新的）
                    if p is not None:
                        agg['power'] = p
                        agg['power_time'] = dt
                        # 同步更新缓存
                        with self.cache_lock:
                            if data_date == cache["日期"]:
                                cache["功率"] = p
                                cache["功率时间"] = dt

                elif json_data.get("CT") == "A":
                    # 告警
                    agg['alarm_count'] += 1
                    # 限制告警内容长度，避免无限增长
                    if len(agg['alarm_content']) < 100:  # 最多保留100条告警
                        agg['alarm_content'].append(data_str)
                    # 同步更新缓存（用于实时查询）- 使用锁保护
                    with self.cache_lock:
                        if data_date == cache["日期"]:
                            cache["告警条数"] += 1
                            # 限制缓存中的告警内容长度
                            if len(cache["告警内容"]) < 10000:  # 最多10000字符
                                cache["告警内容"] += data_str + "\n"

                # 更新最新时间
                agg['latest_time'] = max(agg['latest_time'], dt)
                # 同步更新缓存（用于实时查询）- 使用锁保护
                with self.cache_lock:
                    if data_date == cache["日期"]:
                        cache["在线情况"] = 1

            # 单连接批量写入数据库
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 批量插入原始数据
                for dev, rows in table_data.items():
                    sql = f"INSERT INTO `{dev}` (SV, CT, datetime, data) VALUES (%s, %s, %s, %s)"
                    cursor.executemany(sql, rows)
                
                # 批量UPSERT解析数据
                for (dev, data_date), agg in parsed_agg.items():
                    # 处理无电能数据的情况
                    min_ec = agg['min_ec'] if agg['min_ec'] != float('inf') else 0
                    max_ec = agg['max_ec']
                    daily_ec = max_ec - min_ec if max_ec > min_ec else 0
                    alarm_content = "\n".join(agg['alarm_content'])
                    power = agg.get('power', 0)
                    power_time = agg.get('power_time')

                    table_name = f"{dev}_parsed"
                    # 使用 REPLACE 避免告警内容重复累加
                    # 先查询现有告警内容，避免重复
                    cursor.execute(f"SELECT `告警内容`, `功率时间` FROM `{table_name}` WHERE `日期` = %s", (data_date,))
                    existing_row = cursor.fetchone()

                    if existing_row:
                        # 已存在，检查是否已有相同告警
                        existing_alarms = existing_row['告警内容'] or ""
                        # 只添加新的告警内容
                        new_alarms = []
                        for alarm in agg['alarm_content']:
                            if alarm not in existing_alarms:
                                new_alarms.append(alarm)
                        if new_alarms:
                            alarm_content = existing_alarms + "\n" + "\n".join(new_alarms) if existing_alarms else "\n".join(new_alarms)
                        else:
                            alarm_content = existing_alarms
                        # 保留较新的功率时间
                        existing_power_time = existing_row.get('功率时间')
                        if existing_power_time and power_time:
                            if existing_power_time > power_time:
                                power_time = existing_power_time

                    sql = f"""
                        INSERT INTO `{table_name}` (
                            `日期`,
                            `最新时间`,
                            `最低累计电能`,
                            `最高累计电能`,
                            `当天累计电能`,
                            `在线情况`,
                            `告警条数`,
                            `告警内容`,
                            `功率`,
                            `功率时间`
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            `最低累计电能` = LEAST(`最低累计电能`, VALUES(`最低累计电能`)),
                            `最高累计电能` = GREATEST(`最高累计电能`, VALUES(`最高累计电能`)),
                            `当天累计电能` = `最高累计电能` - `最低累计电能`,
                            `在线情况` = VALUES(`在线情况`),
                            `告警条数` = `告警条数` + VALUES(`告警条数`),
                            `告警内容` = VALUES(`告警内容`),
                            `最新时间` = GREATEST(`最新时间`, VALUES(`最新时间`)),
                            `功率` = VALUES(`功率`),
                            `功率时间` = VALUES(`功率时间`)
                    """
                    cursor.execute(sql, (
                        data_date,
                        agg['latest_time'],
                        min_ec,
                        max_ec,
                        daily_ec,
                        agg['online'],
                        agg['alarm_count'],
                        alarm_content,
                        power,
                        power_time
                    ))
                
                conn.commit()

            # 删除已处理文件
            try:
                os.remove(filepath)
                _log.info(f"成功入库 {len(lines)} 条 → {file} 已删除")
            except Exception as e:
                _log.warning(f"删除文件 {file} 失败: {e}")
            
            # 保存缓存到Redis（如果启用缓存持久化）
            if Config.CACHE_PERSISTENCE_ENABLED:
                self._save_cache_to_redis()
                
        except Exception as e:
            if not self.shutdown_event.is_set():
                _log.error(f"处理文件 {file} 异常: {e}")
                traceback.print_exc()
                # 异常时重命名文件，避免重复处理
                try:
                    error_file = filepath + ".error"
                    os.rename(filepath, error_file)
                    _log.warning(f"文件已重命名为 {error_file}，避免重复处理")
                except:
                    pass
    
    def _db_inserter(self):
        """数据库插入线程 - 将缓存的数据文件写入数据库（优化版）
        
        优化点：
        1. 多线程池：并行处理多个文件
        2. 文件级单连接：整个文件处理使用单一数据库连接
        3. 解析数据聚合：按(设备,日期)聚合，批量UPSERT替代逐条更新
        4. 跨天处理：自动检测日期变化，重置缓存并刷盘
        """
        import os
        # 创建线程池，最大线程数为CPU核心数
        max_workers = min(8, os.cpu_count() * 2)
        _log.info(f"初始化数据库插入线程池，最大线程数: {max_workers}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while not self.shutdown_event.is_set():
                try:
                    # 1. 找到所有待消费文件
                    files = [
                        f for f in os.listdir(Config.DATA_DIR)
                        if f.startswith(self.PENDING_PREFIX)
                    ]

                    if not files:
                        for _ in range(Config.THREAD_SLEEP_INTERVAL):
                            if self.shutdown_event.is_set():
                                return
                            sleep(Config.THREAD_SLEEP_INTERVAL)
                        continue

                    # 2. 按时间排序，优先处理旧文件
                    files = sorted(files)[:max_workers]  # 每次最多处理max_workers个文件

                    # 3. 提交到线程池处理
                    futures = []
                    for file in files:
                        future = executor.submit(self._process_file, file)
                        futures.append((file, future))

                    # 4. 等待完成
                    for file, future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            _log.error(f"文件 {file} 处理失败: {e}")

                except Exception as e:
                    if not self.shutdown_event.is_set():
                        _log.error(f"数据库插入线程异常: {e}")
                        traceback.print_exc()
                        sleep(Config.DB_INSERTER_RETRY_DELAY)

    def _get_parsed_data(self, data):
        """获取指定数据的解析数据"""
        paresd = {}
        for name,keys in Config.PARSED_KEYS.items():
            try:
                json_date = data.copy()
                for key in keys:
                    json_date = json_date[key]
                paresd[name] = json_date
            except:
                paresd[name] = None
        return paresd
        

                
    
    def _device_monitor(self):
        """设备数量监控线程"""
        while not self.shutdown_event.is_set():
            try:
                # 使用可中断的睡眠
                for _ in range(Config.DEVICE_CHECK_INTERVAL):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)

                with self.get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) as count FROM device_info")
                        current_count = cursor.fetchone()["count"]

                # 使用锁保护设备数量更新
                with self.device_count_lock:
                    if current_count != self.device_count:
                        _log.info(f"设备数量变化: {self.device_count} -> {current_count}")
                        self.device_count = current_count
                        self._update_subscriptions()

            except Exception as e:
                if not self.shutdown_event.is_set():
                    _log.error(f"设备监控线程异常: {e}")

    def _power_monitor(self):
        """功率记录监控线程 - 每分钟记录一次功率数据到_power表（验证模式）"""
        last_recorded_minute = -1  # 记录上次写入的分钟数，避免重复写入

        while not self.shutdown_event.is_set():
            try:
                # 每秒检查一次
                for _ in range(Config.POWER_RECORD_INTERVAL):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)

                now = datetime.now()
                current_minute = now.minute

                # 验证模式：每分钟记录一次
                if current_minute != last_recorded_minute:
                    # 获取当前时间点（整分钟）
                    time_point = now.replace(second=0, microsecond=0)
                    self._record_power_data(time_point)
                    last_recorded_minute = current_minute

            except Exception as e:
                if not self.shutdown_event.is_set():
                    _log.error(f"功率监控线程异常: {e}")
                    traceback.print_exc()

    def _record_power_data(self, time_point):
        """记录功率数据到各设备的_power表"""
        try:
            devices = []
            with self.cache_lock:
                devices = list(self.deivce_parsed_cache.keys())

            if not devices:
                return

            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    for dev_id in devices:
                        try:
                            # 优先从内存缓存获取功率（更实时）
                            power = None  # 默认为NULL，表示无数据
                            power_time = None
                            
                            with self.cache_lock:
                                cache = self.deivce_parsed_cache.get(dev_id, {})
                                cached_power = cache.get("功率")
                                cached_power_time = cache.get("功率时间")
                                
                                # 使用OFFLINE_THRESHOLD判断数据是否有效（转换为分钟）
                                if cached_power_time:
                                    time_diff = abs((time_point - cached_power_time).total_seconds() / 60)
                                    if time_diff < (Config.OFFLINE_THRESHOLD // 60):  # 使用离线阈值
                                        power = cached_power
                                        power_time = cached_power_time
                            
                            # 如果缓存中没有有效功率，尝试从_parsed表获取
                            if power is None:
                                parsed_table = f"{dev_id}_parsed"
                                today = date.today()

                                cursor.execute(
                                    f"SELECT `功率`, `功率时间` FROM `{parsed_table}` WHERE `日期` = %s",
                                    (today,)
                                )
                                row = cursor.fetchone()

                                if row:
                                    parsed_power = row.get("功率")
                                    parsed_power_time = row.get("功率时间")

                                    # 使用OFFLINE_THRESHOLD判断数据是否有效
                                    if parsed_power_time:
                                        time_diff = abs((time_point - parsed_power_time).total_seconds() / 60)
                                        if time_diff < (Config.OFFLINE_THRESHOLD // 60):  # 使用离线阈值
                                            power = parsed_power
                            
                            # 如果_parsed表也没有，尝试从原始数据表查询（处理数据延迟入库的情况）
                            if power is None:
                                try:
                                    raw_table = f"{dev_id}"
                                    # 使用OFFLINE_THRESHOLD作为时间范围（转换为分钟）
                                    fallback_minutes = Config.OFFLINE_THRESHOLD // 60
                                    # 查询该时间点前后OFFLINE_THRESHOLD时间范围内的最新数据
                                    cursor.execute(
                                        f"SELECT `data`, `datetime` FROM `{raw_table}` WHERE `datetime` >= %s AND `datetime` <= %s ORDER BY `datetime` DESC LIMIT 1",
                                        (time_point - timedelta(minutes=fallback_minutes), 
                                         time_point + timedelta(minutes=fallback_minutes))
                                    )
                                    raw_row = cursor.fetchone()
                                    
                                    if raw_row:
                                        try:
                                            json_data = json.loads(raw_row["data"])
                                            # 只处理非告警非写返回的数据
                                            if json_data.get("CT") != "A" and json_data.get("CT") != "W":
                                                parsed = self._get_parsed_data(json_data)
                                                raw_power = parsed.get("功率")
                                                raw_time = raw_row["datetime"]
                                                
                                                if raw_power is not None:
                                                    # 检查时间差是否在有效范围内
                                                    time_diff = abs((time_point - raw_time).total_seconds() / 60)
                                                    if time_diff < (Config.OFFLINE_THRESHOLD // 60):
                                                        power = raw_power
                                                        _log.debug(f"设备 {dev_id} 从原始数据表获取功率: {power}W [数据时间:{raw_time}, 时间差:{time_diff:.0f}分钟, 离线阈值:{Config.OFFLINE_THRESHOLD // 60}分钟]")
                                        except json.JSONDecodeError:
                                            pass
                                except Exception as e:
                                    # 表不存在或其他错误，忽略
                                    pass

                            # 写入_power表
                            power_table = f"{dev_id}_power"
                            cursor.execute(
                                f"""
                                INSERT INTO `{power_table}` (`时间点`, `功率`)
                                VALUES (%s, %s)
                                ON DUPLICATE KEY UPDATE `功率` = VALUES(`功率`)
                                """,
                                (time_point, power)
                            )
                            
                            # 更新设备最后数据时间（用于状态感知回退）
                            if power is not None:
                                with self.cache_lock:
                                    cache = self.deivce_parsed_cache.get(dev_id, {})
                                    cache['最后数据时间'] = time_point
                                    self.deivce_parsed_cache[dev_id] = cache
                            
                            if power is not None and power > 0:
                                _log.debug(f"记录功率数据: {dev_id} @ {time_point} = {power}W")
                            elif power is None:
                                _log.debug(f"记录功率数据: {dev_id} @ {time_point} = NULL (无数据)")

                        except Exception as e:
                            _log.error(f"记录设备 {dev_id} 功率数据失败: {e}")

                    conn.commit()
                    _log.info(f"完成功率数据记录，时间点: {time_point}，设备数: {len(devices)}")

        except Exception as e:
            _log.error(f"记录功率数据异常: {e}")
            traceback.print_exc()

    def _power_aggregator(self):
        """功率预聚合线程 - 每分钟执行一次预聚合（验证模式）"""
        _log.info("功率预聚合线程启动")
        _log.info(f"  执行间隔: {Config.POWER_RECORD_INTERVAL}秒")
        _log.info(f"  聚合逻辑: 不使用回退，只统计实际有数据的功率")
        _log.info(f"  说明: 聚合时只使用_power表中实际存在的功率数据，不回退查询")
        _log.info(f"  离线阈值: {Config.OFFLINE_THRESHOLD}秒 ({Config.OFFLINE_THRESHOLD // 60}分钟)")
        _log.info(f"  注意: 回退策略({Config.FALLBACK_STRATEGY})仅用于功率记录，不用于聚合")
        last_aggregation_time = None

        while not self.shutdown_event.is_set():
            try:
                # 验证模式：每分钟执行一次
                now = datetime.now()
                next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=Config.POWER_RECORD_INTERVAL // 60)

                wait_seconds = (next_run - now).total_seconds()
                _log.debug(f"预聚合线程等待 {wait_seconds:.0f} 秒后执行")

                # 等待，但可被中断
                for _ in range(int(wait_seconds)):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)

                # 验证模式：每分钟执行预聚合
                now = datetime.now()
                # 延迟执行，确保_power表数据已写入
                sleep(Config.POWER_AGGREGATION_DELAY)
                
                if last_aggregation_time is None or (now - last_aggregation_time).total_seconds() >= 30:
                    self._aggregate_power_data()
                    last_aggregation_time = datetime.now()

            except Exception as e:
                _log.error(f"功率预聚合线程异常: {e}")
                traceback.print_exc()
                sleep(Config.POWER_AGGREGATION_RETRY_DELAY)  # 异常后重试

    def _daily_stats_aggregator(self):
        """每日在线率和能耗聚合线程 - 每小时执行一次（支持1000-2000台设备）"""
        _log.info("每日统计聚合线程启动")
        _log.info("  执行间隔: 每小时执行一次")
        _log.info("  聚合内容: 每日在线率、每日能耗")
        _log.info("  支持规模: 1000-2000台设备")

        while not self.shutdown_event.is_set():
            try:
                now = datetime.now()
                # 计算下一个整点执行时间
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait_seconds = (next_hour - now).total_seconds()

                _log.debug(f"每日统计聚合线程等待 {wait_seconds:.0f} 秒后执行")

                # 等待，但可被中断
                for _ in range(int(wait_seconds)):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)

                # 执行每日统计聚合
                self._aggregate_daily_stats()

            except Exception as e:
                _log.error(f"每日统计聚合线程异常: {e}")
                traceback.print_exc()
                sleep(60)  # 异常后1分钟重试

    def _aggregate_daily_stats(self):
        """执行每日在线率和能耗聚合（支持1000-2000台设备场景）"""
        try:
            _log.info("开始执行每日统计聚合")

            # 获取昨天和今天的日期
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)

            # 获取所有账户
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT DISTINCT `账户` FROM `device_info` WHERE `账户` != ''")
                    accounts = [row['账户'] for row in cursor.fetchall()]

            if not accounts:
                _log.warning("没有账户数据，跳过每日统计聚合")
                return

            # 为每个账户聚合数据
            for account in accounts:
                self._aggregate_account_daily_stats(account, yesterday)
                self._aggregate_account_daily_stats(account, today)

            _log.info(f"每日统计聚合完成，共处理 {len(accounts)} 个账户")

        except Exception as e:
            _log.error(f"每日统计聚合失败: {e}")
            traceback.print_exc()

    def _aggregate_account_daily_stats(self, account, date):
        """为指定账户和日期聚合每日统计数据（优化版：支持5000-10000台设备）
        
        优化策略：
        1. 使用批量查询代替逐个查询
        2. 分页处理设备数据
        3. 使用UNION ALL合并多个设备表查询
        """
        try:
            _log.info(f"账户[{account}]开始聚合 {date} 的每日统计数据")
            date_str = date.strftime("%Y-%m-%d")

            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 获取账户下的所有设备及其区域信息
                    cursor.execute(
                        """
                        SELECT `设备号`, `区域1`, `区域2`, `区域3` 
                        FROM `device_info` 
                        WHERE `账户` = %s
                        """,
                        (account,)
                    )
                    devices = cursor.fetchall()

                    if not devices:
                        _log.warning(f"账户[{account}]没有设备数据")
                        return

                    _log.info(f"账户[{account}]共有 {len(devices)} 台设备需要聚合")

                    # 按区域分组设备
                    area_groups = {'ALL': []}  # ALL包含所有设备
                    for dev in devices:
                        dev_id = dev['设备号']
                        area1 = dev['区域1'] or ''
                        area2 = dev['区域2'] or ''
                        area3 = dev['区域3'] or ''

                        area_groups['ALL'].append(dev_id)

                        # 按区域路径分组
                        if area1:
                            area_path = area1
                            if area_path not in area_groups:
                                area_groups[area_path] = []
                            area_groups[area_path].append(dev_id)

                            if area2:
                                area_path = f"{area1}/{area2}"
                                if area_path not in area_groups:
                                    area_groups[area_path] = []
                                area_groups[area_path].append(dev_id)

                                if area3:
                                    area_path = f"{area1}/{area2}/{area3}"
                                    if area_path not in area_groups:
                                        area_groups[area_path] = []
                                    area_groups[area_path].append(dev_id)

                    # 使用批量查询获取所有设备的在线状态和能耗
                    # 分页处理，每批100个设备，避免SQL过长
                    batch_size = 100
                    all_device_stats = {}  # {dev_id: {'online': bool, 'electricity': int}}

                    for i in range(0, len(devices), batch_size):
                        batch = devices[i:i + batch_size]
                        batch_ids = [dev['设备号'] for dev in batch]

                        # 构建UNION ALL查询
                        union_parts = []
                        for dev_id in batch_ids:
                            union_parts.append(f"""
                                SELECT '{dev_id}' as dev_id, `在线`, `用电量` 
                                FROM `{dev_id}_parsed` 
                                WHERE `日期` = '{date_str}'
                            """)

                        if union_parts:
                            union_sql = " UNION ALL ".join(union_parts)
                            try:
                                cursor.execute(union_sql)
                                rows = cursor.fetchall()
                                for row in rows:
                                    all_device_stats[row['dev_id']] = {
                                        'online': bool(row['在线']),
                                        'electricity': row['用电量'] or 0
                                    }
                            except Exception as e:
                                _log.warning(f"批量查询设备数据失败: {e}")
                                # 批量查询失败，回退到逐个查询
                                for dev_id in batch_ids:
                                    try:
                                        cursor.execute(
                                            f"SELECT `在线`, `用电量` FROM `{dev_id}_parsed` WHERE `日期` = %s",
                                            (date_str,)
                                        )
                                        row = cursor.fetchone()
                                        if row:
                                            all_device_stats[dev_id] = {
                                                'online': bool(row['在线']),
                                                'electricity': row['用电量'] or 0
                                            }
                                    except Exception:
                                        pass

                    # 聚合每个区域的统计数据
                    online_stats = []  # 在线率统计
                    electricity_stats = []  # 能耗统计

                    for area_path, dev_ids in area_groups.items():
                        total_devices = len(dev_ids)
                        online_count = 0
                        total_electricity = 0

                        # 从批量查询结果中统计
                        for dev_id in dev_ids:
                            if dev_id in all_device_stats:
                                stats = all_device_stats[dev_id]
                                if stats['online']:
                                    online_count += 1
                                total_electricity += stats['electricity']

                        # 计算在线率
                        online_rate = (online_count / total_devices * 100) if total_devices > 0 else 0

                        # 添加到统计列表
                        online_stats.append({
                            'account': account,
                            'date': date,
                            'area_path': area_path,
                            'total_devices': total_devices,
                            'online_count': online_count,
                            'online_rate': round(online_rate, 2)
                        })

                        electricity_stats.append({
                            'account': account,
                            'date': date,
                            'area_path': area_path,
                            'total_devices': total_devices,
                            'total_electricity': total_electricity
                        })

                    # 批量写入在线率汇总表
                    if online_stats:
                        # 写入全部汇总表
                        all_online_data = [d for d in online_stats if d['area_path'] == 'ALL']
                        if all_online_data:
                            sql_online_all = """
                                INSERT INTO `summary_daily_online`
                                (`账户`, `日期`, `设备总数`, `在线设备数`, `在线率`)
                                VALUES (%s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    `设备总数` = VALUES(`设备总数`),
                                    `在线设备数` = VALUES(`在线设备数`),
                                    `在线率` = VALUES(`在线率`),
                                    `创建时间` = CURRENT_TIMESTAMP
                            """
                            cursor.executemany(sql_online_all, [
                                (d['account'], d['date'], d['total_devices'], d['online_count'], d['online_rate'])
                                for d in all_online_data
                            ])

                        # 写入区域汇总表
                        area_online_data = [d for d in online_stats if d['area_path'] != 'ALL']
                        if area_online_data:
                            sql_online_area = """
                                INSERT INTO `summary_daily_online_by_area`
                                (`账户`, `日期`, `区域路径`, `设备数`, `在线设备数`, `在线率`)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    `设备数` = VALUES(`设备数`),
                                    `在线设备数` = VALUES(`在线设备数`),
                                    `在线率` = VALUES(`在线率`),
                                    `创建时间` = CURRENT_TIMESTAMP
                            """
                            # 分批写入，每批1000条
                            for i in range(0, len(area_online_data), 1000):
                                batch = area_online_data[i:i + 1000]
                                cursor.executemany(sql_online_area, [
                                    (d['account'], d['date'], d['area_path'], d['total_devices'], d['online_count'], d['online_rate'])
                                    for d in batch
                                ])

                    # 批量写入能耗汇总表
                    if electricity_stats:
                        # 写入全部汇总表
                        all_elec_data = [d for d in electricity_stats if d['area_path'] == 'ALL']
                        if all_elec_data:
                            sql_elec_all = """
                                INSERT INTO `summary_daily_electricity`
                                (`账户`, `日期`, `设备总数`, `总用电量`)
                                VALUES (%s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    `设备总数` = VALUES(`设备总数`),
                                    `总用电量` = VALUES(`总用电量`),
                                    `创建时间` = CURRENT_TIMESTAMP
                            """
                            cursor.executemany(sql_elec_all, [
                                (d['account'], d['date'], d['total_devices'], d['total_electricity'])
                                for d in all_elec_data
                            ])

                        # 写入区域汇总表
                        area_elec_data = [d for d in electricity_stats if d['area_path'] != 'ALL']
                        if area_elec_data:
                            sql_elec_area = """
                                INSERT INTO `summary_daily_electricity_by_area`
                                (`账户`, `日期`, `区域路径`, `设备数`, `总用电量`)
                                VALUES (%s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    `设备数` = VALUES(`设备数`),
                                    `总用电量` = VALUES(`总用电量`),
                                    `创建时间` = CURRENT_TIMESTAMP
                            """
                            # 分批写入，每批1000条
                            for i in range(0, len(area_elec_data), 1000):
                                batch = area_elec_data[i:i + 1000]
                                cursor.executemany(sql_elec_area, [
                                    (d['account'], d['date'], d['area_path'], d['total_devices'], d['total_electricity'])
                                    for d in batch
                                ])

                    conn.commit()

            _log.info(f"账户[{account}] {date} 的每日统计聚合完成: {len(online_stats)} 个区域, {len(devices)} 台设备")

        except Exception as e:
            _log.error(f"账户[{account}]每日统计聚合失败: {e}")
            traceback.print_exc()

    def _aggregate_power_data(self):
        """执行功率数据预聚合（按账户隔离）"""
        try:
            _log.info("开始执行功率数据预聚合（按账户隔离）")

            # 获取所有账户
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT DISTINCT `账户` FROM `device_info` WHERE `账户` != ''")
                    accounts = [row['账户'] for row in cursor.fetchall()]

            if not accounts:
                _log.warning("没有账户数据，跳过预聚合")
                return

            # 计算最近24个时间点（过去24分钟，每分钟一个点）- 验证模式
            now = datetime.now()
            time_points = []
            for i in range(Config.POWER_TIME_POINTS - 1, -1, -1):  # 24个点 = 24分钟
                point = now - timedelta(minutes=i)
                point = point.replace(second=0, microsecond=0)
                time_points.append(point)
            
            _log.debug(f"预聚合时间范围: {time_points[0]} 到 {time_points[-1]}, 共 {len(time_points)} 个点")

            # 为每个账户分别聚合
            for account in accounts:
                self._aggregate_account_power_data(account, time_points)

        except Exception as e:
            _log.error(f"功率预聚合失败: {e}")
            traceback.print_exc()
    
    def _aggregate_account_power_data(self, account, time_points):
        """为指定账户执行功率数据预聚合"""
        try:
            _log.debug(f"开始聚合账户[{account}]的功率数据")

            # 获取该账户的设备及其区域信息
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT d.`设备号`, d.`区域1`, d.`区域2`, d.`区域3`,
                               CONCAT_WS('/', 
                                   NULLIF(d.`区域1`, ''), 
                                   NULLIF(d.`区域2`, ''), 
                                   NULLIF(d.`区域3`, '')
                               ) as `区域路径`
                        FROM `device_info` d
                        WHERE d.`账户` = %s
                    """, (account,))
                    devices = cursor.fetchall()

            if not devices:
                _log.debug(f"账户[{account}]没有设备，跳过")
                return

            # 构建区域分组
            area_groups = {}  # {区域路径: [设备号列表]}
            all_devices = []

            for dev in devices:
                dev_id = dev['设备号']
                area_path = dev['区域路径'] or '未分类'

                all_devices.append(dev_id)

                if area_path not in area_groups:
                    area_groups[area_path] = []
                area_groups[area_path].append(dev_id)

                # 同时按父区域分组（支持层级筛选）
                parts = area_path.split('/')
                for i in range(1, len(parts)):
                    parent_path = '/'.join(parts[:i])
                    if parent_path not in area_groups:
                        area_groups[parent_path] = []
                    area_groups[parent_path].append(dev_id)

            # 添加"全部"分组
            area_groups['ALL'] = all_devices

            # 按区域聚合功率数据
            aggregated_data = []
            total_query_count = 0
            total_power_found = 0

            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    for area_path, dev_list in area_groups.items():
                        for point_time in time_points:
                            total_power = 0
                            online_count = 0
                            valid_device_count = 0  # 有功率数据的设备数（包括功率为0的）

                            # 批量查询设备功率（使用配置批量大小）
                            batch_size = Config.BATCH_QUERY_SIZE
                            for i in range(0, len(dev_list), batch_size):
                                batch = dev_list[i:i + batch_size]
                                
                                # 构建批量查询 - 使用 UNION ALL 优化多表查询
                                union_queries = []
                                query_params = []
                                
                                for dev_id in batch:
                                    power_table = f"{dev_id}_power"
                                    union_queries.append(
                                        f"SELECT %s as dev_id, `功率` FROM `{power_table}` WHERE `时间点` = %s LIMIT 1"
                                    )
                                    query_params.extend([dev_id, point_time])
                                
                                if union_queries:
                                    try:
                                        # 执行批量查询
                                        batch_sql = " UNION ALL ".join(union_queries)
                                        cursor.execute(batch_sql, query_params)
                                        rows = cursor.fetchall()
                                        total_query_count += len(batch)
                                        
                                        # 处理查询结果
                                        power_map = {row['dev_id']: row['功率'] for row in rows if row.get('功率') is not None}
                                        
                                        # 处理每个设备（聚合时不使用回退，只使用实际存在的功率数据）
                                        for dev_id in batch:
                                            power = power_map.get(dev_id)  # 可能是NULL、0或正数
                                            has_data = power is not None
                                            
                                            # 聚合时不使用回退逻辑，只统计实际有数据的时间点
                                            # 这样可以避免设备离线后仍然显示回退功率的问题
                                            
                                            # 只有实际有数据（包括功率为0）才计入统计
                                            if has_data and power is not None:
                                                total_power += power
                                                valid_device_count += 1
                                                # 功率大于0视为在线，功率为0视为待机但仍计入在线
                                                online_count += 1
                                                if power > 0:
                                                    total_power_found += 1
                                    except Exception as e:
                                        _log.debug(f"批量查询功率失败: {e}")
                                        # 批量查询失败，回退到逐个查询（不使用回退逻辑）
                                        for dev_id in batch:
                                            try:
                                                power_table = f"{dev_id}_power"
                                                cursor.execute(
                                                    f"SELECT `功率` FROM `{power_table}` WHERE `时间点` = %s LIMIT 1",
                                                    (point_time,)
                                                )
                                                row = cursor.fetchone()
                                                total_query_count += 1
                                                
                                                power = row.get('功率') if row else None
                                                has_data = power is not None
                                                
                                                # 聚合时不使用回退逻辑
                                                if has_data and power is not None:
                                                    total_power += power
                                                    valid_device_count += 1
                                                    online_count += 1
                                                    if power > 0:
                                                        total_power_found += 1
                                            except Exception:
                                                pass

                            # 修复问题4：确保设备总数与在线设备数逻辑一致
                            # total_devices使用实际有数据的设备数，而不是区域分组中的全部设备
                            aggregated_data.append({
                                'account': account,
                                'time_point': point_time,
                                'area_path': area_path,
                                'total_devices': valid_device_count,  # 使用实际有功率数据的设备数
                                'total_power': total_power,
                                'online_count': online_count
                            })
            
            _log.debug(f"账户[{account}]预聚合查询统计: 共查询 {total_query_count} 次，找到 {total_power_found} 个有效功率值")

            # 批量写入汇总表
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 写入全部汇总表（带账户字段）
                    all_data = [d for d in aggregated_data if d['area_path'] == 'ALL']
                    if all_data:
                        sql_all = """
                            INSERT INTO `summary_power` 
                            (`账户`, `时间点`, `设备总数`, `功率之和`, `在线设备数`)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                `设备总数` = VALUES(`设备总数`),
                                `功率之和` = VALUES(`功率之和`),
                                `在线设备数` = VALUES(`在线设备数`),
                                `创建时间` = CURRENT_TIMESTAMP
                        """
                        cursor.executemany(sql_all, [
                            (d['account'], d['time_point'], d['total_devices'], d['total_power'], d['online_count'])
                            for d in all_data
                        ])

                    # 写入区域汇总表（带账户字段）
                    area_data = [d for d in aggregated_data if d['area_path'] != 'ALL']
                    if area_data:
                        sql_area = """
                            INSERT INTO `summary_power_by_area` 
                            (`账户`, `时间点`, `区域路径`, `设备数`, `功率之和`, `在线设备数`)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                `设备数` = VALUES(`设备数`),
                                `功率之和` = VALUES(`功率之和`),
                                `在线设备数` = VALUES(`在线设备数`),
                                `创建时间` = CURRENT_TIMESTAMP
                        """
                        # 分批写入，每批1000条
                        batch_size = 1000
                        for i in range(0, len(area_data), batch_size):
                            batch = area_data[i:i + batch_size]
                            cursor.executemany(sql_area, [
                                (d['account'], d['time_point'], d['area_path'], d['total_devices'], 
                                 d['total_power'], d['online_count'])
                                for d in batch
                            ])

                    conn.commit()

            _log.info(f"账户[{account}]功率预聚合完成：{len(area_groups)} 个区域，{len(aggregated_data)} 条记录")

            # 同时缓存到Redis（如果可用，带账户隔离）
            if self.redis_client:
                self._cache_aggregation_to_redis_with_account(aggregated_data)

        except Exception as e:
            _log.error(f"账户[{account}]功率预聚合失败: {e}")
            traceback.print_exc()
    
    def _get_power_with_state_aware_fallback(self, cursor, dev_id, point_time):
        """状态感知回退策略 - 根据设备最后数据时间决定是否回退
        
        Returns:
            tuple: (power, has_data)
        """
        try:
            # 获取设备最后数据时间
            last_data_time = None
            with self.cache_lock:
                cache = self.deivce_parsed_cache.get(dev_id, {})
                last_data_time = cache.get('最后数据时间')
            
            # 如果没有最后数据时间，尝试从_power表查询最近的有效数据时间
            if not last_data_time:
                power_table = f"{dev_id}_power"
                cursor.execute(
                    f"SELECT `时间点` FROM `{power_table}` WHERE `功率` IS NOT NULL ORDER BY `时间点` DESC LIMIT 1",
                )
                row = cursor.fetchone()
                if row:
                    last_data_time = row['时间点']
            
            # 如果仍然没有最后数据时间，无法回退
            if not last_data_time:
                return None, False
            
            # 计算距离最后数据的时间差
            time_diff_seconds = abs((point_time - last_data_time).total_seconds())
            
            # 如果超过最大回退间隔（等于离线时间），视为离线，不回退
            if time_diff_seconds > Config.OFFLINE_THRESHOLD:
                _log.debug(f"设备 {dev_id} 超过离线时间({Config.OFFLINE_THRESHOLD}秒={Config.OFFLINE_THRESHOLD // 60}分钟)，不回退 [上报间隔:{Config.DEVICE_REPORT_INTERVAL // 60}分钟]")
                return None, False
            
            # 在回退范围内，查询最近的有效功率
            power_table = f"{dev_id}_power"
            cursor.execute(
                f"SELECT `功率` FROM `{power_table}` WHERE `时间点` <= %s AND `功率` IS NOT NULL ORDER BY `时间点` DESC LIMIT 1",
                (point_time,)
            )
            row = cursor.fetchone()
            
            if row:
                power = row.get('功率')
                if power is not None:
                    _log.debug(f"设备 {dev_id} 使用回退功率: {power}W [最后数据:{last_data_time}, 时间差:{time_diff_seconds:.0f}秒, 离线阈值:{Config.OFFLINE_THRESHOLD // 60}分钟, 上报间隔:{Config.DEVICE_REPORT_INTERVAL // 60}分钟]")
                    return power, True
            
            return None, False
        except Exception as e:
            _log.debug(f"状态感知回退查询失败: {e}")
            return None, False
    
    def _get_power_with_fixed_fallback(self, cursor, dev_id, point_time):
        """固定时间回退策略 - 在固定时间范围内回退
        
        Returns:
            tuple: (power, has_data)
        """
        try:
            fallback_minutes = Config.FALLBACK_FIXED_MINUTES
            power_table = f"{dev_id}_power"
            
            # 查询范围：[point_time - fallback_minutes, point_time]
            cursor.execute(
                f"SELECT `功率` FROM `{power_table}` WHERE `时间点` >= %s AND `时间点` <= %s AND `功率` IS NOT NULL ORDER BY `时间点` DESC LIMIT 1",
                (point_time - timedelta(minutes=fallback_minutes), point_time)
            )
            row = cursor.fetchone()
            
            if row:
                power = row.get('功率')
                if power is not None:
                    _log.debug(f"设备 {dev_id} 使用固定时间回退功率: {power}W [回退时间:{fallback_minutes}分钟, 上报间隔:{Config.DEVICE_REPORT_INTERVAL // 60}分钟]")
                    return power, True
            
            return None, False
        except Exception as e:
            _log.debug(f"固定时间回退查询失败: {e}")
            return None, False
    
    def _cache_aggregation_to_redis_with_account(self, aggregated_data):
        """将预聚合数据缓存到Redis（带账户隔离，支持NULL功率值）"""
        try:
            pipe = self.redis_client.pipeline()

            for data in aggregated_data:
                # Redis key格式: power:{账户}:{区域路径}:{时间点}
                key = f"power:{data['account']}:{data['area_path']}:{data['time_point'].strftime('%Y%m%d%H%M')}"
                
                # 支持NULL功率值（None表示无数据，0表示功率为0）
                total_power = data['total_power']
                value = {
                    'account': data['account'],
                    'time_point': data['time_point'].isoformat(),
                    'area_path': data['area_path'],
                    'total_devices': data['total_devices'],
                    'total_power': total_power if total_power is not None else None,  # NULL表示无数据
                    'online_count': data['online_count'],
                    'has_data': total_power is not None  # 标记是否有数据
                }
                pipe.setex(key, 3600, json.dumps(value))  # 缓存1小时

            pipe.execute()
            _log.debug(f"预聚合数据已缓存到Redis（账户隔离）: {len(aggregated_data)} 条")
        except Exception as e:
            _log.warning(f"缓存到Redis失败: {e}")

    def _cache_aggregation_to_redis(self, aggregated_data):
        """将预聚合数据缓存到Redis（支持NULL功率值）"""
        try:
            pipe = self.redis_client.pipeline()

            for data in aggregated_data:
                key = f"power:{data['area_path']}:{data['time_point'].strftime('%Y%m%d%H%M')}"
                
                # 支持NULL功率值（None表示无数据，0表示功率为0）
                total_power = data['total_power']
                value = {
                    'time_point': data['time_point'].isoformat(),
                    'area_path': data['area_path'],
                    'total_devices': data['total_devices'],
                    'total_power': total_power if total_power is not None else None,  # NULL表示无数据
                    'online_count': data['online_count'],
                    'has_data': total_power is not None  # 标记是否有数据
                }
                pipe.setex(key, 3600, json.dumps(value))  # 缓存1小时

            pipe.execute()
            _log.debug(f"预聚合数据已缓存到Redis: {len(aggregated_data)} 条")
        except Exception as e:
            _log.warning(f"缓存到Redis失败: {e}")
    
    def _data_delay_monitor(self):
        """数据延迟监控线程 - 监控设备数据入库延迟"""
        _log.info("数据延迟监控线程启动")
        _log.info(f"  检查间隔: {Config.DATA_DELAY_CHECK_INTERVAL}秒")
        _log.info(f"  告警阈值: {Config.DATA_DELAY_THRESHOLD}秒 ({Config.DATA_DELAY_THRESHOLD // 60}分钟)")
        _log.info(f"  说明: 超过离线时间({Config.OFFLINE_THRESHOLD // 60}分钟)未上报数据的设备将触发告警")
        last_check_time = {}
        
        while not self.shutdown_event.is_set():
            try:
                # 检查间隔
                for _ in range(Config.DATA_DELAY_CHECK_INTERVAL):
                    if self.shutdown_event.is_set():
                        return
                    sleep(Config.THREAD_SLEEP_INTERVAL)
                
                # 获取所有设备
                devices = []
                with self.cache_lock:
                    devices = list(self.deivce_parsed_cache.keys())
                
                if not devices:
                    continue
                
                now = datetime.now()
                delayed_devices = []
                
                for dev_id in devices:
                    try:
                        with self.cache_lock:
                            cache = self.deivce_parsed_cache.get(dev_id, {})
                            last_data_time = cache.get('功率时间')
                        
                        if not last_data_time:
                            continue
                        
                        # 计算数据延迟
                        delay_seconds = (now - last_data_time).total_seconds()
                        
                        # 如果延迟超过阈值，记录告警
                        if delay_seconds > Config.DATA_DELAY_THRESHOLD:
                            # 避免重复告警（同一设备5分钟内只告警一次）
                            last_alert = last_check_time.get(dev_id)
                            if not last_alert or (now - last_alert).total_seconds() > 300:
                                delayed_devices.append({
                                    'dev_id': dev_id,
                                    'delay': delay_seconds,
                                    'last_data_time': last_data_time
                                })
                                last_check_time[dev_id] = now
                    except Exception as e:
                        _log.debug(f"检查设备 {dev_id} 数据延迟失败: {e}")
                
                # 记录告警日志
                if delayed_devices:
                    _log.warning(f"数据延迟告警: 发现 {len(delayed_devices)} 个设备数据延迟超过 {Config.DATA_DELAY_THRESHOLD} 秒")
                    for dev in delayed_devices[:10]:  # 最多显示10个
                        _log.warning(f"  - 设备 {dev['dev_id']}: 延迟 {dev['delay']:.0f} 秒, 最后数据时间: {dev['last_data_time']}")
                    
                    # 如果延迟设备过多，记录到专门的告警日志
                    if len(delayed_devices) > 20:
                        _log.error(f"严重数据延迟: 共 {len(delayed_devices)} 个设备数据延迟，请检查系统状态")
                
            except Exception as e:
                if not self.shutdown_event.is_set():
                    _log.error(f"数据延迟监控线程异常: {e}")
                    traceback.print_exc()
    
    def _update_subscriptions(self):
        """更新MQTT订阅"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 设备号 FROM device_info")
                    devices = cursor.fetchall()

            for dev in devices:
                dev_id = dev["设备号"]
                # MqttClient.subscribe 内部会检查是否已订阅
                self._create_device_table(dev_id) #先创建表在订阅-防止接收了数据，表不存在
                if self.client.subscribe(dev_id):
                    _log.debug(f"订阅设备主题: {dev_id}")

        except Exception as e:
            _log.error(f"更新订阅失败: {e}")
    
    def start(self):
        """启动服务端"""
        _log.info("=" * 50)
        _log.info("服务端启动")
        _log.info("=" * 50)

        # 保存线程引用
        self._threads = []

        # 启动后台线程
        threads = [
            Thread(target=self._log_rotator, name="LogRotator", daemon=True),
            Thread(target=self._db_inserter, name="DBInserter", daemon=True),
            Thread(target=self._device_monitor, name="DeviceMonitor", daemon=True),
            Thread(target=self._power_monitor, name="PowerMonitor", daemon=True),
            Thread(target=self._power_aggregator, name="PowerAggregator", daemon=True),  # 功率预聚合线程
            Thread(target=self._daily_stats_aggregator, name="DailyStatsAggregator", daemon=True),  # 每日在线率和能耗聚合线程
            Thread(target=self._data_delay_monitor, name="DataDelayMonitor", daemon=True),  # 数据延迟监控线程
        ]

        for t in threads:
            t.start()
            self._threads.append(t)
            _log.info(f"启动线程: {t.name}")

        # 初始订阅
        self._update_subscriptions()

        # 主循环
        try:
            while not self.shutdown_event.is_set():
                sleep(Config.THREAD_SLEEP_INTERVAL)
        except KeyboardInterrupt:
            _log.info("收到键盘中断信号")
        finally:
            self.stop()

    def stop(self):
        """停止服务端"""
        _log.info("正在停止服务端...")
        self.shutdown_event.set()

        # 等待后台线程退出（最多5秒）
        if hasattr(self, '_threads'):
            for t in self._threads:
                if t.is_alive():
                    t.join(timeout=2)
                    _log.info(f"线程 {t.name} 已停止")

        # 停止MQTT客户端
        if self.client:
            try:
                self.client.stop()
                _log.info("MQTT客户端已停止")
            except Exception as e:
                _log.error(f"停止MQTT客户端失败: {e}")

        # 关闭数据库连接池
        if self.db_pool:
            try:
                self.db_pool.close()
                _log.info("数据库连接池已关闭")
            except Exception as e:
                _log.error(f"关闭数据库连接池失败: {e}")

        _log.info("服务端已停止")


# ===================== 信号处理 =====================
def signal_handler(signum, frame):
    """信号处理函数"""
    signals = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM"
    }
    sig_name = signals.get(signum, f"Signal({signum})")
    _log.info(f"收到 {sig_name} 信号，准备退出...")
    
    if hasattr(signal_handler, 'server'):
        signal_handler.server.stop()
    sys.exit(0)


# ===================== 主入口 =====================
if __name__ == "__main__":
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Windows 不支持 SIGTERM，但保留代码兼容性
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        server = Server()
        signal_handler.server = server
        server.start()
    except Exception as e:
        _log.error(f"服务端启动失败: {e}")
        traceback.print_exc()
        sys.exit(1)
