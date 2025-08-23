"""
GBase Adapter的日志模块
提供与GBase系统兼容的日志接口
"""

from loguru import logger as loguru_logger
import logging

# 主要使用loguru作为logger
logger = loguru_logger

# 导出所有需要的接口
__all__ = ['logger', 'loguru_logger', 'logging']