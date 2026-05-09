import queue
import threading
from collections import defaultdict
from weakref import WeakValueDictionary
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QDateTime, pyqtSignal, QObject
import time
from log_save import Logger
_log = Logger(True).logger
from generalfunction import get_time

class DeviceDataProcessor(QObject):
    # 信号：更新UI数据（设备号，数据字典）
    signal_update_ui = pyqtSignal(str, dict)
    def __init__(self, max_workers=30):
        super().__init__()
        """
        :param max_workers: 最大并发工作线程数（同时处理的设备数）
        """
        self.max_workers = max_workers
        
        # 设备队列 {device_id: Queue()}
        self.device_queues = {}
        
        # 设备工作线程 {device_id: Thread()}
        self.device_workers = {}
        
        # 线程锁
        self._lock = threading.Lock()
        
        # 空闲设备超时清理（可选）
        self._last_active = {}
        self._cleanup_timer = None

        # 配置
        self.device_model = None
        self.device_cols_index = None
        # self.signal_show = None
        self.signal_mess_show = None
        self.client = None
        self.topic_config = None
        self.send_order = None
        self.err_list = None
        self.apply_key_cols = None
        self.apply_FLOAT_cols = None
        self.apply_DATETIME_cols = None

        # 轮询索引，用于负载均衡分配设备到队列
        self._round_robin_index = 0
        # 队列到设备的映射 {queue_id: [dev1, dev2, ...]}
        self._queue_devices = {}


    def receive_data(self, topic, data):
        """接收数据入口（非阻塞）"""
        dev = topic.split("/")[1]

        with self._lock:
            # 创建新设备队列
            if dev not in self.device_queues:
                # 限制最大并发数 - 超过限制时轮询分配到现有队列
                if len(self.device_workers) >= self.max_workers:
                    # 轮询选择队列，实现负载均衡
                    queue_ids = list(self._queue_devices.keys())
                    if queue_ids:
                        selected_queue_id = queue_ids[self._round_robin_index % len(queue_ids)]
                        self._round_robin_index += 1

                        # _log.debug(f"线程数达上限，将设备 {dev} 分配到队列 {selected_queue_id}")

                        # 新设备使用选中的队列
                        self.device_queues[dev] = self._queue_devices[selected_queue_id]['queue']
                        self.device_workers[dev] = self._queue_devices[selected_queue_id]['thread']
                        self._queue_devices[selected_queue_id]['devices'].append(dev)
                        self._last_active[dev] = time.time()
                    else:
                        _log.error("队列为空，无法分配设备")
                        return
                else:
                    # 创建新队列和线程
                    q = queue.Queue(maxsize=100)  # 单设备队列上限
                    self.device_queues[dev] = q
                    self._last_active[dev] = time.time()

                    # 记录队列信息
                    queue_id = f"queue_{len(self._queue_devices)}"
                    self._queue_devices[queue_id] = {
                        'queue': q,
                        'thread': None,
                        'devices': [dev]
                    }

                    # 启动设备专属工作线程
                    t = threading.Thread(
                        target=self._device_worker,
                        args=(queue_id, q),
                        daemon=True,
                        name=f"Worker-{queue_id}"
                    )
                    t.start()
                    self.device_workers[dev] = t
                    self._queue_devices[queue_id]['thread'] = t
                    # _log.debug(f"为设备 {dev} 创建工作线程 {queue_id}，当前线程数: {len(self.device_workers)}")

            self._last_active[dev] = time.time()
        
        # 入队（队列满时丢弃旧数据，保留最新）
        try:
            self.device_queues[dev].put((topic, data), block=False)
        except queue.Full:
            # 丢弃最旧的数据，保留最新
            try:
                self.device_queues[dev].get_nowait()
                self.device_queues[dev].put((topic, data), block=False)
                _log.warning(f"设备 {dev} 队列满，丢弃旧数据")
            except queue.Empty:
                pass
    
    def _device_worker(self, queue_id, q):
        """队列工作线程（处理多个设备的数据）"""
        # _log.debug(f"工作线程 {queue_id} 启动")

        while True:
            try:
                # 等待数据，超时检查是否需要退出
                topic, data = q.get(timeout=60)

                # 处理数据
                dev = topic.split("/")[1]
                self._process_data(dev, topic, data)

                q.task_done()

            except queue.Empty:
                # 60秒无数据，检查该队列下所有设备是否都空闲
                with self._lock:
                    devices = self._queue_devices.get(queue_id, {}).get('devices', [])
                    all_idle = all(
                        time.time() - self._last_active.get(d, 0) > 60
                        for d in devices
                    )
                    if all_idle and devices:
                        _log.debug(f"队列 {queue_id} 下所有设备空闲，清理资源")
                        for d in devices:
                            self._cleanup_device(d, lock_acquired=True)  # 已持有锁，避免死锁
                        # 清理队列记录
                        if queue_id in self._queue_devices:
                            del self._queue_devices[queue_id]
                        break

        _log.debug(f"工作线程 {queue_id} 退出")
    
    def _process_data(self, dev, topic, data):
        """实际数据处理（原start_data逻辑）"""
        # 登录回复、校时、数据解析...
        # _log.debug(f"处理数据: {dev} {topic} {data}")
        
        result = {}
        if "SV" in data and "CT" in data :
            if data.get("ER")!= None and data.get("ER") != 0:
                self.signal_mess_show.emit("error", self.err_list[data["ER"]])
                return

            if data["SV"] == "ctrl" and data["CT"] == "W":

                pass
            elif data["SV"] == "rept" and data["CT"] == "L":  # 登录回复
                order = self.send_order["login_reply"]
                order["SN"] = dev
                order["ID"] = data["ID"]
                order["TM"] = get_time("UTC")
                if self.client.publish(self.topic_config["pub"].replace("#",dev),
                                        str(order).replace("'", "\"")):
                    _log.info("{} 登录回复成功！！！  {}".format(dev, str(order).replace("'", "\"")))
                else:
                    _log.error(f"{dev} 登录回复失败！！！")
            elif data["CT"] == "R" and data["SV"] == "rqst":  # 校时
                if "DO" in data["DT"].keys():
                    if data["DT"]["DO"] == "TmCali":
                        order = self.send_order["time_reply"]
                        order["SN"] = dev
                        order["ID"] = data["ID"]
                        order["TM"] = get_time("UTC")
                        if self.client.publish(self.topic_config["pub"].replace("#",dev),
                                                str(order).replace("'", "\"")):
                            pass
                            # log.debug("{} 校时回复成功！！！ {}".format(dev, str(order).replace("'","\"")))
                        else:
                            pass
                            # log.error(f"{dev} 校时回复失败！！！")
            else:
                result_flg = False # 数据解析标志位
                for col_name, config_list in self.apply_key_cols.items():
                    # _log.info(f"解析列 {col_name} 配置 {config_list}")
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
                            # 只存储原始数值和文本，不在后台线程创建Qt对象
                            result[col_name] = {
                                'text': str(text),
                                'value': text,
                                'type': 'FLOAT'
                            }
                            result_flg = True

                        elif "INT" in config_list[1]:
                            text = int(text)
                            if config_list[2] != 0:
                                text = text / (10 ** config_list[2])
                            # 只存储原始数值和文本，不在后台线程创建Qt对象
                            result[col_name] = {
                                'text': str(text),
                                'value': text,
                                'type': 'INT'
                            }
                            result_flg = True

                        elif "VARCHAR" in config_list[1]:
                            text = str(text)
                            # 只存储文本，不在后台线程创建Qt对象
                            result[col_name] = {
                                'text': str(text),
                                'type': 'VARCHAR'
                            }
                            result_flg = True

                        elif "DATETIME" in config_list[1]:
                            # 只存储文本，不在后台线程创建Qt对象
                            result[col_name] = {
                                'text': str(text),
                                'type': 'DATETIME'
                            }
                        else:
                            _log.error(f"出现非数据库类型数据 {col_name}  {config_list[1]}")
                    except Exception as e:
                        result[col_name] = {
                            'text': '-',
                            'type': 'EMPTY'
                        }
                        # _log.error(f"解析数据 {col_name} 失败：{str(e)}")
                # _log.info(f"{result_flg} 解析数据 {result}")
                if result_flg:
                    time_now = get_time("now")
                    result["当前时间"] = {
                        'text': time_now,
                        'type': 'DATETIME'
                    }
                    # _log.info(f"{dev} 解析数据 {result}")
                    # 发射信号到主线程更新UI，避免在工作线程中操作Qt对象
                    self.signal_update_ui.emit(dev, result)

    
    def _cleanup_device(self, dev, lock_acquired=False):
        """清理空闲设备资源
        
        Args:
            dev: 设备ID
            lock_acquired: 是否已由调用者获取锁（避免死锁）
        """
        if lock_acquired:
            # 调用者已持有锁，直接执行
            self._do_cleanup_device(dev)
        else:
            # 调用者未持有锁，获取锁后执行
            with self._lock:
                self._do_cleanup_device(dev)
    
    def _do_cleanup_device(self, dev):
        """实际清理操作（假设已持有锁）"""
        if dev in self.device_queues:
            del self.device_queues[dev]
        if dev in self.device_workers:
            del self.device_workers[dev]
        if dev in self._last_active:
            del self._last_active[dev]
        # 从队列设备列表中移除
        for queue_id, queue_info in self._queue_devices.items():
            if dev in queue_info.get('devices', []):
                queue_info['devices'].remove(dev)
                break
        _log.debug(f"清理空闲设备 {dev} 资源")

    def _wait_for_slot(self):
        """等待有空闲槽位（已废弃，使用复用机制代替）"""
        pass

    def get_stats(self):
        """获取统计信息"""
        with self._lock:
            return {
                "active_devices": len(self.device_workers),
                "total_queued": sum(q.qsize() for q in self.device_queues.values()),
                "queue_sizes": {dev: q.qsize() for dev, q in self.device_queues.items()},
                "queue_count": len(self._queue_devices),
                "devices_per_queue": {qid: len(info['devices']) for qid, info in self._queue_devices.items()}
            }