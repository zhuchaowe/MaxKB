"""
MinerU文档解析处理器

该处理器使用MinerU解析PDF和PPT文档，提供高质量的文档解析功能。
支持多种文档格式，包括复杂的表格、图片、公式等内容的解析。
"""

import io
import os
import traceback
import asyncio
from typing import List, Dict
from pathlib import Path

from langchain.docstore.document import Document

from common.handle.base_split_handle import BaseSplitHandle
from common.handle.impl.text.split_text import SplitText
from common.utils.logger import maxkb_logger
from knowledge.models import File, FileSourceType
import uuid_utils.compat as uuid


class MinerUSplitHandle(BaseSplitHandle):
    """MinerU文档解析处理器"""
    
    def __init__(self):
        """初始化MinerU解析器"""
        self.mineru_loader = None
        self._init_mineru()
    
    def _init_mineru(self):
        """延迟初始化MinerU解析器"""
        try:
            # 导入本地的MinerU解析器（使用maxkb_adapter作为入口）
            from common.handle.impl.mineru.maxkb_adapter import MinerUExtractor
            self.mineru_loader = MinerUExtractor
            maxkb_logger.info("MinerU parser initialized successfully")
        except Exception as e:
            maxkb_logger.error(f"Failed to initialize MinerU parser: {str(e)}")
            self.mineru_loader = None
    
    def support(self, file, get_buffer):
        """
        判断是否支持该文件格式
        
        Args:
            file: 文件对象
            get_buffer: 获取文件缓冲区的函数
            
        Returns:
            bool: 是否支持该文件格式
        """
        # 只在启用MinerU时支持
        if not self.mineru_loader:
            return False
            
        file_name = file.name.lower()
        # MinerU支持PDF和PPT格式
        return file_name.endswith('.pdf') or file_name.endswith('.ppt') or file_name.endswith('.pptx')
    
    def handle(self, file, pattern_list: List, with_filter: bool, limit: int, get_buffer, save_image, **kwargs):
        """
        处理文档文件
        
        Args:
            file: 文件对象
            pattern_list: 分段模式列表
            with_filter: 是否过滤
            limit: 段落长度限制
            get_buffer: 获取文件缓冲区的函数
            save_image: 保存图片的函数
            **kwargs: 额外参数，包括模型配置等
            
        Returns:
            dict: 包含文档名称和段落列表的字典
        """
        try:
            # 如果MinerU未初始化，返回空结果
            if not self.mineru_loader:
                maxkb_logger.error("MinerU parser not initialized")
                return {'name': file.name, 'paragraphs': []}
            
            # 创建临时文件
            buffer = get_buffer(file)
            temp_file_path = f"/tmp/{uuid.uuid7()}_{file.name}"
            
            with open(temp_file_path, 'wb') as temp_file:
                temp_file.write(buffer)
            
            # 使用MinerU解析文档
            maxkb_logger.info(f"Processing document with MinerU: {file.name}")
            
            # 获取模型配置
            llm_model_id = kwargs.get('llm_model_id')
            vision_model_id = kwargs.get('vision_model_id')
            
            # 创建MinerU解析器实例，传入模型配置
            extractor = self.mineru_loader(
                llm_model_id=llm_model_id,
                vision_model_id=vision_model_id
            )
            
            # 异步运行解析
            documents = asyncio.run(self._process_with_mineru(extractor, temp_file_path, file.name))
            
            # 清理临时文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            if not documents:
                maxkb_logger.warning(f"MinerU returned no content for: {file.name}")
                return {'name': file.name, 'paragraphs': []}
            
            # 将Document转换为段落格式
            paragraphs = self._convert_to_paragraphs(documents, pattern_list, with_filter, limit, save_image)
            
            return {
                'name': file.name,
                'paragraphs': paragraphs
            }
            
        except Exception as e:
            maxkb_logger.error(f"Error processing document with MinerU: {str(e)}\n{traceback.format_exc()}")
            # 如果MinerU处理失败，返回空结果
            return {'name': file.name, 'paragraphs': []}
    
    async def _process_with_mineru(self, extractor, file_path: str, file_name: str) -> List[Document]:
        """
        使用MinerU异步处理文档
        
        Args:
            extractor: MinerU解析器实例
            file_path: 文件路径
            file_name: 文件名
            
        Returns:
            List[Document]: 解析后的文档列表
        """
        try:
            # 调用MinerU的process_file方法
            documents = await extractor.process_file(
                filepath=file_path,
                src_name=file_name,
                upload_options=None  # 暂时不处理图片上传
            )
            return documents
        except Exception as e:
            maxkb_logger.error(f"MinerU processing failed: {str(e)}")
            return []
    
    def _convert_to_paragraphs(self, documents: List[Document], pattern_list: List, 
                              with_filter: bool, limit: int, save_image) -> List[Dict]:
        """
        将Document对象转换为段落格式
        
        Args:
            documents: Document对象列表
            pattern_list: 分段模式列表
            with_filter: 是否过滤
            limit: 段落长度限制
            save_image: 保存图片的函数
            
        Returns:
            List[Dict]: 段落列表
        """
        paragraphs = []
        
        for doc in documents:
            content = doc.page_content
            metadata = doc.metadata
            
            # 提取图片资源
            resources = metadata.get('resources', [])
            if resources and save_image:
                # 处理图片资源
                self._handle_images(resources, save_image)
            
            # 如果有分段模式，按模式分段
            if pattern_list and len(pattern_list) > 0:
                split_text = SplitText(pattern_list, with_filter, limit)
                content_paragraphs = split_text.split(content)
                
                for para_content in content_paragraphs:
                    if para_content.strip():
                        paragraphs.append({
                            'content': para_content,
                            'title': metadata.get('title', ''),
                            'metadata': metadata
                        })
            else:
                # 如果内容太长，进行分段
                if len(content) > limit:
                    # 按限制长度分段
                    for i in range(0, len(content), limit):
                        segment = content[i:i + limit]
                        if segment.strip():
                            paragraphs.append({
                                'content': segment,
                                'title': metadata.get('title', '') + f' - Part {i//limit + 1}' if i > 0 else metadata.get('title', ''),
                                'metadata': metadata
                            })
                else:
                    # 直接作为一个段落
                    if content.strip():
                        paragraphs.append({
                            'content': content,
                            'title': metadata.get('title', ''),
                            'metadata': metadata
                        })
        
        return paragraphs
    
    def _handle_images(self, image_urls: List[str], save_image):
        """
        处理图片资源
        
        Args:
            image_urls: 图片URL列表
            save_image: 保存图片的函数
        """
        try:
            image_list = []
            for url in image_urls:
                # 从URL中提取图片信息
                # 这里需要根据实际的图片URL格式来处理
                # 暂时跳过图片处理
                pass
            
            if image_list:
                save_image(image_list)
        except Exception as e:
            maxkb_logger.error(f"Error handling images: {str(e)}")

    def get_content(self, file, save_image):
        """
        获取文档内容（用于纯文本提取）
        
        Args:
            file: 文件对象
            save_image: 保存图片的函数
            
        Returns:
            str: 文档的纯文本内容
        """
        try:
            # 如果MinerU未初始化，返回空内容
            if not self.mineru_loader:
                return ""
            
            # 使用handle方法获取段落
            result = self.handle(file, [], False, 999999, lambda f: f.read(), save_image)
            
            if result and 'paragraphs' in result:
                # 合并所有段落内容
                return '\n\n'.join([p['content'] for p in result['paragraphs'] if 'content' in p])
            
            return ""
        except Exception as e:
            maxkb_logger.error(f"Error getting content with MinerU: {str(e)}")
            return ""