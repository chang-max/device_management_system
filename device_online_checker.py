"""
设备在线状态检查线程
定时检查设备是否离线，更新设备模型中的在线状态列
直接使用device_model中的最新时间列进行判断
"""
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from datetime import datetime
import time


class DeviceOnlineChecker(QThread):
    """设备在线状态检查线程"""
    # 信号：设备状态变化时发射 (device_id, is_online)
    signal_status_changed = pyqtSignal(str, bool)

    def __init__(self, device_model, device_cols_index, outline_time=300, check_interval=10):
        """
        初始化设备在线状态检查线程

        Args:
            device_model: 设备数据模型 (FastDeviceTableModel)
            device_cols_index: 列名到索引的映射
            outline_time: 离线时间阈值（秒），默认300秒（5分钟）
            check_interval: 检查间隔（秒），默认10秒
        """
        super().__init__()
        self.device_model = device_model
        self.device_cols_index = device_cols_index
        self.outline_time = outline_time
        self.check_interval = check_interval
        self._running = True
        self._device_status_cache = {}  # 设备状态缓存: {device_id: is_online}

    def run(self):
        """线程主循环"""
        while self._running:
            try:
                self._check_all_devices_status()
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"设备在线状态检查异常: {e}")
                time.sleep(self.check_interval)

    def _check_all_devices_status(self):
        """检查所有设备的在线状态"""
        try:
            # 检查每个设备的在线状态
            for dev in self.device_model.all_devices:
                device_id = dev.get("设备号")
                if not device_id:
                    continue

                # 使用device_model中的最新时间判断在线状态
                is_online = self._check_device_online_by_time(dev)

                # 获取之前的在线状态
                prev_status = self._device_status_cache.get(device_id, False)

                # 如果状态发生变化，更新模型并发射信号
                if is_online != prev_status:
                    self._device_status_cache[device_id] = is_online
                    self.signal_status_changed.emit(device_id, is_online)

        except Exception as e:
            print(f"检查设备在线状态失败: {e}")

    def _check_device_online_by_time(self, dev):
        """
        根据设备字典中的最新时间判断设备是否在线

        Args:
            dev: 设备字典

        Returns:
            bool: 是否在线
        """
        try:
            # 获取最新时间
            latest_time_str = dev.get("当前时间", "")
            if not latest_time_str or latest_time_str == '-':
                return False

            # 解析时间
            try:
                latest_time = datetime.strptime(latest_time_str, "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    latest_time = datetime.strptime(latest_time_str, "%Y-%m-%d %H:%M")
                except:
                    return False

            # 判断是否在离线时间阈值内
            now = datetime.now()
            return (now - latest_time).total_seconds() < self.outline_time

        except Exception as e:
            print(f"判断设备在线状态失败: {e}")
            return False

    def stop(self):
        """停止线程"""
        self._running = False
        self.wait(1000)  # 等待1秒让线程结束
