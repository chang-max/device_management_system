
from log_save import Logger
_log = Logger(True).logger

import sys
from json import loads

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import paho.mqtt.client as mqtt
from time import sleep

# MQTT子线程类
class MqttThread(QThread):
    # 定义自定义信号，用于向主线程传递接收到的MQTT数据
    # 信号参数：主题、消息内容
    signal_mqtt_connected = pyqtSignal(bool,bool)
    signal_mqtt_message_received = pyqtSignal(str, object)

    def __init__(self, mqtt_config, username=None, password=None):
        super().__init__()
        # MQTT连接参数
        self.broker = mqtt_config[0] # 地址
        self.port = mqtt_config[1] # 端口
        self.client_id = mqtt_config[2] # 链接名
        self.qos = mqtt_config[3] #QOS
        self.username = username
        self.password = password
        self.devs = [] #设备列表

        self.sub_topic = "MS/#/dev2plt"

        # 重连控制参数
        self._is_running = True  # 线程运行开关
        self._reconnecting = False  # 重连中标记（避免重复重连）
        self._reconnect_interval = 5  # 重连间隔（秒）
        self._max_retry = -1  # 最大重连次数（-1=无限重试）
        self._retry_count = 0  # 当前重连次数
        self._mutex = QMutex()  # 线程安全锁
        self._first_connect = True  # 是否首次连接

        # MQTT客户端实例
        self.client = mqtt.Client( callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  client_id= self.client_id )

        # 设置认证（如果需要）
        if username and password:
            self.client.username_pw_set(username, password)

        # 设置核心回调（新增on_disconnect）
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect  # 监听断开事件

    # MQTT连接成功回调
    def on_connect(self, client, userdata, flags, rc, properties=None):
        # 检查对象是否已被销毁
        try:
            _ = self._is_running
        except RuntimeError:
            return

        if rc == 0:
            # 连接成功后重置重连计数
            locker = QMutexLocker(self._mutex)
            self._retry_count = 0
            self._reconnecting = False
            try:
                self.signal_mqtt_connected.emit(True, self._first_connect)
            except RuntimeError:
                pass
            self._first_connect = False
            # 重新订阅所有主题（重连后需要重新订阅）
            client.subscribe("#")
        else:
            try:
                self.signal_mqtt_connected.emit(False, False)
            except RuntimeError:
                pass

    # VERSION2 断开连接回调（核心：触发重连）
    def on_disconnect(self, client, userdata, rc, disconnect_flags, properties=None):
        # 检查对象是否已被销毁
        try:
            _ = self._is_running
        except RuntimeError:
            return

        # rc=0表示正常断开（主动调用disconnect），无需重连
        try:
            self.signal_mqtt_connected.emit(False, False)
        except RuntimeError:
            pass
        # 异常断开，触发自动重连
        _log.error(f"警告 - 连接断开（状态码：{rc}），将在{self._reconnect_interval}秒后尝试重连")
        self._auto_reconnect()

    # 自动重连核心逻辑
    def _auto_reconnect(self):
        locker = QMutexLocker(self._mutex)
        # 检查是否需要重连（线程运行中、未在重连中、未达最大重试次数）
        if not self._is_running or self._reconnecting or (
                self._max_retry != -1 and self._retry_count >= self._max_retry):
            return

        self._reconnecting = True
        self._retry_count += 1

        # 释放锁后执行重连（避免阻塞）
        locker.unlock()

        while self._is_running:
            try:
                # 检查是否达到最大重试次数
                if self._max_retry != -1 and self._retry_count > self._max_retry:
                    _log.error(f"错误 - 重连{self._max_retry}次失败，停止重连")
                    self._reconnecting = False
                    break

                # 尝试重新连接
                _log.info(f"系统 - 第{self._retry_count}次重连...")
                # reconnect() 是异步方法，不会立即返回连接结果
                # 连接成功后会触发 on_connect 回调
                self.client.reconnect()
                
                # 等待连接结果（通过 on_connect 回调设置标志）
                # 最多等待 reconnect_interval 秒
                wait_time = 0
                while wait_time < self._reconnect_interval:
                    sleep(0.1)
                    wait_time += 0.1
                    # 检查是否已连接（由 on_connect 回调设置）
                    if not self._reconnecting:
                        _log.info("系统 - 重连成功！")
                        return
                        
            except Exception as e:
                _log.error(f"错误 - 重连失败：{str(e)}")
                # 重连间隔
                sleep(self._reconnect_interval)
                self._retry_count += 1


    # MQTT接收消息回调
    def on_message(self, client, userdata, msg):
        # 检查对象是否已被销毁
        try:
            _ = self._is_running
        except RuntimeError:
            # 对象已被销毁，直接返回
            return

        try:
            data = loads(msg.payload)  # data = 字典  #payload = json数据
        except Exception as e:
            _log.warning(f"接收数据(非JSON格式)：  {msg.topic}  {msg.payload}, 错误: {e}")
        else:
            try:
                # _log.debug(f"接收数据(JSON格式)：  {msg.topic}  {data}")
                self.signal_mqtt_message_received.emit(msg.topic, data)
            except RuntimeError:
                # 对象已被销毁，忽略
                pass
            except Exception as e:
                _log.error(f"发射MQTT接收信号失败: {e}, topic={msg.topic}, data类型={type(data)}")
                import traceback
                traceback.print_exc()

    def subscribe(self, dev):
        """
        对一个订阅主题进行订阅
        :param dev: 设备ID
        :return:
        """
        if dev not in self.devs:
            topic = self.sub_topic.replace("#",dev)
            result = self.client.subscribe(topic,self.qos)
            if result[0] == 0:
                self.devs.append(dev)
                return True
            else:
                return False
        else:
            return False

    # def updata_sub(self,topic):
    #     """更新订阅主题"""
    #     if dev not in self.devs:
    #         topic = self.sub_topic.format("#",dev)
    #         result = self.client.subscribe(topic, self.qos)
    #         if result:
    #             _log.debug("{}订阅成功！！".format(topic))
    #             self.devs.append(dev)
    #         else:
    #             _log.error("{}订阅失败！！".format(topic))
    #         return result
    #     else:
    #         return True

    def unsubscribe(self, dev):
        """
         对一个订阅主题进行取消订阅
        :param mqtt_sub: 订阅主题
        :return:
        """
        if dev in self.devs:
            topic = self.sub_topic.replace("#",dev)
            result = self.client.unsubscribe(topic)
            self.devs.remove(dev)
            if result[0] == 0:
                return True
            else:
                return False
        else:
            return True

    def publish(self, mqtt_topic, mqtt_msg):
        """
        对一个订阅主题进行取消订阅
        :param mqtt_topic: 订阅主题
        :param mqtt_msg: 发布消息
        :return:
        """
        # _log.debug(f"发布消息：{mqtt_topic}  {mqtt_msg}")
        # 发布消息
        result = self.client.publish(mqtt_topic, mqtt_msg, self.qos)
        if result[0] == 0:
            return True
        else:
            return False


    # 线程运行入口
    def run(self):
        try:
            # 初始连接
            # print(self.broker)
            self.client.connect(self.broker, self.port)
            _log.debug(f"{self.broker}  {self.port} {self.client_id}连接成功")

            # 持续运行MQTT循环（阻塞式）
            self.client.loop_start()

            # while self._is_running:
            #     self.client.loop(timeout=1.0)  # 非阻塞loop，便于检测退出开关
        except Exception as e:
            self.mqtt_connected.emit(False,False)
            _log.error(f"初始连接失败：{str(e)}")
            # 触发自动重连
            self._auto_reconnect()

    # 停止线程和重连
    def stop(self):
        locker = QMutexLocker(self._mutex)
        self._is_running = False
        self._reconnecting = False

        # 断开MQTT连接
        self.client.disconnect()
        self.client.loop_stop()

        # 停止线程
        self.quit()
        self.wait(timeout=5000)