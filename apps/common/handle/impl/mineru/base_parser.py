"""
Base parser module for MinerU - 公共代码基类

这个模块包含所有公共的处理逻辑，不依赖任何特定平台的代码。
通过适配器模式，支持不同平台的差异化实现。
"""

import os
import json
import hashlib
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Protocol
from dataclasses import dataclass
from abc import ABC, abstractmethod
from langchain.docstore.document import Document
from .logger import get_module_logger
logger = get_module_logger('base_parser')

from .config_base import MinerUConfig
from .converter import DocumentConverter
from .api_client import MinerUAPIClient, MinerUResult
from .image_processor import MinerUImageProcessor
from .content_processor import MinerUContentProcessor
from .context_types import EnhancedProcessingResult, PageContext, ContextMode
from .parallel_processor import ParallelMinerUProcessor, PageTask
from .parallel_processor_pool import get_parallel_processor
from .utils import get_file_hash, get_temp_dir


class PlatformAdapter(ABC):
    """平台适配器接口 - 定义不同平台需要实现的方法"""
    
    @abstractmethod
    async def trace_context(self, trace_id: str):
        """进入追踪上下文"""
        pass
    
    @abstractmethod
    async def lock_enter(self, temp_dir: str):
        """进入文件锁"""
        pass
    
    @abstractmethod
    async def lock_release(self, temp_dir: str):
        """释放文件锁"""
        pass
    
    @abstractmethod
    async def upload_file(self, file_path: str, options: Any = None) -> str:
        """上传文件，返回URL"""
        pass
    
    @abstractmethod
    def get_logger(self):
        """获取日志器"""
        return logger
    
    @abstractmethod
    def get_settings(self) -> Dict[str, Any]:
        """获取配置设置"""
        return {}
    
    @abstractmethod
    def get_learn_type(self, params: Dict[str, Any]) -> int:
        """获取learn_type参数"""
        return params.get('learn_type', 9)
    
    @abstractmethod
    def set_trace_id(self, trace_id: str):
        """设置trace ID用于日志跟踪"""
        pass


@dataclass
class ProcessingResult:
    """Main processing result data class - 公共数据结构"""
    success: bool
    content: str
    images: List[str]
    pages: List[Dict]
    advanced_parser: Dict
    error: Optional[str] = None
    page_contexts: Optional[List[PageContext]] = None
    content_list: Optional[List[Dict]] = None
    page_chunks: Optional[List[Dict]] = None


class BaseMinerUExtractor:
    """
    基础MinerU解析器 - 包含所有公共逻辑
    
    这个类包含了所有与平台无关的处理逻辑，
    通过适配器模式支持不同平台的差异化实现。
    """
    
    def __init__(self, adapter: PlatformAdapter, config=None, **kwargs):
        """
        初始化基础解析器
        
        Args:
            adapter: 平台适配器实例
            config: 配置实例（可选，如果不提供则创建默认配置）
            **kwargs: 平台特定的参数
        """
        self.adapter = adapter
        self.config = config if config else MinerUConfig()
        self.logger = adapter.get_logger()
        
        # 从适配器获取learn_type
        self.learn_type = adapter.get_learn_type(kwargs)
        
        # 保存其他参数供子类使用
        self.platform_params = kwargs
        
        # 保存adapter作为platform_adapter（为了兼容性）
        self.platform_adapter = adapter
        
        # 初始化组件
        self.converter = DocumentConverter(self.config)
        self.image_processor = MinerUImageProcessor(self.config)
        self.content_processor = MinerUContentProcessor(self.config)
        
        # 获取并行处理器，传递platform_adapter和配置
        self.parallel_processor = get_parallel_processor(self.learn_type, self.platform_adapter, self.config)

    async def process_file(self, filepath: str, src_name: str = None, 
                          upload_options: Tuple = None) -> List[Document]:
        """
        主处理方法 - 处理文档的完整流程
        
        这是公共的处理流程，通过适配器调用平台特定的功能。
        """
        # 生成文件ID
        src_fileid = get_file_hash(filepath)
        
        # 使用适配器的追踪上下文
        async with self.adapter.trace_context(src_fileid):
            try:
                self.logger.info(f"mineru-parser: starting file processing: {filepath}, file hash: {src_fileid}")
                
                # 设置处理环境
                temp_dir = get_temp_dir(src_fileid, self.learn_type, self.config.cache_version)
                await self.adapter.lock_enter(temp_dir)
                
                try:
                    # 检查缓存
                    if self.config.enable_cache:
                        cached_docs = await self._load_from_cache(temp_dir, filepath, src_name)
                        if cached_docs:
                            self.logger.info(f"mineru-parser: loaded {len(cached_docs)} documents from cache")
                            return cached_docs
                    
                    # 处理文档
                    result = await self._process_document_pipeline(
                        filepath, src_name, temp_dir, src_fileid, upload_options
                    )
                    
                    self.logger.info(f"mineru-parser: pipeline returned result with success={result.success}")
                    
                    if result.success:
                        if result.page_chunks:
                            docs = self._create_page_documents(result, filepath, src_name, temp_dir)
                            self.logger.info(f"mineru-parser: processing completed - returning {len(docs)} page documents")
                            return docs
                        else:
                            doc = self._create_document(result, filepath, src_name, temp_dir)
                            return [doc]
                    else:
                        raise Exception(result.error or "Processing failed")
                        
                finally:
                    await self.adapter.lock_release(temp_dir)
                    
                    # 清理临时目录
                    if not self.config.enable_cache:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
            except Exception as e:
                self.logger.error(f"mineru-parser: processing failed: {str(e)}")
                raise

    async def _process_document_pipeline(self, filepath: str, src_name: str, 
                                       temp_dir: str, src_fileid: str,
                                       upload_options: Tuple) -> ProcessingResult:
        """处理文档的流水线 - 公共逻辑"""
        try:
            start_time = time.time()
            
            # Step 1: 文件类型检测和转换
            pdf_path, is_ppt_source = await self.converter.handle_file_input(
                filepath, temp_dir, src_fileid
            )
            
            # Step 2: PDF格式检测
            if not is_ppt_source:
                is_ppt_format, metadata = self.converter.detect_pdf_format(pdf_path, src_fileid)
                self.logger.info(f"mineru-parser: PDF format detection: is_ppt={is_ppt_format}")
            else:
                is_ppt_format = True
            
            # Step 3: 提取PDF页面
            pages_info = self.converter.extract_pdf_pages(pdf_path, src_fileid)
            
            # Step 4: 处理文档
            result = await self._process_document_format(
                pdf_path, pages_info, temp_dir, src_fileid, upload_options,
                is_ppt_format=(is_ppt_format or is_ppt_source)
            )
            
            processing_duration = time.time() - start_time
            
            # 添加处理元数据
            result.advanced_parser.update({
                'processing_duration': processing_duration,
                'is_ppt_source': is_ppt_source,
                'is_ppt_format': is_ppt_format,
                'learn_type': self.learn_type,
                'mineru_version': self.config.cache_version
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-parser: pipeline failed: {str(e)}")
            return ProcessingResult(
                success=False,
                content="",
                images=[],
                pages=[],
                advanced_parser={},
                error=str(e)
            )

    async def _process_document_format(self, pdf_path: str, pages_info: List, temp_dir: str,
                                      src_fileid: str, upload_options: Tuple, 
                                      is_ppt_format: bool) -> ProcessingResult:
        """统一的文档处理方法 - 使用并行处理"""
        try:
            format_type = "PPT" if is_ppt_format else "non-PPT"
            self.logger.info(f"mineru-parser: processing as {format_type} format")
            
            if not self.parallel_processor:
                raise RuntimeError("Parallel processor not initialized")
            
            result = await self._process_document_parallel(
                pdf_path, pages_info, temp_dir, src_fileid, 
                upload_options, is_ppt_format
            )
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-parser: {format_type} format processing failed: {str(e)}")
            raise

    async def _process_document_parallel(self, pdf_path: str, pages_info: List, 
                                       temp_dir: str, src_fileid: str,
                                       upload_options: Tuple, 
                                       is_ppt_format: bool) -> ProcessingResult:
        """并行处理文档 - 带缓存支持"""
        try:
            self.logger.info(f"mineru-parser: using parallel processing pipeline")
            
            # 加载已缓存的页面
            cached_pages = self._load_cached_pages(temp_dir)
            if cached_pages:
                self.logger.info(f"mineru-parser: found {len(cached_pages)} cached pages")
            
            # 获取上传回调（通过适配器）
            upload_callback = lambda file_path: self.adapter.upload_file(file_path, upload_options)
            
            # 并行处理文档
            completed_tasks = await self.parallel_processor.process_document_with_cache(
                pdf_path, temp_dir, src_fileid, is_ppt_format,
                len(pages_info), upload_callback if upload_options else None, upload_options,
                cached_pages=cached_pages,
                save_callback=lambda idx, data: self._save_page_cache(temp_dir, idx, data)
            )
            
            self.logger.info(f"mineru-parser: received {len(completed_tasks)} completed tasks")
            
            # 转换结果
            result = self._convert_parallel_results(completed_tasks, pages_info)
            
            # 标记缓存完成
            if len(result.page_chunks) == len(pages_info):
                self._mark_cache_complete(temp_dir, len(pages_info))
            
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-parser: parallel processing failed: {str(e)}")
            raise

    def _build_final_content(self, pages: List[Dict]) -> str:
        """构建最终内容 - 公共方法"""
        content_parts = []
        for index, page in enumerate(pages):
            content_parts.append(f"__PAGE_OF_PORTION_{index + 1}__\n\n")
            content_parts.append(page['content'])
            content_parts.append('\n\n')
        return ''.join(content_parts)

    def _create_document(self, result: ProcessingResult, filepath: str, 
                        src_name: str, temp_dir: str) -> Document:
        """创建Document对象 - 公共方法"""
        # 保存结果到JSON
        json_filepath = os.path.join(temp_dir, 'mineru_result.json')
        with open(json_filepath, 'w', encoding='utf-8') as file:
            json.dump(result.advanced_parser, file, ensure_ascii=False, indent=2)
        
        # 保存内容
        content_filepath = os.path.join(temp_dir, 'content.txt')
        with open(content_filepath, 'w', encoding='utf-8') as file:
            file.write(result.content)
        
        # 准备元数据
        doc_src_name = src_name if src_name else filepath
        doc_src_name = os.path.splitext(os.path.basename(doc_src_name))[0] + Path(filepath).suffix
        
        # 创建文档
        doc = Document(
            page_content=result.content,
            metadata={
                'title': doc_src_name,
                'source': filepath,
                'outlines': '',
                'advanced_parser': json.dumps(result.advanced_parser, ensure_ascii=False),
                'resources': result.images,
                'parser_type': 'mineru',
                'parser_version': self.config.cache_version,
                'context_aware': self.config.enable_context_extraction
            }
        )
        
        return doc

    def _create_page_documents(self, result: ProcessingResult, filepath: str, 
                              src_name: str, temp_dir: str) -> List[Document]:
        """创建分页文档 - 公共方法"""
        docs = []
        base_name = src_name if src_name else filepath
        base_name = os.path.splitext(os.path.basename(base_name))[0]
        file_ext = Path(filepath).suffix
        
        # 保存主结果
        main_advanced_parser = result.advanced_parser.copy()
        main_advanced_parser['per_page_processing'] = True
        main_advanced_parser['total_pages'] = len(result.page_chunks)
        
        main_json_filepath = os.path.join(temp_dir, 'mineru_result.json')
        with open(main_json_filepath, 'w', encoding='utf-8') as file:
            json.dump(main_advanced_parser, file, ensure_ascii=False, indent=2)
        
        # 跟踪空页面
        empty_pages = []
        
        for chunk in result.page_chunks:
            page_num = chunk['page_idx'] + 1
            
            # 检查页面是否为空
            page_content = chunk.get('content', '').strip()
            page_images = chunk.get('images', [])
            
            if not page_content and not page_images:
                self.logger.error(f"mineru-parser: Page {page_num} has no content and no images - skipping")
                empty_pages.append(page_num)
                continue
            
            # 创建页面元数据
            page_advanced_parser = {
                'learn_type': self.learn_type,
                'page_number': page_num,
                'total_pages': len(result.page_chunks),
                'has_tables': chunk.get('has_tables', False),
                'images': chunk.get('images', []),
                'processing_metadata': chunk.get('processing_metadata', {}),
                'mineru_metadata': result.advanced_parser.get('mineru_metadata', {}),
                'per_page_processing': True
            }
            
            # 保存页面结果
            page_json_filepath = os.path.join(temp_dir, f'mineru_result_page_{page_num}.json')
            with open(page_json_filepath, 'w', encoding='utf-8') as file:
                json.dump(page_advanced_parser, file, ensure_ascii=False, indent=2)
            
            # 保存页面内容
            page_content_filepath = os.path.join(temp_dir, f'page_{page_num}_content.txt')
            with open(page_content_filepath, 'w', encoding='utf-8') as file:
                file.write(chunk['content'])
            
            # 创建文档
            doc = Document(
                page_content=chunk['content'],
                metadata={
                    'title': f"{base_name}_page_{page_num}{file_ext}",
                    'source': filepath,
                    'page': page_num,
                    'total_pages': len(result.page_chunks),
                    'outlines': '',
                    'advanced_parser': json.dumps(page_advanced_parser, ensure_ascii=False),
                    'resources': chunk.get('images', []),
                    'parser_type': 'mineru',
                    'parser_version': self.config.cache_version,
                    'context_aware': self.config.enable_context_extraction,
                    'has_tables': chunk.get('has_tables', False)
                }
            )
            
            docs.append(doc)
        
        # 报告空页面
        if empty_pages:
            self.logger.error(f"mineru-parser: Found {len(empty_pages)} empty pages: {empty_pages}")
        
        return docs

    def _convert_parallel_results(self, completed_tasks: List[PageTask], 
                                pages_info: List) -> ProcessingResult:
        """转换并行处理结果 - 公共方法"""
        page_chunks = []
        all_processed_images = {}
        
        for task in completed_tasks:
            # 获取内容并清理
            content = task.refined_content or task.content or ''
            
            if content and not content.strip():
                self.logger.info(f"mineru-parser: page {task.page_idx} contains only whitespace")
                content = ''
            
            # 清理内容
            content = self.content_processor._clean_hallucination_patterns(content)
            MAX_CONTENT_LENGTH = 30000
            if len(content) > MAX_CONTENT_LENGTH:
                self.logger.warning(f"mineru-parser: page {task.page_idx} content too long, truncating")
                content = content[:MAX_CONTENT_LENGTH] + "..."
            
            page_chunk = {
                'page_idx': task.page_idx,
                'content': content,
                'images': task.images,
                'processed_images': task.processed_images,
                'image_descriptions': task.image_descriptions,
                'has_tables': task.metadata.get('has_tables', False),
                'processing_metadata': task.metadata
            }
            page_chunks.append(page_chunk)
            all_processed_images.update(task.processed_images)
        
        # 构建页面结构
        pages = []
        for chunk in page_chunks:
            pages.append({
                'index': chunk['page_idx'],
                'content': chunk['content'],
                'image_map': {},
                'summary': '',
                'input_tokens': 0,
                'output_tokens': 0,
                'dura': 0.0,
                'has_tables': chunk.get('has_tables', False),
                'images': chunk.get('images', [])
            })
        
        # 构建最终内容
        final_content = self._build_final_content(pages)
        
        # 构建元数据
        advanced_parser = {
            'learn_type': self.learn_type,
            'input_tokens': 0,
            'output_tokens': 0,
            'dura': 0,
            'pages': pages,
            'parallel_processing': True,
            'page_processing_metadata': [chunk.get('processing_metadata', {}) for chunk in page_chunks],
            'image_count': len(all_processed_images),
            'context_extraction_enabled': self.config.enable_context_extraction,
            'multimodal_refinement_enabled': self.config.enable_multimodal_refinement,
            'per_page_processing': True
        }
        
        return ProcessingResult(
            success=True,
            content=final_content,
            images=list(all_processed_images.values()),
            pages=pages,
            advanced_parser=advanced_parser,
            page_chunks=page_chunks
        )

    # ========== 缓存相关方法 ==========
    
    async def _load_from_cache(self, temp_dir: str, filepath: str, src_name: str) -> Optional[List[Document]]:
        """从缓存加载 - 公共方法"""
        try:
            result_json_path = os.path.join(temp_dir, 'mineru_result.json')
            cache_status_path = os.path.join(temp_dir, 'cache_status.json')
            
            # 检查缓存状态
            if os.path.exists(cache_status_path):
                with open(cache_status_path, 'r', encoding='utf-8') as f:
                    cache_status = json.load(f)
                
                if cache_status.get('status') == 'partial':
                    self.logger.info(f"mineru-parser: found partial cache")
                    return None
                elif cache_status.get('status') != 'complete':
                    return None
            
            if not os.path.exists(result_json_path):
                return None
            
            # 加载主结果
            with open(result_json_path, 'r', encoding='utf-8') as f:
                advanced_parser = json.load(f)
            
            # 检查是否是分页处理
            if advanced_parser.get('per_page_processing'):
                docs = []
                total_pages = advanced_parser.get('total_pages', 0)
                
                for page_num in range(1, total_pages + 1):
                    page_json_path = os.path.join(temp_dir, f'mineru_result_page_{page_num}.json')
                    page_content_path = os.path.join(temp_dir, f'page_{page_num}_content.txt')
                    
                    if not os.path.exists(page_json_path) or not os.path.exists(page_content_path):
                        return None
                    
                    with open(page_content_path, 'r', encoding='utf-8') as f:
                        page_content = f.read()
                    
                    if page_content == '[EMPTY_PAGE]':
                        page_content = ''
                    
                    with open(page_json_path, 'r', encoding='utf-8') as f:
                        page_advanced_parser = json.load(f)
                    
                    base_name = src_name if src_name else filepath
                    base_name = os.path.splitext(os.path.basename(base_name))[0]
                    file_ext = Path(filepath).suffix
                    
                    doc = Document(
                        page_content=page_content,
                        metadata={
                            'title': f"{base_name}_page_{page_num}{file_ext}",
                            'source': filepath,
                            'page': page_num,
                            'total_pages': total_pages,
                            'outlines': '',
                            'advanced_parser': json.dumps(page_advanced_parser, ensure_ascii=False),
                            'resources': page_advanced_parser.get('images', []),
                            'parser_type': 'mineru',
                            'parser_version': self.config.cache_version,
                            'context_aware': self.config.enable_context_extraction,
                            'has_tables': page_advanced_parser.get('has_tables', False)
                        }
                    )
                    docs.append(doc)
                
                self.logger.info(f"mineru-parser: cache hit - loaded {len(docs)} page documents")
                return docs
            else:
                # 单文档结果
                content_path = os.path.join(temp_dir, 'content.txt')
                if not os.path.exists(content_path):
                    return None
                
                with open(content_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                doc_src_name = src_name if src_name else filepath
                doc_src_name = os.path.splitext(os.path.basename(doc_src_name))[0] + Path(filepath).suffix
                
                doc = Document(
                    page_content=content,
                    metadata={
                        'title': doc_src_name,
                        'source': filepath,
                        'outlines': '',
                        'advanced_parser': json.dumps(advanced_parser, ensure_ascii=False),
                        'resources': advanced_parser.get('pages', [{}])[0].get('images', []),
                        'parser_type': 'mineru',
                        'parser_version': self.config.cache_version,
                        'context_aware': self.config.enable_context_extraction
                    }
                )
                
                self.logger.info(f"mineru-parser: cache hit - loaded single document")
                return [doc]
                
        except Exception as e:
            self.logger.error(f"mineru-parser: error loading from cache: {str(e)}")
            return None

    def _save_page_cache(self, temp_dir: str, page_idx: int, page_data: Dict):
        """保存页面缓存 - 公共方法"""
        try:
            page_num = page_idx + 1
            
            # 保存页面内容
            page_content_path = os.path.join(temp_dir, f'page_{page_num}_content.txt')
            content = page_data.get('content', '')
            page_images = page_data.get('images', [])
            
            if (not content or not content.strip()) and not page_images:
                self.logger.error(f"mineru-parser: Page {page_num} has no content and no images")
                return
            
            if not content or not content.strip():
                content = '[EMPTY_PAGE]'
            
            with open(page_content_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 保存页面元数据
            page_meta_path = os.path.join(temp_dir, f'page_{page_num}_meta.json')
            page_metadata = {
                'page_idx': page_idx,
                'page_num': page_num,
                'has_tables': page_data.get('has_tables', False),
                'images': page_data.get('images', []),
                'processed_images': page_data.get('processed_images', {}),
                'image_descriptions': page_data.get('image_descriptions', {}),
                'processing_metadata': page_data.get('processing_metadata', {}),
                'cached_at': time.time()
            }
            with open(page_meta_path, 'w', encoding='utf-8') as f:
                json.dump(page_metadata, f, ensure_ascii=False, indent=2)
            
            # 更新缓存状态
            self._update_cache_status(temp_dir, page_idx)
            
            self.logger.debug(f"mineru-parser: saved page {page_num} to cache")
            
        except Exception as e:
            self.logger.error(f"mineru-parser: failed to save page cache: {str(e)}")

    def _update_cache_status(self, temp_dir: str, completed_page_idx: int):
        """更新缓存状态 - 公共方法"""
        cache_status_path = os.path.join(temp_dir, 'cache_status.json')
        
        try:
            if os.path.exists(cache_status_path):
                with open(cache_status_path, 'r', encoding='utf-8') as f:
                    status = json.load(f)
            else:
                status = {
                    'status': 'partial',
                    'completed_pages': 0,
                    'completed_indices': [],
                    'total_pages': None,
                    'started_at': time.time(),
                    'updated_at': time.time()
                }
            
            if completed_page_idx not in status['completed_indices']:
                status['completed_indices'].append(completed_page_idx)
                status['completed_pages'] = len(status['completed_indices'])
            
            status['updated_at'] = time.time()
            
            with open(cache_status_path, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"mineru-parser: failed to update cache status: {str(e)}")

    def _mark_cache_complete(self, temp_dir: str, total_pages: int):
        """标记缓存完成 - 公共方法"""
        cache_status_path = os.path.join(temp_dir, 'cache_status.json')
        
        try:
            status = {
                'status': 'complete',
                'completed_pages': total_pages,
                'total_pages': total_pages,
                'completed_at': time.time()
            }
            
            with open(cache_status_path, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"mineru-parser: marked cache as complete")
            
        except Exception as e:
            self.logger.error(f"mineru-parser: failed to mark cache complete: {str(e)}")

    def _load_cached_pages(self, temp_dir: str) -> Dict[int, Dict]:
        """加载缓存页面 - 公共方法"""
        cached_pages = {}
        
        try:
            cache_status_path = os.path.join(temp_dir, 'cache_status.json')
            if os.path.exists(cache_status_path):
                with open(cache_status_path, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                
                for page_idx in status.get('completed_indices', []):
                    page_num = page_idx + 1
                    
                    content_path = os.path.join(temp_dir, f'page_{page_num}_content.txt')
                    meta_path = os.path.join(temp_dir, f'page_{page_num}_meta.json')
                    
                    if os.path.exists(content_path) and os.path.exists(meta_path):
                        with open(content_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        if content == '[EMPTY_PAGE]':
                            content = ''
                        
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        
                        cached_pages[page_idx] = {
                            'content': content,
                            'metadata': metadata
                        }
                
                self.logger.info(f"mineru-parser: loaded {len(cached_pages)} cached pages")
                
        except Exception as e:
            self.logger.error(f"mineru-parser: failed to load cached pages: {str(e)}")
        
        return cached_pages