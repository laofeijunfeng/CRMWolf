"""
日志配置模块

提供结构化日志输出、文件轮转、级别分离
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import TextIO

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


# 日志格式
STANDARD_FORMAT = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 包含异常堆栈的日志格式
ERROR_FORMAT = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s\n%(exc_text)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


class ExtraFormatter(logging.Formatter):
    """支持 extra 字段的格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        # 基础格式
        base = super().format(record)

        # 添加 extra 字段
        if hasattr(record, 'extra_fields') and record.extra_fields:
            fields = " | " + " ".join(f"{k}={v}" for k, v in record.extra_fields.items())
            base += fields

        return base


class ExcTextFilter(logging.Filter):
    """为 ERROR 级别添加堆栈文本"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and record.exc_info:
            record.exc_text = self.format_exception(record.exc_info)
        elif not hasattr(record, 'exc_text'):
            record.exc_text = ""
        return True

    def format_exception(
        self,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None],
    ) -> str:
        import traceback
        return "".join(traceback.format_exception(*exc_info))


def get_file_handler(
    filename: str,
    level: int,
    backup_days: int = 30,
    formatter: logging.Formatter | None = None
) -> TimedRotatingFileHandler:
    """创建按天轮转的文件日志处理器。"""
    handler = TimedRotatingFileHandler(
        filename=str(LOG_DIR / filename),
        when="midnight",
        backupCount=backup_days,
        encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(formatter or STANDARD_FORMAT)
    handler.addFilter(ExcTextFilter())
    return handler


def get_console_handler(level: int, formatter: logging.Formatter | None = None) -> logging.StreamHandler[TextIO]:
    """创建控制台日志处理器"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter or STANDARD_FORMAT)
    handler.addFilter(ExcTextFilter())
    return handler


def setup_logging(debug: bool = False) -> None:
    """
    初始化日志配置

    Args:
        debug: 是否开启开发环境的 DEBUG 日志
    """
    # 根日志级别
    root_level = logging.DEBUG if debug else logging.INFO

    # 清除默认处理器
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(root_level)

    # 开发环境的控制台处理器
    if debug:
        root_logger.addHandler(get_console_handler(logging.DEBUG))

    # 应用日志文件记录 INFO 及以上级别
    root_logger.addHandler(get_file_handler("app.log", logging.INFO, backup_days=30))

    # 错误日志文件记录 ERROR 及以上级别
    root_logger.addHandler(get_file_handler("error.log", logging.ERROR, backup_days=90))

    # 调试日志文件仅用于开发环境
    if debug:
        root_logger.addHandler(get_file_handler("debug.log", logging.DEBUG, backup_days=7))

    # 降低第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # 启动日志
    root_logger.info(
        "日志系统初始化完成",
        extra={"extra_fields": {"log_dir": str(LOG_DIR), "level": "DEBUG" if debug else "INFO"}}
    )


def get_logger(name: str | None = None) -> logging.Logger:
    """
    获取 Logger 实例

    Args:
        name: 模块名通常使用 __name__

    Returns:
        配置好的 Logger 实例
    """
    return logging.getLogger(name)


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    """记录带额外字段的日志"""
    logger.log(level, message, extra={"extra_fields": fields})