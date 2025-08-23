"""
MinerU通用日志模块
根据运行环境自动选择合适的日志系统
优先从adapter中导入，如果失败则使用默认logger
"""

import os
import sys
import logging

def get_logger_for_environment():
    """根据环境获取合适的logger"""
    
    # 1. 检测是否在MaxKB环境中
    if os.path.exists('/opt/maxkb-app/apps'):
        try:
            # 尝试导入MaxKB的logger
            from common.utils.logger import maxkb_logger
            
            # 设置日志级别
            log_level = os.environ.get('MINERU_LOG_LEVEL', 'INFO')
            if hasattr(logging, log_level):
                maxkb_logger.setLevel(getattr(logging, log_level))
            else:
                maxkb_logger.setLevel(logging.INFO)
            
            # 确保有handler（如果没有的话）
            if not maxkb_logger.handlers:
                handler = logging.StreamHandler()
                # 使用MaxKB风格的格式
                formatter = logging.Formatter('%(asctime)s [%(name)s %(levelname)s] %(message)s', 
                                            datefmt='%Y-%m-%d %H:%M:%S')
                handler.setFormatter(formatter)
                handler.setLevel(logging.DEBUG)
                maxkb_logger.addHandler(handler)
            
            # 返回MaxKB logger
            return maxkb_logger, 'maxkb'
        except ImportError:
            pass
    
    # 2. 尝试从gbase_adapter导入
    try:
        from .gbase_adapter.logger import logger as gbase_logger
        return gbase_logger, 'gbase'
    except ImportError:
        pass
    
    # 3. 创建默认logger
    default_logger = logging.getLogger('mineru')
    if not default_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        default_logger.addHandler(handler)
        default_logger.setLevel(logging.INFO)
    
    return default_logger, 'default'

# 获取环境logger
base_logger, env_type = get_logger_for_environment()

def get_module_logger(module_name):
    """为特定模块获取logger
    
    在MaxKB环境下，创建max_kb的子logger
    在其他环境下，创建相应的子logger
    """
    if env_type == 'maxkb':
        # 使用max_kb的子logger，这样日志会继承max_kb的配置
        module_logger = logging.getLogger(f'max_kb.{module_name}')
        # 确保子logger的级别不高于父logger
        log_level = os.environ.get('MINERU_LOG_LEVEL', 'INFO')
        if hasattr(logging, log_level):
            module_logger.setLevel(getattr(logging, log_level))
        return module_logger
    elif env_type == 'gbase':
        # 保持gbase的独立性
        try:
            from .gbase_adapter.logger import logger as gbase_logger
            return gbase_logger
        except ImportError:
            pass
    
    # 默认情况，创建独立的logger
    return logging.getLogger(module_name)

# 为了兼容性，导出默认logger
logger = get_module_logger('mineru')

# 导出logging模块
logging_module = logging

# 导出接口
__all__ = ['logger', 'logging_module', 'get_module_logger', 'env_type']
# 为了兼容性，也导出logging
logging = logging_module