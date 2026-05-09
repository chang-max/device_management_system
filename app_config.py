"""
应用程序配置管理类
统一管理地址、指向、离线时间判断等全局配置
"""


class AppConfig:
    """应用程序配置管理类 - 单例模式"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AppConfig._initialized:
            return
        AppConfig._initialized = True

        # ==================== MQTT配置 ====================
        self.mqtt_host = "opr.iotdirvers.com"  # MQTT服务器地址
        self.mqtt_port = 1883  # MQTT服务器端口
        self.mqtt_username = "MST_IC"  # MQTT用户名
        self.mqtt_password = ""  # MQTT密码（空表示无密码）
        self.mqtt_keepalive = 60  # MQTT保持连接时间（秒）

        # MQTT主题配置
        self.mqtt_sub_topic_template = "MS/#/dev2plt"  # 订阅主题模板
        self.mqtt_pub_topic_template = "MS/{device_id}/plt2dev"  # 发布主题模板


        # ==================== 设备在线状态配置 ====================
        self.outline_time = 300  # 设备离线时间阈值（秒），默认5分钟
        self.online_check_interval = 10  # 在线状态检查间隔（秒）

        # ==================== 数据库配置 ====================
        self.db_host = "localhost"  # 数据库地址
        self.db_port = 3311  # 数据库端口
        self.db_name = "MST_SQL"  # 数据库名
        self.db_username = "root"  # 数据库用户名
        self.db_password = "MST@2026!"  # 数据库密码
        self.db_charset = "utf8mb4"  # 数据库字符集

        # ==================== Redis配置 ====================
        self.redis_host = "localhost"  # Redis地址
        self.redis_port = 6379  # Redis端口
        self.redis_password = "MST@2026!"  # Redis密码（空表示无密码）
        self.redis_db = 0  # Redis数据库索引

        # ==================== 图片配置 ====================
        self.position_x = 0  # 图片位置X坐标（默认0）
        self.position_y = 0  # 图片位置Y坐标（默认0）

        # ==================== 功率数据配置 ====================
        self.power_aggregation_interval = 60  # 功率数据聚合间隔（秒）
        self.power_chart_points = 24  # 功率图表显示点数（24小时或24分钟验证模式）
        self.power_verification_mode = True  # 功率验证模式（True=24分钟，False=24小时）

        # ==================== 界面配置 ====================
        self.ui_refresh_interval = 1000  # UI刷新间隔（毫秒）
        self.chart_update_interval = 60000  # 图表更新间隔（毫秒）
        self.message_show_time = 3000  # 消息提示显示时间（毫秒）

        # ==================== 日志配置 ====================
        self.log_level = "DEBUG"  # 日志级别
        self.log_to_file = True  # 是否写入日志文件
        self.log_max_size = 10 * 1024 * 1024  # 日志文件最大大小（10MB）
        self.log_backup_count = 5  # 日志文件备份数量

    # ==================== 配置获取方法 ====================
    def get_mqtt_config(self):
        """获取MQTT配置"""
        return {
            'host': self.mqtt_host,
            'port': self.mqtt_port,
            'username': self.mqtt_username,
            'password': self.mqtt_password,
            'keepalive': self.mqtt_keepalive
        }

    def get_db_config(self):
        """获取数据库配置"""
        return {
            'host': self.db_host,
            'port': self.db_port,
            'database': self.db_name,
            'user': self.db_username,
            'password': self.db_password,
            'charset': self.db_charset
        }

    def get_redis_config(self):
        """获取Redis配置"""
        return {
            'host': self.redis_host,
            'port': self.redis_port,
            'password': self.redis_password if self.redis_password else None,
            'db': self.redis_db
        }

    def get_image_config(self):
        """获取图片配置"""
        return {
            'x': self.position_x,
            'y': self.position_y
        }

    # ==================== 配置更新方法 ====================
    def update_outline_time(self, seconds):
        """更新离线时间阈值"""
        self.outline_time = seconds

    def update_mqtt_config(self, host=None, port=None, username=None, password=None):
        """更新MQTT配置"""
        if host is not None:
            self.mqtt_host = host
        if port is not None:
            self.mqtt_port = port
        if username is not None:
            self.mqtt_username = username
        if password is not None:
            self.mqtt_password = password

    def update_db_config(self, host=None, port=None, database=None, user=None, password=None):
        """更新数据库配置"""
        if host is not None:
            self.db_host = host
        if port is not None:
            self.db_port = port
        if database is not None:
            self.db_name = database
        if user is not None:
            self.db_username = user
        if password is not None:
            self.db_password = password


# 全局配置实例
app_config = AppConfig()
