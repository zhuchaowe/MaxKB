# -*- coding: utf-8 -*-
"""
MinerU Split Handle - 使用MinerU服务处理PDF文档
"""
import os
from typing import List, Dict, Any
from common.handle.base_split_handle import BaseSplitHandle
from common.handle.impl.mineru.maxkb_adapter.adapter import MinerUAdapter
from common.utils.logger import maxkb_logger as logger


class MinerUSplitHandle(BaseSplitHandle):
    """
    使用MinerU服务处理PDF等复杂文档格式
    """
    
    def __init__(self):
        super().__init__()
        self.mineru_adapter = None
        
    def support(self, file, get_buffer, **kwargs):
        """
        检查是否支持该文件类型
        当前仅支持PDF文件，且需要MinerU服务配置
        预览模式下不使用MinerU处理器，因为处理速度较慢
        """
        # 如果是预览模式，不使用MinerU处理器
        if kwargs.get('is_preview', False):
            return False
            
        file_name = file.name.lower()
        # 检查文件扩展名
        if not file_name.endswith('.pdf'):
            return False
            
        # 检查MinerU配置
        mineru_api_type = os.environ.get('MINERU_API_TYPE', '')
        if not mineru_api_type:
            return False
            
        return True
    
    def handle(self, file, pattern_list: List, with_filter: bool, limit: int, 
               get_buffer, save_image):
        """
        使用MinerU处理文档
        """
        try:
            logger.info(f"MinerUSplitHandle.handle called for file: {file.name if hasattr(file, 'name') else 'unknown'}")
            
            # 初始化MinerU适配器
            if not self.mineru_adapter:
                logger.info("Initializing MinerU adapter")
                self.mineru_adapter = MinerUAdapter()
            
            # 获取文件内容
            buffer = get_buffer(file)
            logger.info(f"File buffer size: {len(buffer) if buffer else 0} bytes")
            
            # 处理文档
            logger.info("Calling MinerU adapter to process document")
            result = self.mineru_adapter.process_document(
                file_content=buffer,
                file_name=file.name if hasattr(file, 'name') else 'document.pdf',
                save_image_func=save_image
            )
            logger.info(f"MinerU adapter returned result with {len(result.get('sections', []))} sections")
            
            # 转换为段落格式
            paragraphs = []
            for section in result.get('sections', []):
                content = section.get('content', '')
                if content:
                    paragraph = {
                        'content': content,
                        'title': section.get('title', ''),
                        'images': section.get('images', [])
                    }
                    paragraphs.append(paragraph)
            
            logger.info(f"Converted to {len(paragraphs)} paragraphs before pattern processing")
            
            # 应用分段模式
            if pattern_list and len(pattern_list) > 0:
                split_paragraphs = []
                for paragraph in paragraphs:
                    content = paragraph['content']
                    for pattern in pattern_list:
                        split_contents = pattern.parse(content)
                        for split_content in split_contents:
                            split_paragraph = {
                                'content': split_content,
                                'title': paragraph.get('title', ''),
                                'images': paragraph.get('images', [])
                            }
                            split_paragraphs.append(split_paragraph)
                paragraphs = split_paragraphs
            
            # 限制返回数量
            if limit > 0:
                paragraphs = paragraphs[:limit]
            
            logger.info(f"MinerUSplitHandle returning {len(paragraphs)} paragraphs")
            return paragraphs
            
        except Exception as e:
            logger.error(f"MinerU处理文档失败: {str(e)}", exc_info=True)
            # 如果MinerU处理失败，回退到PDF处理器
            from common.handle.impl.text.pdf_split_handle import PdfSplitHandle
            pdf_handler = PdfSplitHandle()
            return pdf_handler.handle(file, pattern_list, with_filter, limit, 
                                     get_buffer, save_image)
    
    def get_content(self, file, get_buffer):
        """
        获取文件的文本内容
        """
        try:
            # 如果MinerU可用，使用MinerU提取内容
            if self.mineru_adapter is None:
                # 检查MinerU配置
                mineru_api_type = os.environ.get('MINERU_API_TYPE', '')
                if mineru_api_type:
                    self.mineru_adapter = MinerUAdapter()
            
            if self.mineru_adapter:
                buffer = get_buffer(file)
                result = self.mineru_adapter.process_document(
                    file_content=buffer,
                    file_name=file.name,
                    save_image_func=None
                )
                
                # 合并所有sections的内容
                content_parts = []
                for section in result.get('sections', []):
                    if section.get('content'):
                        content_parts.append(section['content'])
                
                return '\n'.join(content_parts) if content_parts else ''
        except Exception as e:
            logger.warning(f"MinerU获取内容失败，回退到PDF处理器: {str(e)}")
        
        # 回退到PDF处理器
        from common.handle.impl.text.pdf_split_handle import PdfSplitHandle
        pdf_handler = PdfSplitHandle()
        return pdf_handler.get_content(file, get_buffer)