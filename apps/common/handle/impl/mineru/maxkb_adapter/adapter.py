"""
MaxKB平台适配器 - 实现MaxKB特定的功能

这个适配器实现了MaxKB平台的特定功能，包括：
- MaxKB的trace上下文管理（如果有）
- MaxKB的锁机制（如果有）
- MaxKB的文件存储客户端
- MaxKB的模型客户端
"""

import contextlib
import os
from typing import Any, Dict, Optional
from .logger import get_module_logger
logger = get_module_logger('adapter')

# 导入MaxKB特有的模块
from .file_storage_client import FileStorageClient
from .maxkb_model_client import maxkb_model_client

# 导入基类从上级目录
from ..base_parser import PlatformAdapter, BaseMinerUExtractor


class MaxKBAdapter(PlatformAdapter):
    """MaxKB平台的适配器实现"""
    
    def __init__(self):
        """初始化MaxKB适配器"""
        self.file_storage = FileStorageClient()
        self.model_client = maxkb_model_client
        
        # 导入配置以获取存储路径
        from .config_maxkb import MaxKBMinerUConfig
        self.config = MaxKBMinerUConfig()
        self.storage_path = self.config.file_storage_path
    
    @contextlib.asynccontextmanager
    async def trace_context(self, trace_id: str):
        """MaxKB的trace上下文 - 如果没有特殊实现，使用简单的上下文"""
        # MaxKB可能没有trace_context，这里提供一个简单的实现
        logger.info(f"MaxKB: Starting trace {trace_id}")
        try:
            yield
        finally:
            logger.info(f"MaxKB: Ending trace {trace_id}")
    
    async def lock_enter(self, temp_dir: str):
        """MaxKB的锁机制进入 - 如果没有特殊实现，创建目录即可"""
        # MaxKB可能没有特殊的锁机制，确保目录存在即可
        os.makedirs(temp_dir, exist_ok=True)
        logger.debug(f"MaxKB: Entered lock for {temp_dir}")
    
    async def lock_release(self, temp_dir: str):
        """MaxKB的锁机制释放 - 如果没有特殊实现，简单记录即可"""
        logger.debug(f"MaxKB: Released lock for {temp_dir}")
    
    async def upload_file(self, file_path: str, options: Any = None) -> str:
        """使用MaxKB的文件存储上传文件 - 直接复制文件到存储目录"""
        import shutil
        import uuid
        
        logger.info(f"MaxKB: upload_file called with path={file_path}, options={options}")
        
        # 如果在测试模式下，直接返回原图地址
        #if os.getenv('MINERU_TEST_FILE'):
        #    logger.info(f"MaxKB: Test mode - returning original path: {file_path}")
        #    return file_path
        
        try:
            # 确保文件存在
            if not os.path.exists(file_path):
                logger.warning(f"MaxKB: File not found: {file_path}")
                return file_path
            
            # 获取knowledge_id（如果在options中提供）
            knowledge_id = None
            if options and isinstance(options, (tuple, list)) and len(options) > 0:
                knowledge_id = options[0]
            
            # 创建存储目录结构
            # 使用 knowledge_id 或 'mineru' 作为子目录
            sub_dir = knowledge_id if knowledge_id else 'mineru'
            storage_dir = os.path.join(self.storage_path, sub_dir, 'images')
            
            # 确保存储目录存在
            os.makedirs(storage_dir, exist_ok=True)
            
            # 生成唯一的文件名，保留原始扩展名
            file_ext = os.path.splitext(file_path)[1]
            file_name = f"{uuid.uuid4().hex}{file_ext}"
            dest_path = os.path.join(storage_dir, file_name)
            
            # 复制文件到存储目录
            shutil.copy2(file_path, dest_path)
            
            # 返回相对路径或URL格式
            # 生成相对于storage根目录的路径
            relative_path = os.path.relpath(dest_path, self.storage_path)
            # 确保路径使用正斜杠（兼容所有系统）
            relative_path = relative_path.replace(os.path.sep, '/')
            
            # 根据环境配置生成完整的URL
            # 检查是否配置了基础URL
            base_url = os.getenv('MAXKB_BASE_URL', '')
            if base_url:
                # 如果有基础URL，生成完整的URL
                result_url = f"{base_url.rstrip('/')}/storage/{relative_path}"
            else:
                # 生成相对URL，直接使用/storage/路径
                result_url = f"/storage/{relative_path}"
            
            logger.info(f"MaxKB: Copied file {file_path} -> {dest_path}")
            logger.info(f"MaxKB: Returning URL: {result_url}")
            
            return result_url
            
        except Exception as e:
            logger.error(f"MaxKB: Failed to copy file {file_path}: {str(e)}")
            # 如果复制失败，返回本地路径
            return file_path
    
    def get_logger(self):
        """获取MaxKB的日志器"""
        return logger
    
    def get_settings(self) -> Dict[str, Any]:
        """获取MaxKB的配置"""
        # 返回MaxKB的配置，可以从环境变量或配置文件读取
        return {
            'api_key': os.getenv('MAXKB_API_KEY'),
            'api_url': os.getenv('MAXKB_API_URL', 'https://api.maxkb.com'),
            'model': os.getenv('MAXKB_DEFAULT_MODEL', 'gpt-4o'),
            # 添加其他MaxKB特有的配置
        }
    
    def get_learn_type(self, params: Dict[str, Any]) -> int:
        """获取learn_type参数 - MaxKB使用model_id映射到learn_type"""
        # MaxKB使用llm_model_id和vision_model_id
        # 这里可以根据model_id映射到learn_type
        llm_model_id = params.get('llm_model_id')
        vision_model_id = params.get('vision_model_id')
        
        # 根据模型ID映射到learn_type（这里是示例映射）
        if llm_model_id:
            # 可以根据具体的模型ID返回不同的learn_type
            return 9  # 默认返回9
        return 9
    
    def set_trace_id(self, trace_id: str):
        """设置trace ID用于日志跟踪"""
        # MaxKB可能有自己的trace机制
        # 这里简单记录日志
        logger.debug(f"MaxKB: Setting trace ID to: {trace_id}")


class MinerUExtractor(BaseMinerUExtractor):
    """
    MaxKB平台的MinerU解析器
    
    继承自基类，使用MaxKB适配器
    """
    
    def __init__(self, llm_model_id: Optional[str] = None, 
                 vision_model_id: Optional[str] = None):
        """
        初始化MaxKB的MinerU解析器
        
        Args:
            llm_model_id: 大语言模型ID（MaxKB特有参数）
            vision_model_id: 视觉模型ID（MaxKB特有参数）
        """
        # 创建MaxKB适配器
        adapter = MaxKBAdapter()
        
        # 导入并创建MaxKB特定的配置，传递模型ID
        from .config_maxkb import MaxKBMinerUConfig
        config = MaxKBMinerUConfig(llm_model_id=llm_model_id, vision_model_id=vision_model_id)
        
        # 调用基类初始化，传递适配器、配置和MaxKB特有参数
        super().__init__(
            adapter,
            config=config,
            llm_model_id=llm_model_id,
            vision_model_id=vision_model_id
        )
        
        # 保存MaxKB特有的参数
        self.llm_model_id = llm_model_id
        self.vision_model_id = vision_model_id
        
        # 如果需要，可以在这里初始化MaxKB特有的组件
        self.model_client = adapter.model_client
        self.file_storage = adapter.file_storage
    
    async def process_file_with_models(self, filepath: str, src_name: str = None,
                                      upload_options: Any = None) -> Any:
        """
        MaxKB特有的处理方法 - 使用指定的模型处理文件
        
        这个方法展示了如何在子类中添加平台特有的功能
        """
        logger.info(f"MaxKB: Processing with LLM: {self.llm_model_id}, Vision: {self.vision_model_id}")
        
        # 调用基类的处理方法
        result = await self.process_file(filepath, src_name, upload_options)
        
        # 可以在这里添加MaxKB特有的后处理
        if self.llm_model_id:
            logger.info(f"MaxKB: Used LLM model {self.llm_model_id} for processing")
        if self.vision_model_id:
            logger.info(f"MaxKB: Used Vision model {self.vision_model_id} for image processing")
        
        return result


class MinerUAdapter:
    """
    MinerU文档处理适配器 - 用于MaxKB中处理文档
    """
    
    def __init__(self):
        """初始化MinerU适配器"""
        self.extractor = None
        self._init_extractor()
    
    def _init_extractor(self):
        """初始化MinerU解析器"""
        try:
            # 获取配置的模型ID
            llm_model_id = os.environ.get('MINERU_LLM_MODEL_ID')
            vision_model_id = os.environ.get('MINERU_VISION_MODEL_ID')
            
            # 创建解析器
            self.extractor = MinerUExtractor(
                llm_model_id=llm_model_id,
                vision_model_id=vision_model_id
            )
            logger.info("MinerU适配器初始化成功")
        except Exception as e:
            logger.error(f"MinerU适配器初始化失败: {str(e)}")
            raise
    
    def process_document(self, file_content: bytes, file_name: str, 
                        save_image_func=None, **kwargs) -> Dict[str, Any]:
        """
        处理文档并返回结构化内容
        
        Args:
            file_content: 文件内容字节流
            file_name: 文件名
            save_image_func: 保存图片的函数
            **kwargs: 额外参数，包括llm_model_id和vision_model_id
            
        Returns:
            包含sections的字典，每个section包含content、title和images
        """
        import tempfile
        import asyncio
        import threading
        
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], 
                                            delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file_path = tmp_file.name
            
            try:
                # 在新线程中运行异步代码，避免事件循环冲突
                result = None
                exception = None
                
                def run_async():
                    nonlocal result, exception
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            # 提取模型ID参数
                            llm_model_id = kwargs.get('llm_model_id')
                            vision_model_id = kwargs.get('vision_model_id')
                            if llm_model_id and vision_model_id:
                                logger.info(f"使用指定模型处理文档: LLM={llm_model_id}, Vision={vision_model_id}")
                                # TODO: 将模型ID传递给extractor
                                # 目前暂时使用默认配置，后续可以在这里设置模型
                            
                            result = loop.run_until_complete(
                                self.extractor.process_file(tmp_file_path, file_name)
                            )
                        finally:
                            loop.close()
                    except Exception as e:
                        exception = e
                
                thread = threading.Thread(target=run_async)
                thread.start()
                thread.join(timeout=300)  # 5分钟超时
                
                if exception:
                    raise exception
                
                if result is None:
                    logger.warning("MinerU处理超时或无结果")
                    return {'sections': []}
                
                logger.info(f"MinerU返回结果类型: {type(result)}")
                
                # 转换结果格式
                sections = []
                
                # 检查result的类型
                if isinstance(result, list):
                    # result是一个页面文档列表（Langchain Document对象）
                    for page_doc in result:
                        # 处理Langchain Document对象
                        if hasattr(page_doc, 'page_content') and hasattr(page_doc, 'metadata'):
                            page_content = page_doc.page_content
                            metadata = page_doc.metadata
                            
                            if page_content:
                                # 提取页码
                                page_num = metadata.get('page', metadata.get('page_num', ''))
                                
                                # 提取图片列表
                                images = metadata.get('images', [])
                                
                                sections.append({
                                    'content': page_content,
                                    'title': f"Page {page_num}" if page_num else '',
                                    'images': images
                                })
                        elif isinstance(page_doc, dict):
                            # 字典格式的文档
                            page_content = page_doc.get('text', page_doc.get('page_content', ''))
                            if page_content:
                                sections.append({
                                    'content': page_content,
                                    'title': f"Page {page_doc.get('page_num', '')}",
                                    'images': page_doc.get('images', [])
                                })
                elif isinstance(result, dict):
                    # result是一个字典
                    if 'content' in result:
                        content = result['content']
                        if isinstance(content, str):
                            sections.append({
                                'content': content,
                                'title': '',
                                'images': []
                            })
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    sections.append({
                                        'content': item.get('text', ''),
                                        'title': item.get('title', ''),
                                        'images': item.get('images', [])
                                    })
                                else:
                                    sections.append({
                                        'content': str(item),
                                        'title': '',
                                        'images': []
                                    })
                
                # 处理图片（如果有保存函数）
                if save_image_func and sections:
                    for section in sections:
                        if section.get('images'):
                            saved_images = []
                            for img_path in section['images']:
                                try:
                                    # 检查图片文件是否存在
                                    if os.path.exists(img_path):
                                        with open(img_path, 'rb') as f:
                                            img_content = f.read()
                                        saved_path = save_image_func(img_content)
                                        saved_images.append(saved_path)
                                    else:
                                        saved_images.append(img_path)
                                except Exception as e:
                                    logger.warning(f"保存图片失败 {img_path}: {str(e)}")
                                    saved_images.append(img_path)
                            section['images'] = saved_images
                
                logger.info(f"MinerU处理完成，提取了{len(sections)}个sections")
                return {'sections': sections}
                
            finally:
                # 清理临时文件
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    
        except Exception as e:
            logger.error(f"MinerU处理文档失败: {str(e)}")
            # 返回空结果而不是抛出异常，让调用方可以回退到其他处理器
            return {'sections': []}
