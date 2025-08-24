"""
GPTBase平台适配器 - 实现GPTBase特定的功能

这个适配器实现了GPTBase平台的特定功能，包括：
- trace上下文管理
- gzero锁机制
- gzero文件上传
- GPTBase配置管理
"""

import contextlib
from typing import Any, Dict
from .logger import logger
import os
from .gptbase_utils import GPTBaseUtils, GZeroUtils
from .config_gptbase import GPTBaseMinerUConfig
from ..base_parser import PlatformAdapter, BaseMinerUExtractor, ProcessingResult

try:
    from loader.trace import trace_context as original_trace_context
except ImportError:
    # Fallback if loader.trace is not available
    import contextlib
    @contextlib.asynccontextmanager
    async def original_trace_context(trace_id: str):
        yield


class GPTBaseAdapter(PlatformAdapter):
    """GPTBase平台的适配器实现"""
    
    @contextlib.asynccontextmanager
    async def trace_context(self, trace_id: str):
        """使用GPTBase的trace上下文"""
        async with original_trace_context(trace_id):
            yield
    
    async def lock_enter(self, temp_dir: str):
        """使用gzero的锁机制进入"""
        await GZeroUtils.gzero_lock_enter(temp_dir)
    
    async def lock_release(self, temp_dir: str):
        """使用gzero的锁机制释放"""
        await GZeroUtils.gzero_lock_release(temp_dir)
    
    async def upload_file(self, file_path: str, options: Any = None) -> str:
        """上传文件 - PDF使用S3特殊处理，图片使用gzero上传"""
        # 如果在测试模式下，直接返回原图地址
        if os.getenv('MINERU_TEST_FILE'):
            logger.info(f"Gbase: Test mode - returning original path: {file_path}")
            return file_path 
        
        import os
        
        # 判断文件类型
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in ['.pdf']:
            # PDF文件使用S3上传，包含域名替换等特殊处理
            return await GPTBaseUtils.upload_file_to_s3(file_path, options)
        else:
            # 图片等其他文件使用gzero上传
            return await GZeroUtils.gzero_upload(file_path, options)
    
    def get_logger(self):
        """获取GPTBase的日志器"""
        return logger
    
    def get_settings(self) -> Dict[str, Any]:
        """获取GPTBase的配置"""
        return GPTBaseUtils.get_settings()
    
    def get_learn_type(self, params: Dict[str, Any]) -> int:
        """获取learn_type参数 - GPTBase使用learn_type"""
        return params.get('learn_type', 9)
    
    def set_trace_id(self, trace_id: str):
        """设置trace ID用于日志跟踪"""
        try:
            from loader.trace import set_trace_id
            set_trace_id(trace_id)
        except ImportError:
            # 如果loader.trace不可用，至少记录一下
            logger.debug(f"Trace ID would be set to: {trace_id}")


class MinerUExtractor(BaseMinerUExtractor):
    """
    GPTBase平台的MinerU解析器
    
    继承自基类，使用GPTBase适配器
    """
    
    def __init__(self, learn_type: int = 9):
        """
        初始化GPTBase的MinerU解析器
        
        Args:
            learn_type: 学习类型（GPTBase特有参数）
        """
        # 创建GPTBase适配器
        adapter = GPTBaseAdapter()
        
        # 创建GPTBase特定的配置
        config = GPTBaseMinerUConfig()
        
        # 调用基类初始化，传递适配器、配置和learn_type
        super().__init__(adapter, config=config, learn_type=learn_type)
        
        # 保存learn_type供后续使用（基类已经保存了，这里是为了兼容性）
        self.learn_type = learn_type
