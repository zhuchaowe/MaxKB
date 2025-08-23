"""
MaxKB Adapter的日志模块
提供与MaxKB日志系统兼容的接口
"""

import logging

try:
    # 尝试导入MaxKB的logger
    from common.utils.logger import maxkb_logger
    # 使用MaxKB的logger作为基础
    base_logger = maxkb_logger
except ImportError:
    # 如果无法导入，创建默认logger
    base_logger = logging.getLogger('max_kb')

# 导出logger作为主要的日志接口
logger = base_logger

# 为了兼容性，也导出为loguru_logger
loguru_logger = base_logger

# 提供标准logging模块
logging_module = logging

def get_module_logger(module_name):
    """为特定模块获取logger，使用max_kb的子logger"""
    # 创建max_kb的子logger，这样会继承max_kb的所有配置
    return logging.getLogger(f'max_kb.{module_name}')

# 导出所有需要的接口
__all__ = ['logger', 'loguru_logger', 'logging_module', 'get_module_logger']
# 为了兼容性
logging = logging_module