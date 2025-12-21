"""
日志配置模块

配置日志输出到文件和控制台，支持日志轮转。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_dir: str = "logs",
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    level: int = logging.INFO,
    console_output: bool = True,
) -> None:
    """
    配置日志系统
    
    Args:
        log_dir: 日志文件目录（相对于项目根目录）
        log_file: 日志文件名
        max_bytes: 单个日志文件最大大小（字节），超过后轮转
        backup_count: 保留的备份文件数量
        level: 日志级别
        console_output: 是否同时输出到控制台
    """
    # 获取项目根目录
    project_root = Path(__file__).parent.parent.parent
    log_path = project_root / log_dir
    
    # 创建日志目录（如果不存在）
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 日志文件完整路径
    log_file_path = log_path / log_file
    
    # 配置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 创建根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有的handlers（避免重复添加）
    root_logger.handlers.clear()
    
    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(file_handler)
    
    # 控制台处理器（可选）
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(console_handler)
    
    # 记录日志配置信息
    logger = logging.getLogger(__name__)
    logger.info(f"📝 [日志配置] 日志文件: {log_file_path}")
    logger.info(f"📝 [日志配置] 日志级别: {logging.getLevelName(level)}")
    logger.info(f"📝 [日志配置] 文件大小限制: {max_bytes / 1024 / 1024:.1f}MB")
    logger.info(f"📝 [日志配置] 备份文件数量: {backup_count}")
    logger.info(f"📝 [日志配置] 控制台输出: {'启用' if console_output else '禁用'}")


def setup_logging_from_settings(settings) -> None:
    """
    从settings配置日志
    
    Args:
        settings: AppSettings实例
    """
    # 转换日志级别字符串为常量
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    level = level_map.get(settings.log_level.upper(), logging.INFO)
    
    setup_logging(
        log_dir=settings.log_dir,
        log_file=settings.log_file,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
        level=level,
        console_output=settings.log_console_output,
    )

