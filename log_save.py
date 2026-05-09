# 日志保存.py
import logging
import os
import colorlog
from logging.handlers import RotatingFileHandler
from typing import Optional

# 全局日志配置开关（核心控制变量）
_LOG_SAVE_ENABLED = True  # True=保存日志到文件，False=仅控制台输出（不保存）
_LOG_FILE_PATH = "app.log"  # 日志文件路径
_LOG_MAX_SIZE = 250 * 1024 * 1024  # 单个日志文件最大10MB
_LOG_BACKUP_COUNT = 30  # 最多保留5个备份日志文件
_LOG_LEVEL = logging.DEBUG  # 日志级别，设为DEBUG以显示所有级别的日志

# 全局日志器实例（避免重复创建handler）
_logger: Optional[logging.Logger] = None


def set_log_save(enabled: bool):
    """
    动态设置是否保存日志到文件（全局生效）
    :param enabled: True=保存，False=不保存
    """
    global _LOG_SAVE_ENABLED
    _LOG_SAVE_ENABLED = enabled

    # 重新配置日志器，让开关立即生效
    get_logger()


def get_log_save_status() -> bool:
    """获取当前日志保存开关状态"""
    return _LOG_SAVE_ENABLED


def set_log_level(level: int):
    """
    动态设置日志级别（全局生效）
    :param level: 日志级别，如logging.DEBUG, logging.INFO等
    """
    global _LOG_LEVEL
    _LOG_LEVEL = level

    # 重新配置日志器，让设置立即生效
    get_logger()


def get_log_level() -> int:
    """获取当前日志级别"""
    return _LOG_LEVEL


def get_logger(name: str = "app") -> logging.Logger:
    """
    获取全局日志器实例（所有.py文件都通过这个方法获取logger）
    :param name: 日志器名称（默认统一为app，保证全局唯一）
    :return: 配置好的logger实例
    """
    global _logger

    # 如果已创建logger，先清理旧的handler（避免重复输出）
    if _logger is not None:
        # 移除所有旧handler
        for handler in _logger.handlers[:]:
            handler.close()
            _logger.removeHandler(handler)
    else:
        _logger = logging.getLogger(name)

    # 基础配置：设置日志级别，避免重复传播
    _logger.setLevel(_LOG_LEVEL)
    _logger.propagate = False

    # 1. 添加控制台handler（始终开启，方便调试）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_LOG_LEVEL)

    # 定义日志颜色
    log_colors_config = {
        'DEBUG': 'white',  # cyan white
        'INFO': 'light_green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }

    # 控制台日志格式
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors=log_colors_config
    )
    console_handler.setFormatter(console_formatter)
    _logger.addHandler(console_handler)

    # 2. 如果开启保存，添加文件handler
    if _LOG_SAVE_ENABLED:
        # 创建日志目录（如果不存在）
        log_dir = os.path.dirname(_LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 滚动文件handler（避免日志文件过大）
        file_handler = RotatingFileHandler(
            filename=_LOG_FILE_PATH,
            maxBytes=_LOG_MAX_SIZE,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(_LOG_LEVEL)
        # 文件日志格式（可增加更多信息，比如行号）
        file_formatter = logging.Formatter(
            "%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        _logger.addHandler(file_handler)

    return _logger


class Logger:
    """
    兼容旧代码的Logger类
    用法: Logger(True).logger
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        # 设置日志保存状态
        set_log_save(enabled)
        # 获取logger实例
        self.logger = get_logger()


# 对外暴露便捷的日志方法（可选，简化调用）
def info(msg: str):
    get_logger().info(msg)


def debug(msg: str):
    get_logger().debug(msg)


def warning(msg: str):
    get_logger().warning(msg)


def error(msg: str):
    get_logger().error(msg)


def critical(msg: str):
    get_logger().critical(msg)