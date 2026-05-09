import random
import time
import datetime
import json
import threading
import os
import logging
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import paho.mqtt.client as mqtt
from paho.mqtt import client as mqtt_client

# ====================== 【配置项】你只需要改这里 ======================
MQTT_BROKER = "opr.iotdirvers.com"
MQTT_PORT = 1883
MQTT_USERNAME = ""
MQTT_PASSWORD = ""
# 发布时 # 会自动替换成 SN
MQTT_TOPIC_TEMPLATE = "MS/{sn}/dev2plt"
MQTT_QOS = 0

DEVICE_COUNT = 12  # 模拟设备数量
PROCESS_COUNT = min(16, cpu_count())  # 进程数，默认CPU核心数，最多16个
DEVICES_PER_PROCESS = DEVICE_COUNT // PROCESS_COUNT  # 每进程设备数

REPORT_MIN = 30   # 最小上报间隔(秒) - 固定5分钟
REPORT_MAX = 31 # 最大上报间隔(秒) - 固定30分钟

FIXED_CT = "C"
FIXED_SV = "rept"

# 日志配置
LOG_LEVEL = logging.INFO
PRINT_INTERVAL = 100  # 每多少条打印一次日志
# =================================================================

# 配置日志
def setup_logging():
    """配置日志，避免print阻塞"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(processName)s - %(message)s',
        handlers=[
            logging.FileHandler(f'device_test_{current_process().name}.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_sn():
    return str(random.randint(1, 9)) + ''.join(random.choices('0123456789', k=14))

# ====================== MQTT连接池 ======================
class MqttConnectionPool:
    """MQTT连接池，多个设备共享连接"""
    def __init__(self, pool_size=10, logger=None):
        self.pool_size = pool_size
        self.clients = []
        self.locks = []
        self.connected = []
        self.logger = logger or logging.getLogger(__name__)
        self._init_connections()
    
    def _init_connections(self):
        """初始化连接池"""
        for i in range(self.pool_size):
            client = mqtt_client.Client(
                callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
                client_id=f"pool_{current_process().name}_{i}_{int(time.time())}"
            )
            if MQTT_USERNAME and MQTT_PASSWORD:
                client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 60)
                client.loop_start()
                self.clients.append(client)
                self.locks.append(threading.Lock())
                self.connected.append(True)
                self.logger.info(f"连接池客户端 {i} 连接成功")
            except Exception as e:
                self.logger.error(f"连接池客户端 {i} 连接失败: {e}")
                self.clients.append(None)
                self.locks.append(None)
                self.connected.append(False)
    
    def get_client(self, device_index):
        """根据设备索引获取客户端（轮询）"""
        pool_idx = device_index % self.pool_size
        if self.connected[pool_idx]:
            return self.clients[pool_idx], self.locks[pool_idx]
        return None, None
    
    def publish(self, device_index, topic, payload, qos=MQTT_QOS):
        """线程安全的发布"""
        client, lock = self.get_client(device_index)
        if client and lock:
            with lock:
                try:
                    result = client.publish(topic, payload, qos)
                    self.logger.info(topic)
                    return result.rc == mqtt.MQTT_ERR_SUCCESS
                except Exception as e:
                    self.logger.error(f"发布失败: {e}")
                    return False
        return False
    
    def stop_all(self):
        """停止所有连接"""
        for i, client in enumerate(self.clients):
            if client and self.connected[i]:
                try:
                    client.loop_stop()
                    client.disconnect()
                except:
                    pass

# ====================== 设备线程（优化版）======================
class DeviceThread(threading.Thread):
    def __init__(self, sn: str, device_index: int, mqtt_pool: MqttConnectionPool, logger=None):
        super().__init__(daemon=True)
        self.sn = sn
        self.device_index = device_index
        self.mqtt_pool = mqtt_pool
        self.logger = logger or logging.getLogger(__name__)
        self.running = True

        # 每台设备自己维护上报条数ID，从1开始
        self.report_id = 1
        self.last_print_id = 0

        # 独立上报周期
        self.interval = random.uniform(REPORT_MIN, REPORT_MAX)

        # 累加字段（线性增长）
        self.total_run_time = random.randint(1000, 50000)
        self.total_energy = random.randint(1000, 100000)
        self.total_light_time = random.randint(1000, 50000)

        # 拼接真实主题
        self.mqtt_topic = MQTT_TOPIC_TEMPLATE.format(sn=sn)

    def generate_payload(self):
        # 上报条数ID自增
        current_id = f"{self.report_id:06d}"
        self.report_id += 1

        # 累加字段持续增长
        self.total_run_time += random.randint(1, 4)
        self.total_energy += random.randint(5, 50)
        self.total_light_time += random.randint(1, 4)

        sts_list = [0, 11, 12, 21, 31, 32]

        return {
            "CT": FIXED_CT,
            "DT": {
                "RunTm": {
                    "rTime": random.randint(0, 1440),
                    "tTime": self.total_run_time
                },
                "RunSts": {
                    "bri": [random.randint(0, 100)],
                    "sts": [random.choice(sts_list)]
                },
                "EleInfo": {
                    "c": [random.randint(0, 10000)],
                    "e": [random.choices([0, 1], [95, 5])[0]],
                    "f": [random.randint(490, 510)],
                    "p": [random.randint(0, 400)],
                    "v": [random.randint(2000, 2400)],
                    "cm": 0,
                    "oc": [random.randint(0, 1000)],
                    "op": [random.randint(0, 400)],
                    "ov": [random.randint(0, 1000)],
                    "vp": [random.choices([0,1,2,3,4], [95,1.25,1.25,1.25,1.25])[0]],
                    "eff": [random.randint(850, 950)],
                    "pwr": random.choices([0,1], [95,5])[0],
                    "rEc": [random.randint(0, 1000)],
                    "tEc": [self.total_energy],
                    "cons": [random.choices([0,1], [95,5])[0]],
                    "open": [random.choices([0,1], [95,5])[0]],
                    "ovp": random.choices([0,1], [95,5])[0],
                    "ovtp": random.choices([0,1,2,3,4,5,6,7], [95,0.7,0.7,0.7,0.7,0.7,0.7,0.7])[0],
                    "lc": [random.randint(0, 100)]
                },
                "LightTm": {
                    "rLtTime": [random.randint(0, 1440)],
                    "tLtTime": [self.total_light_time]
                }
            },
            "ID": current_id,
            "SN": self.sn,
            "SV": FIXED_SV,
            "TM": get_time()
        }

    def run(self):
        """设备主循环"""
        while self.running:
            try:
                data = self.generate_payload()
                payload = json.dumps(data, ensure_ascii=False)
                
                # 使用连接池发布
                success = self.mqtt_pool.publish(
                    self.device_index, 
                    self.mqtt_topic, 
                    payload, 
                    MQTT_QOS
                )
                
                # 抽样打印日志（每100条）
                if self.report_id - self.last_print_id >= PRINT_INTERVAL:
                    if success:
                        self.logger.info(f"设备 {self.sn} | ID:{self.report_id-1:06d} | 周期:{self.interval:.1f}s | 成功")
                    else:
                        self.logger.warning(f"设备 {self.sn} | ID:{self.report_id-1:06d} | 发布失败")
                    self.last_print_id = self.report_id - 1
                
                time.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"设备 {self.sn} 异常: {e}")
                time.sleep(2)

    def stop(self):
        self.running = False

# ====================== 进程工作函数 ======================
def run_device_process(process_id, sn_list):
    """每个进程运行一批设备"""
    logger = setup_logging()
    logger.info(f"进程 {process_id} 启动，管理 {len(sn_list)} 个设备")
    
    # 创建MQTT连接池（每进程10个连接）
    pool_size = min(10, len(sn_list))
    mqtt_pool = MqttConnectionPool(pool_size=pool_size, logger=logger)
    
    # 创建设备线程
    devices = []
    for i, sn in enumerate(sn_list):
        device_index = process_id * DEVICES_PER_PROCESS + i
        t = DeviceThread(sn, device_index, mqtt_pool, logger)
        t.start()
        devices.append(t)
        time.sleep(0.005)  # 快速启动，减少 stagger
    
    logger.info(f"进程 {process_id} 所有设备已启动")
    
    # 保持运行
    try:
        while True:
            time.sleep(1)
            # 检查设备状态
            alive_count = sum(1 for d in devices if d.is_alive())
            if alive_count < len(devices):
                logger.warning(f"进程 {process_id} 设备异常: {alive_count}/{len(devices)}")
    except KeyboardInterrupt:
        logger.info(f"进程 {process_id} 收到停止信号")
    finally:
        # 停止所有设备
        for d in devices:
            d.stop()
        for d in devices:
            d.join(timeout=2)
        mqtt_pool.stop_all()
        logger.info(f"进程 {process_id} 已停止")

# ====================== 启动 + 生成设备TXT文件 ======================
def generate_device_list():
    """生成或读取设备列表"""
    sn_list = []
    device_list_file = "device_list.txt"

    if os.path.exists(device_list_file):
        print(f"📄 发现设备列表文件：{device_list_file}")
        with open(device_list_file, "r", encoding="utf-8") as f:
            for line in f:
                if "| SN：" in line:
                    sn = line.split("| SN：")[1].strip()
                    sn_list.append(sn)
                    print(sn)
                    if len(sn_list) >= DEVICE_COUNT:
                        break
        print(f"✅ 从文件读取 {len(sn_list)} 个设备")
    else:
        print(f"📝 生成 {DEVICE_COUNT} 个新设备")
        for _ in range(DEVICE_COUNT):
            sn_list.append(generate_sn())

        with open(device_list_file, "w", encoding="utf-8") as f:
            f.write(f"模拟设备总数：{len(sn_list)}\n")
            f.write(f"生成时间：{get_time()}\n")
            f.write("-" * 50 + "\n")
            for idx, sn in enumerate(sn_list, 1):
                f.write(f"设备{idx:03d} | SN：{sn}\n")
        print(f"✅ 设备列表已保存到：{device_list_file}")
    
    return sn_list

def main():
    print(f"🚀 启动 {DEVICE_COUNT} 台设备模拟器")
    print(f"📊 进程数: {PROCESS_COUNT}, 每进程设备数: {DEVICES_PER_PROCESS}")
    print(f"⏱️  上报间隔: {REPORT_MIN}-{REPORT_MAX}秒")
    print(f"🔌 MQTT连接池: 每进程10个连接")
    print("-" * 50)
    
    # 读取设备列表
    sn_list = generate_device_list()
    
    if len(sn_list) < DEVICE_COUNT:
        print(f"⚠️  警告: 设备数量不足 {DEVICE_COUNT}，实际 {len(sn_list)}")
    
    # 分割设备到各进程
    batches = []
    for i in range(PROCESS_COUNT):
        start = i * DEVICES_PER_PROCESS
        end = start + DEVICES_PER_PROCESS
        batch = sn_list[start:end]
        if batch:
            batches.append((i, batch))
    
    print(f"\n✅ 分配完成: {len(batches)} 个进程批次")
    print("🚀 启动多进程...")
    print("⚠️  按 Ctrl+C 停止所有设备\n")
    
    # 启动多进程
    try:
        with Pool(PROCESS_COUNT) as pool:
            # 使用apply_async非阻塞启动
            results = []
            for process_id, batch in batches:
                result = pool.apply_async(run_device_process, (process_id, batch))
                results.append(result)
                time.sleep(0.5)  # 进程 staggered 启动
            
            # 等待所有进程完成
            while True:
                time.sleep(1)
                # 检查是否有进程异常
                for i, result in enumerate(results):
                    if result.ready() and not result.successful():
                        print(f"❌ 进程 {i} 异常退出")
                        
    except KeyboardInterrupt:
        print("\n🛑 主进程收到停止信号，正在终止...")
    finally:
        print("✅ 所有进程已停止")

if __name__ == "__main__":
    main()
