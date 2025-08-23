"""
Parallel processing module for MinerU with task-level granularity.

This module implements a producer-consumer pattern with four independent
processing threads for maximum parallelism.
"""

import asyncio
import os
import queue
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from .logger import get_module_logger
logger = get_module_logger('parallel_processor')

from .config_base import MinerUConfig
from .converter import DocumentConverter
from .api_client import MinerUAPIClient, MinerUResult
from .image_processor import MinerUImageProcessor
from .content_processor import MinerUContentProcessor


class TaskStatus(Enum):
    """Task processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PageTask:
    """Represents a page-level processing task"""
    page_idx: int
    pdf_path: str
    temp_dir: str
    src_fileid: str
    status: TaskStatus = TaskStatus.PENDING
    content: Optional[str] = None
    images: List[str] = field(default_factory=list)
    refined_content: Optional[str] = None
    processed_images: Dict[str, str] = field(default_factory=dict)
    image_descriptions: Dict[str, Dict] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Non-serializable fields
    upload_callback: Optional[Any] = field(default=None, repr=False)
    upload_options: Optional[Any] = field(default=None, repr=False)
    meaningful_images: List[Any] = field(default_factory=list, repr=False)
    save_callback: Optional[Any] = field(default=None, repr=False)  # Cache save callback
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3


@dataclass 
class ProcessingQueues:
    """Container for all processing queues"""
    parsing_queue: queue.Queue
    content_refinement_queue: queue.Queue
    image_recognition_queue: queue.Queue
    image_upload_queue: queue.Queue


class ParallelMinerUProcessor:
    """
    Parallel processor implementing task-level granularity.
    
    Architecture:
    - 4 independent threads: parsing, content refinement, image recognition, image upload
    - Producer-consumer pattern with queues connecting stages
    - Page-level task granularity for maximum parallelism
    """
    
    def __init__(self, config: MinerUConfig, learn_type: int = 9, platform_adapter=None):
        self.config = config
        self.learn_type = learn_type
        self.logger = logger
        self.platform_adapter = platform_adapter
        
        # Initialize components
        self.converter = DocumentConverter(config)
        self.content_processor = MinerUContentProcessor(config)
        self.image_processor = MinerUImageProcessor(config)
        
        # Initialize queues
        self.queues = ProcessingQueues(
            parsing_queue=queue.Queue(maxsize=config.queue_size),
            content_refinement_queue=queue.Queue(maxsize=config.queue_size),
            image_recognition_queue=queue.Queue(maxsize=config.queue_size),
            image_upload_queue=queue.Queue(maxsize=config.queue_size)
        )
        
        # Task tracking - use document-specific dictionaries
        self.document_tasks: Dict[str, Dict[int, PageTask]] = {}  # src_fileid -> page_idx -> task
        self.tasks_lock = threading.Lock()
        
        # Thread control
        self.shutdown_event = threading.Event()
        self.threads: List[threading.Thread] = []
        
        # Results collection - per document
        self.document_completed_tasks: Dict[str, List[PageTask]] = {}  # src_fileid -> completed tasks
        self.completed_lock = threading.Lock()
        
        # Async initialization flag
        self._initialized = False
        
        # Queue monitoring
        self._monitor_thread = None
        self._monitor_stop_event = threading.Event()
        
        # Document-level language detection cache
        self.document_languages: Dict[str, str] = {}  # src_fileid -> detected language
        
    async def initialize(self):
        """Initialize async components like image processor"""
        if not self._initialized:
            await self.image_processor.initialize()
            self._initialized = True
        
    def initialize_threads(self):
        """
        Initialize and start all processing threads.
        
        This is the main initialization function that starts:
        1. Parsing thread - processes MinerU API calls
        2. Content refinement thread - refines content with AI
        3. Image recognition thread - classifies and recognizes images
        4. Image upload thread - uploads images to storage
        """
        self.logger.info("Initializing parallel processing threads...")
        
        # Create threads
        threads = [
            threading.Thread(target=self._run_async_thread, args=(self._parsing_worker,), 
                           name="MinerU-Parser"),
            threading.Thread(target=self._run_async_thread, args=(self._content_refinement_worker,), 
                           name="MinerU-ContentRefiner"),
            threading.Thread(target=self._run_async_thread, args=(self._image_recognition_worker,), 
                           name="MinerU-ImageRecognizer"),
            threading.Thread(target=self._run_async_thread, args=(self._image_upload_worker,), 
                           name="MinerU-ImageUploader")
        ]
        
        # Start all threads
        for thread in threads:
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
            self.logger.info(f"Started thread: {thread.name}")
            
    def _run_async_thread(self, async_worker):
        """Run async worker in thread with its own event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_worker())
        finally:
            loop.close()
            
    async def _parsing_worker(self):
        """
        Parsing worker thread with on-demand batch processing.
        
        Consumes: PageTask from parsing_queue
        Produces: PageTask to content_refinement_queue and image_recognition_queue
        """
        self.logger.info("Parsing worker started")
        
        # Cache for batch results: {src_fileid: {batch_idx: MinerUResult}}
        document_batch_results = {}
        # Track which pages belong to which batch
        document_batch_info = {}  # {src_fileid: {'batch_size': int, 'total_pages': int}}
        
        # Initialize API client
        async with MinerUAPIClient(self.config) as api_client:
            while not self.shutdown_event.is_set():
                try:
                    # Get task from queue (timeout to check shutdown)
                    try:
                        task = self.queues.parsing_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue
                        
                    # Set trace context for this task with page number
                    if self.platform_adapter:
                        self.platform_adapter.set_trace_id(f"{task.src_fileid}_p{task.page_idx + 1}")
                    
                    self.logger.info(f"Parser processing page {task.page_idx + 1}")
                    
                    # Update task status
                    with self.tasks_lock:
                        task.status = TaskStatus.PROCESSING
                        # Track task by document
                        if task.src_fileid not in self.document_tasks:
                            self.document_tasks[task.src_fileid] = {}
                        self.document_tasks[task.src_fileid][task.page_idx] = task
                        
                    try:
                        # Determine batch size and batch index for this page
                        batch_size = self.config.batch_size if self.config.batch_processing_enabled else 0
                        
                        # Initialize document batch info if needed
                        if task.src_fileid not in document_batch_info:
                            # Get total pages from metadata or detect from PDF
                            total_pages = task.metadata.get('total_pages', 0)
                            if total_pages == 0:
                                # Count pages if not provided
                                import fitz
                                with fitz.open(task.pdf_path) as doc:
                                    total_pages = len(doc)
                            
                            document_batch_info[task.src_fileid] = {
                                'batch_size': batch_size if batch_size > 0 and total_pages > batch_size else 0,
                                'total_pages': total_pages
                            }
                            document_batch_results[task.src_fileid] = {}
                            
                        batch_info = document_batch_info[task.src_fileid]
                        
                        # Calculate batch index for this page
                        if batch_info['batch_size'] > 0:
                            batch_idx = task.page_idx // batch_info['batch_size']
                            batch_start = batch_idx * batch_info['batch_size']
                            batch_end = min(batch_start + batch_info['batch_size'], batch_info['total_pages'])
                            
                            # Check if we have results for this batch
                            if batch_idx not in document_batch_results[task.src_fileid]:
                                # Need to process this batch
                                self.logger.info(f"Parser: processing batch {batch_idx + 1} (pages {batch_start + 1}-{batch_end}) for {task.src_fileid[:8]}...")
                                
                                # Split PDF for this batch
                                batch_pdf_path = await self._split_pdf_batch(
                                    task.pdf_path, task.temp_dir, batch_start, batch_end, batch_idx
                                )
                                
                                # Process this batch
                                batch_result = await api_client._process_batch_self_hosted(
                                    batch_pdf_path, task.temp_dir, task.src_fileid,
                                    batch_idx, batch_start, batch_end,
                                    task.metadata.get('is_ppt_format', False)
                                ) if self.config.mineru_api_type == "self_hosted" else await api_client._process_batch_cloud(
                                    batch_pdf_path, task.temp_dir, task.src_fileid,
                                    batch_idx, batch_start, batch_end,
                                    task.metadata.get('is_ppt_format', False)
                                )
                                
                                if not batch_result.success:
                                    # Batch failed, try single-page processing for this batch
                                    self.logger.warning(f"Batch {batch_idx + 1} failed, falling back to single-page processing for pages {batch_start + 1}-{batch_end}")
                                    
                                    # Mark this batch as needing single-page processing
                                    if task.src_fileid not in document_batch_results:
                                        document_batch_results[task.src_fileid] = {}
                                    
                                    # Create a special marker for failed batch
                                    document_batch_results[task.src_fileid][batch_idx] = MinerUResult(
                                        success=False,
                                        content="",
                                        images=[],
                                        tables=[],
                                        metadata={"batch_failed": True, "needs_single_page": True,
                                                "batch_start": batch_start, "batch_end": batch_end},
                                        error=batch_result.error
                                    )
                                    
                                    # Process pages individually for this failed batch
                                    batch_result = await self._process_batch_as_single_pages(
                                        task, api_client, batch_start, batch_end, batch_idx
                                    )
                                    
                                    if batch_result.success:
                                        # Update cache with successful single-page results
                                        document_batch_results[task.src_fileid][batch_idx] = batch_result
                                        self.logger.info(f"Parser: single-page processing succeeded for batch {batch_idx + 1}")
                                    else:
                                        raise Exception(batch_result.error or f"Batch {batch_idx} processing failed even with single-page fallback")
                                else:
                                    # Original batch succeeded, cache it
                                    document_batch_results[task.src_fileid][batch_idx] = batch_result
                                    self.logger.info(f"Parser: cached batch {batch_idx + 1} result for {task.src_fileid[:8]}...")
                            
                            # Use cached batch result
                            result = document_batch_results[task.src_fileid][batch_idx]
                            self.logger.debug(f"Parser: using cached batch {batch_idx + 1} for page {task.page_idx + 1}")
                            
                        else:
                            # No batching, process entire document
                            if 'full' not in document_batch_results.get(task.src_fileid, {}):
                                self.logger.info(f"Parser: calling MinerU API for full document {task.src_fileid[:8]}...")
                                result = await api_client.process_document(
                                    task.pdf_path, task.temp_dir, task.src_fileid,
                                    is_ppt_converted=task.metadata.get('is_ppt_format', False),
                                    batch_size=0  # Disable batching
                                )
                                
                                if not result.success:
                                    raise Exception(result.error or "MinerU parsing failed")
                                    
                                # Cache the result
                                if task.src_fileid not in document_batch_results:
                                    document_batch_results[task.src_fileid] = {}
                                document_batch_results[task.src_fileid]['full'] = result
                            else:
                                result = document_batch_results[task.src_fileid]['full']
                                self.logger.debug(f"Parser: using cached full result for page {task.page_idx + 1}")
                        
                        # Extract page-specific content from the full document result
                        self.logger.debug(f"Extracting page data for page {task.page_idx + 1}")
                        self.logger.debug(f"Result type: {type(result)}, has content: {hasattr(result, 'content')}")
                        if hasattr(result, 'metadata'):
                            self.logger.debug(f"Result metadata keys: {list(result.metadata.keys())}")
                        
                        page_data = self._extract_page_data(result, task.page_idx)
                        task.content = page_data.get('content', '')
                        task.images = page_data.get('images', [])
                        task.metadata.update(page_data.get('metadata', {}))
                        
                        self.logger.debug(f"Extracted content length: {len(task.content)}, images: {len(task.images)}")
                        
                        # Store content_list in metadata for context extraction
                        if result.metadata.get('content_list'):
                            task.metadata['content_list'] = result.metadata['content_list']
                        
                        # Use language detected from the full document
                        if result.metadata.get('detected_language'):
                            # Store document-level language from API result
                            if task.src_fileid not in self.document_languages:
                                self.document_languages[task.src_fileid] = result.metadata['detected_language']
                                self.logger.info(f"Parser: using document language from API: {result.metadata['detected_language']} for {task.src_fileid[:8]}...")
                        else:
                            # Fallback: detect language from content if available
                            if task.content and task.content.strip():
                                from .language_detector import LanguageDetector
                                language_code, confidence = LanguageDetector.detect_language(task.content)
                                if confidence > 0.7:
                                    # Store document-level language
                                    if task.src_fileid not in self.document_languages:
                                        self.document_languages[task.src_fileid] = language_code
                                        self.logger.info(f"Parser: detected document language (fallback): {language_code} for {task.src_fileid[:8]}...")
                        
                        # Send to next stages (task already contains upload_callback and upload_options)
                        if task.content:
                            self.queues.content_refinement_queue.put(task)
                        else:
                            # No content, set refined_content to empty
                            task.refined_content = ''
                            
                        if task.images:
                            self.queues.image_recognition_queue.put(task)
                        else:
                            # No images to process
                            task.metadata['images_processed'] = True
                            
                        # If page has neither content nor images, mark as complete
                        if not task.content and not task.images:
                            task.refined_content = ''
                            self._check_task_completion(task)
                            
                        self.logger.info(f"Parser completed page {task.page_idx + 1}")
                            
                    except Exception as e:
                        # Page-level task retry (for handling queue/processing failures, not API failures)
                        # Note: Batch API calls don't retry, they fallback to single-page processing
                        # Single-page API calls have their own retry logic in api_client._retry_with_backoff
                        task.retry_count += 1
                        
                        if task.retry_count <= task.max_retries:
                            self.logger.warning(f"Parser task failed for page {task.page_idx + 1} (attempt {task.retry_count}/{task.max_retries}): {e}")
                            # Put the task back in the queue for retry
                            with self.tasks_lock:
                                task.status = TaskStatus.PENDING
                                task.error = f"Task retry {task.retry_count}: {str(e)}"
                            
                            # Add exponential backoff delay
                            retry_delay = min(2.0 * (2 ** (task.retry_count - 1)), 30.0)
                            await asyncio.sleep(retry_delay)
                            
                            # Re-queue the task for retry
                            self.queues.parsing_queue.put(task)
                            self.logger.info(f"Re-queued page {task.page_idx + 1} task for retry after {retry_delay:.1f}s delay")
                        else:
                            # Max retries exceeded, mark as failed
                            self.logger.error(f"Parser task failed for page {task.page_idx + 1} after {task.max_retries} retries: {e}")
                            with self.tasks_lock:
                                task.status = TaskStatus.FAILED
                                task.error = f"Task failed after {task.max_retries} retries: {str(e)}"
                            self._mark_task_completed(task)
                        
                    finally:
                        self.queues.parsing_queue.task_done()
                        
                        # Clean up cached results for completed documents
                        # Check if all pages for this document are processed
                        with self.tasks_lock:
                            if task.src_fileid in self.document_tasks:
                                doc_tasks = self.document_tasks[task.src_fileid]
                                all_processed = all(
                                    t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] 
                                    for t in doc_tasks.values()
                                )
                                if all_processed:
                                    # All pages processed, clean up cache
                                    if task.src_fileid in document_batch_results:
                                        del document_batch_results[task.src_fileid]
                                        self.logger.info(f"Parser: cleaned up cached batch results for document {task.src_fileid[:8]}...")
                                    if task.src_fileid in document_batch_info:
                                        del document_batch_info[task.src_fileid]
                        
                except Exception as e:
                    self.logger.error(f"Parsing worker error: {e}")
                    
        self.logger.info("Parsing worker stopped")
        
    async def _content_refinement_worker(self):
        """
        Content refinement worker thread.
        
        Consumes: PageTask from content_refinement_queue
        Updates: PageTask with refined content
        """
        self.logger.info("Content refinement worker started")
        
        while not self.shutdown_event.is_set():
            try:
                # Get task from queue
                try:
                    task = self.queues.content_refinement_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                    
                # Set trace context for this task with page number
                if self.platform_adapter:
                    self.platform_adapter.set_trace_id(f"{task.src_fileid}_p{task.page_idx + 1}")
                
                self.logger.info(f"Refiner processing page {task.page_idx + 1}")
                
                try:
                    # Get document language
                    language_code = self.document_languages.get(task.src_fileid)
                    
                    # Process content refinement for single page
                    page_result = await self.content_processor.process_page_content(
                        task.content, task.images, task.pdf_path, task.page_idx,
                        task.temp_dir, task.src_fileid, self.learn_type, language_code
                    )
                    
                    # Extract results
                    task.refined_content = page_result['content']
                    task.metadata['has_tables'] = page_result['has_tables']
                    task.metadata['content_processing'] = page_result.get('processing_metadata', {})
                    
                    self.logger.info(f"Refiner completed page {task.page_idx + 1}")
                        
                    # Check if this task is complete
                    self._check_task_completion(task)
                    
                except Exception as e:
                    self.logger.error(f"Refiner failed for page {task.page_idx + 1}: {e}")
                    task.refined_content = task.content  # Fallback
                    self._check_task_completion(task)
                    
                finally:
                    self.queues.content_refinement_queue.task_done()
            except Exception as e:
                self.logger.error(f"Content refinement worker error: {e}")
                
        self.logger.info("Content refinement worker stopped")
        
    async def _image_recognition_worker(self):
        """
        Image recognition worker thread.
        
        Consumes: PageTask from image_recognition_queue
        Produces: PageTask to image_upload_queue
        """
        self.logger.info("Image recognition worker started")
        
        try:
            while not self.shutdown_event.is_set():
                try:
                    # Get task from queue
                    try:
                        task = self.queues.image_recognition_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue
                        
                    # Set trace context for this task with page number
                    if self.platform_adapter:
                        self.platform_adapter.set_trace_id(f"{task.src_fileid}_p{task.page_idx + 1}")
                    
                    self.logger.info(f"Recognizer processing {len(task.images)} images for page {task.page_idx + 1}")
                    
                    try:
                        self.logger.info(f"Recognizer: loading images from {task.temp_dir}")
                        
                        # Create wrapper for classification without upload
                        async def classify_only(learn_type, image_filepath, temp_dir, src_name, hint=""):
                            # Use document-level language directly
                            language_code = self.document_languages.get(task.src_fileid)
                            if language_code:
                                self.logger.info(f"Recognizer: using document language: {language_code} for page {task.page_idx + 1}")
                            else:
                                self.logger.info(f"Recognizer: no document language detected for {task.src_fileid[:8]}")
                            
                            # Extract context for the image if content is available
                            context = None
                            if task.content:
                                try:
                                    # Extract the filename from filepath
                                    import os
                                    import re
                                    filename = os.path.basename(image_filepath)
                                    
                                    # Create ImageContext from page content
                                    from .context_types import ImageContext
                                    
                                    # Try to find image reference in content
                                    # Look for patterns like ![...](filename) or just the filename
                                    surrounding_text = ""
                                    before_text = ""
                                    after_text = ""
                                    
                                    # Extract base name without extension for more flexible matching
                                    base_name = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '')
                                    
                                    # Try different patterns to find the image reference
                                    patterns = [
                                        rf'!\[.*?\]\([^)]*{re.escape(filename)}[^)]*\)',  # Full filename in markdown
                                        rf'!\[.*?\]\([^)]*{re.escape(base_name)}[^)]*\)',  # Base name in markdown
                                        rf'{re.escape(filename)}',  # Just the filename
                                        rf'{re.escape(base_name)}'   # Just the base name
                                    ]
                                    
                                    image_position = -1
                                    for pattern in patterns:
                                        match = re.search(pattern, task.content)
                                        if match:
                                            image_position = match.start()
                                            self.logger.debug(f"Found image reference at position {image_position} using pattern: {pattern}")
                                            break
                                    
                                    if image_position >= 0:
                                        # Extract 250 characters before and after the image reference
                                        start_pos = max(0, image_position - 250)
                                        end_pos = min(len(task.content), image_position + 250)
                                        
                                        before_text = task.content[start_pos:image_position].strip()
                                        after_text = task.content[image_position:end_pos].strip()
                                        surrounding_text = task.content[start_pos:end_pos].strip()
                                        
                                        self.logger.info(f"Recognizer: found image {filename} at position {image_position}, "
                                                       f"extracted {len(before_text)} chars before and {len(after_text)} chars after")
                                    else:
                                        # Fallback: if image reference not found, use first 500 chars of content
                                        surrounding_text = task.content[:500] if len(task.content) > 500 else task.content
                                        self.logger.warning(f"Recognizer: could not find image reference for {filename}, using fallback context")
                                    
                                    context = ImageContext(
                                        page_idx=task.page_idx,
                                        surrounding_text=surrounding_text,
                                        page_type='content',  # Could be enhanced to detect actual page type
                                        token_count=len(surrounding_text) // 4,  # Rough token estimate
                                        before_text=before_text,
                                        after_text=after_text
                                    )
                                    
                                    self.logger.info(f"Recognizer: created context for image {filename} with {len(surrounding_text)} chars of surrounding text")
                                except Exception as e:
                                    self.logger.warning(f"Recognizer: failed to create context for image: {e}")
                                    context = None
                            
                            # Use the image processor's classification method with context
                            return await self.image_processor._classify_single_image_with_context(
                                learn_type, image_filepath, temp_dir, src_name, hint, context, language_code
                            )
                        
                        # Load and classify images
                        images_to_process = []
                        for img_filename in task.images:
                            img_filepath = os.path.join(task.temp_dir, img_filename)
                            self.logger.info(f"Recognizer: checking image {img_filename} at {img_filepath}")
                            if os.path.exists(img_filepath):
                                xref = img_filename.replace('.png', '').replace('mineru_image_', '')
                                self.logger.info(f"Recognizer: loading image info for {img_filename}, xref={xref}")
                                image_info = await self.image_processor.image_optimizer.load_image_info(
                                    img_filepath, img_filename, xref
                                )
                                images_to_process.append(image_info)
                                self.logger.info(f"Recognizer: loaded image info: {image_info}")
                            else:
                                self.logger.warning(f"Recognizer: image file not found: {img_filepath}")
                                
                        if images_to_process:
                            # Classify images sequentially (not concurrently) to avoid pressure on multimodal service
                            self.logger.info(f"Recognizer: classifying {len(images_to_process)} images sequentially for page {task.page_idx + 1}")
                            classification_results = await self.image_processor.image_optimizer.batch_classify_images(
                                images_to_process, classify_only, self.learn_type,
                                task.temp_dir, task.src_fileid
                            )
                            
                            # Filter meaningful images based on configuration
                            meaningful_images = []
                            for image_info in images_to_process:
                                xref = image_info.xref
                                if xref in classification_results:
                                    result = classification_results[xref]
                                    
                                    # Apply meaningless filter if configured
                                    if self.config.filter_meaningless_images and result.get('type') == 'meaningless':
                                        self.logger.info(f"Recognizer: filtering out meaningless image {image_info.filename}")
                                        # Still store the classification for reference
                                        task.image_descriptions[image_info.filename] = result
                                    else:
                                        # Either filter is disabled or image is meaningful
                                        meaningful_images.append(image_info)
                                        task.image_descriptions[image_info.filename] = result
                                        
                            # Send to upload queue if there are images to upload
                            # Note: if filter is disabled, we upload all classified images including meaningless ones
                            if meaningful_images or (not self.config.filter_meaningless_images and images_to_process):
                                if not self.config.filter_meaningless_images:
                                    # If filter is disabled, upload all processed images
                                    task.meaningful_images = images_to_process
                                else:
                                    # If filter is enabled, only upload meaningful images
                                    task.meaningful_images = meaningful_images
                                self.queues.image_upload_queue.put(task)
                            else:
                                # No images to upload
                                task.metadata['images_processed'] = True
                                self._check_task_completion(task)
                                
                            self.logger.info(f"Recognizer completed page {task.page_idx + 1}: "
                                           f"{len(meaningful_images)}/{len(task.images)} meaningful")
                        else:
                            task.metadata['images_processed'] = True
                            self._check_task_completion(task)
                            
                    except Exception as e:
                        self.logger.error(f"Recognizer failed for page {task.page_idx + 1}: {e}")
                        import traceback
                        self.logger.error(f"Recognizer traceback: {traceback.format_exc()}")
                        task.metadata['images_processed'] = True  # Mark as processed to avoid hanging
                        self._check_task_completion(task)
                        
                    finally:
                        self.queues.image_recognition_queue.task_done()
                        
                except Exception as e:
                    self.logger.error(f"Image recognition worker inner error: {e}")
                    import traceback
                    self.logger.error(f"Image recognition worker traceback: {traceback.format_exc()}")
        
        except Exception as e:
            self.logger.error(f"Image recognition worker error: {e}")
        finally:
            self.logger.info("Image recognition worker stopped")
        
    async def _image_upload_worker(self):
        """
        Image upload worker thread.
        
        Consumes: PageTask from image_upload_queue
        Updates: PageTask with uploaded image URLs
        """
        self.logger.info("Image upload worker started")
        
        while not self.shutdown_event.is_set():
            try:
                # Get task from queue
                try:
                    task = self.queues.image_upload_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                    
                # Set trace context for this task with page number
                if self.platform_adapter:
                    self.platform_adapter.set_trace_id(f"{task.src_fileid}_p{task.page_idx + 1}")
                
                meaningful_images = task.meaningful_images
                self.logger.info(f"Uploader processing {len(meaningful_images)} images for page {task.page_idx + 1}")
                
                try:
                    if meaningful_images:
                        # Get upload callback and options from task
                        upload_callback = task.upload_callback
                        upload_options = task.upload_options
                        
                        self.logger.info(f"Uploader: starting upload for {len(meaningful_images)} images on page {task.page_idx + 1}")
                        
                        if upload_callback:
                            # Batch upload images
                            upload_results = await self.image_processor.image_optimizer.batch_upload_images(
                                meaningful_images, upload_callback, upload_options
                            )
                            
                            self.logger.info(f"Uploader: upload_results keys: {list(upload_results.keys())}")
                            
                            # Map results back to filenames
                            for image_info in meaningful_images:
                                xref = image_info.xref
                                if xref in upload_results and upload_results[xref]:
                                    task.processed_images[image_info.filename] = upload_results[xref]
                                    self.logger.info(f"Uploader: mapped {image_info.filename} -> {upload_results[xref]}")
                                else:
                                    self.logger.warning(f"Uploader: no upload result for {image_info.filename} (xref={xref})")
                                    
                            self.logger.info(f"Uploader completed page {task.page_idx + 1}: "
                                           f"{len(task.processed_images)} uploaded")
                        else:
                            self.logger.warning(f"Uploader: no upload_callback provided for page {task.page_idx + 1}")
                    
                    # Mark images as processed
                    task.metadata['images_processed'] = True
                                           
                    # Mark task as complete
                    self._check_task_completion(task)
                    
                except Exception as e:
                    self.logger.error(f"Uploader failed for page {task.page_idx + 1}: {e}")
                    self._check_task_completion(task)
                    
                finally:
                    self.queues.image_upload_queue.task_done()
                    
            except Exception as e:
                self.logger.error(f"Image upload worker error: {e}")
                
        self.logger.info("Image upload worker stopped")
        
    async def _split_pdf_batch(self, pdf_path: str, temp_dir: str, start_page: int, 
                              end_page: int, batch_idx: int) -> str:
        """
        Split PDF to extract specific pages for batch processing.
        
        Args:
            pdf_path: Original PDF path
            temp_dir: Temporary directory
            start_page: Start page index (0-based)
            end_page: End page index (exclusive)
            batch_idx: Batch index for naming
            
        Returns:
            Path to the split PDF file
        """
        import fitz
        batch_pdf_path = os.path.join(temp_dir, f"batch_{batch_idx}.pdf")
        
        with fitz.open(pdf_path) as src_doc:
            batch_doc = fitz.open()  # Create new PDF
            
            # Copy pages to new document
            for page_idx in range(start_page, end_page):
                batch_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)
            
            batch_doc.save(batch_pdf_path)
            batch_doc.close()
        
        self.logger.info(f"Created batch PDF with {end_page - start_page} pages: {batch_pdf_path}")
        return batch_pdf_path
    
    async def _process_batch_as_single_pages(self, task: PageTask, api_client: MinerUAPIClient,
                                            batch_start: int, batch_end: int, batch_idx: int) -> MinerUResult:
        """
        Process a failed batch by trying each page individually.
        This helps identify which specific page is causing the batch to fail.
        
        Args:
            task: The current page task
            api_client: MinerU API client
            batch_start: Start page index of the batch
            batch_end: End page index of the batch  
            batch_idx: Batch index
            
        Returns:
            MinerUResult with combined results from successful pages
        """
        self.logger.info(f"Starting single-page processing for failed batch {batch_idx + 1} (pages {batch_start + 1}-{batch_end})")
        
        successful_pages = []
        failed_pages = []
        all_content_parts = []
        all_images = []
        all_tables = []
        page_data = {}
        
        # Try each page individually
        for page_idx in range(batch_start, batch_end):
            try:
                self.logger.info(f"Processing single page {page_idx + 1}/{batch_end}")
                
                # Create single-page PDF
                single_page_pdf = os.path.join(task.temp_dir, f"single_page_{page_idx}.pdf")
                
                import fitz
                with fitz.open(task.pdf_path) as src_doc:
                    single_doc = fitz.open()
                    single_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)
                    single_doc.save(single_page_pdf)
                    single_doc.close()
                
                # Process single page WITH retry logic
                if self.config.mineru_api_type == "self_hosted":
                    # Use retry wrapper for single-page processing
                    page_result = await api_client._retry_with_backoff(
                        api_client._process_batch_self_hosted_impl,
                        single_page_pdf, task.temp_dir, task.src_fileid,
                        page_idx, page_idx, page_idx + 1,
                        task.metadata.get('is_ppt_format', False)
                    )
                else:
                    # Use retry wrapper for single-page processing
                    page_result = await api_client._retry_with_backoff(
                        api_client._process_batch_cloud_impl,
                        single_page_pdf, task.temp_dir, task.src_fileid,
                        page_idx, page_idx, page_idx + 1,
                        task.metadata.get('is_ppt_format', False)
                    )
                
                # Clean up single-page PDF
                if os.path.exists(single_page_pdf):
                    os.remove(single_page_pdf)
                
                if page_result.success:
                    successful_pages.append(page_idx + 1)
                    all_content_parts.append(page_result.content)
                    all_images.extend(page_result.images)
                    all_tables.extend(page_result.tables)
                    page_data[page_idx] = {
                        'content': page_result.content,
                        'images': page_result.images,
                        'tables': page_result.tables,
                        'metadata': page_result.metadata
                    }
                    self.logger.success(f"✓ Page {page_idx + 1} processed successfully")
                else:
                    failed_pages.append(page_idx + 1)
                    self.logger.error(f"✗ Page {page_idx + 1} failed: {page_result.error}")
                    # Add empty data for failed page
                    page_data[page_idx] = {
                        'content': '',
                        'images': [],
                        'tables': [],
                        'metadata': {'error': page_result.error, 'failed': True}
                    }
                    
            except Exception as e:
                failed_pages.append(page_idx + 1)
                self.logger.error(f"✗ Page {page_idx + 1} processing error: {str(e)}")
                # Add empty data for failed page
                page_data[page_idx] = {
                    'content': '',
                    'images': [],
                    'tables': [],
                    'metadata': {'error': str(e), 'failed': True}
                }
        
        # Log summary
        self.logger.info(f"Single-page processing complete for batch {batch_idx + 1}:")
        self.logger.info(f"  - Successful pages: {successful_pages} ({len(successful_pages)}/{batch_end - batch_start})")
        if failed_pages:
            self.logger.warning(f"  - Failed pages: {failed_pages} ({len(failed_pages)}/{batch_end - batch_start})")
        
        # Return combined result
        success = len(successful_pages) > 0  # Partial success if at least one page worked
        
        metadata = {
            "batch_idx": batch_idx,
            "start_page": batch_start,
            "end_page": batch_end,
            "pages_in_batch": batch_end - batch_start,
            "successful_pages": successful_pages,
            "failed_pages": failed_pages,
            "single_page_fallback": True,
            "page_data": page_data
        }
        
        return MinerUResult(
            success=success,
            content="\n\n".join(all_content_parts),
            images=all_images,
            tables=all_tables,
            metadata=metadata,
            error=f"Failed pages: {failed_pages}" if failed_pages else None
        )
    
    def _extract_page_data(self, mineru_result, page_idx: int) -> Dict:
        """Extract data for a specific page from MinerU result"""
        # Check if we have pre-split page data
        if mineru_result.metadata.get('page_data'):
            page_data = mineru_result.metadata['page_data']
            self.logger.debug(f"Found page_data with keys: {list(page_data.keys())}")
            
            # Try both integer and string keys
            if page_idx in page_data:
                self.logger.debug(f"Found data for page_idx {page_idx} (int key)")
                return {
                    'content': page_data[page_idx].get('content', ''),
                    'images': page_data[page_idx].get('images', []),
                    'metadata': page_data[page_idx].get('metadata', {})
                }
            elif str(page_idx) in page_data:
                self.logger.debug(f"Found data for page_idx {page_idx} (str key)")
                return {
                    'content': page_data[str(page_idx)].get('content', ''),
                    'images': page_data[str(page_idx)].get('images', []),
                    'metadata': page_data[str(page_idx)].get('metadata', {})
                }
            else:
                self.logger.warning(f"No data found for page_idx {page_idx} in page_data")
        
        # Fallback: split content by page markers
        content_parts = mineru_result.content.split(f'__PAGE_OF_PORTION_{page_idx + 1}__')
        if len(content_parts) > 1:
            # Get content after the page marker until next marker
            page_content = content_parts[1].split(f'__PAGE_OF_PORTION_{page_idx + 2}__')[0]
        else:
            # If no page markers, return empty
            page_content = ''
        
        # Filter images by page (assuming images have page info in metadata)
        page_images = []
        
        # For single-page documents, assign all images to page 0
        total_pages = len(mineru_result.metadata.get('page_data', {}))
        if total_pages == 1 and page_idx == 0:
            # Single page document - assign all images to this page
            page_images = list(mineru_result.images)
            self.logger.debug(f"Single-page document: assigning {len(page_images)} images to page 0")
        else:
            # Multi-page document - filter by page markers
            for img in mineru_result.images:
                # This is a simplified version - real implementation would check image metadata
                if f'page_{page_idx}' in img or f'p{page_idx}' in img:
                    page_images.append(img)
        
        # Handle page content - ensure empty/whitespace pages are properly handled
        stripped_content = page_content.strip()
        
        # Log if we have a page with only whitespace
        if page_content and not stripped_content:
            self.logger.debug(f"Page {page_idx} contains only whitespace characters")
        
        return {
            'content': stripped_content,
            'images': page_images,
            'metadata': mineru_result.metadata
        }
        
    def _check_task_completion(self, task: PageTask):
        """Check if a task is complete and mark it accordingly"""
        should_mark_complete = False
        
        with self.tasks_lock:
            # Skip if already completed
            if task.status == TaskStatus.COMPLETED:
                self.logger.debug(f"Page {task.page_idx + 1} already completed, skipping")
                return
                
            # A task is complete when:
            # 1. Content is refined (or original content is used)
            # 2. Images are processed (or there are no images)
            has_content = task.refined_content is not None
            has_no_images = not task.images
            has_processed_images = len(task.images) == 0 or task.metadata.get('images_processed', False)
            
            # Log the current state for debugging
            self.logger.debug(f"Checking completion for page {task.page_idx + 1}: "
                            f"has_content={has_content}, has_no_images={has_no_images}, "
                            f"has_processed_images={has_processed_images}, "
                            f"images_count={len(task.images)}")
            
            if has_content and (has_no_images or has_processed_images):
                # Integrate image descriptions into content before marking complete
                if task.processed_images and task.image_descriptions:
                    self.logger.info(f"Page {task.page_idx + 1} ready for image integration:")
                    self.logger.info(f"  - processed_images: {list(task.processed_images.keys())}")
                    self.logger.info(f"  - image_descriptions: {list(task.image_descriptions.keys())}")
                    self.logger.info(f"  - content length before: {len(task.refined_content)} chars")
                    
                    task.refined_content = self._integrate_images_into_content(
                        task.refined_content,
                        task.image_descriptions,
                        task.processed_images,
                        f"{task.src_fileid}_page_{task.page_idx}"
                    )
                    
                    self.logger.info(f"  - content length after: {len(task.refined_content)} chars")
                else:
                    self.logger.info(f"Page {task.page_idx + 1} has no images to integrate: "
                                   f"processed_images={bool(task.processed_images)}, "
                                   f"image_descriptions={bool(task.image_descriptions)}")
                
                task.status = TaskStatus.COMPLETED
                should_mark_complete = True
        
        # Call _mark_task_completed outside of the lock to avoid deadlock
        if should_mark_complete:
            self._mark_task_completed(task)
    
    def _integrate_images_into_content(self, content: str, image_descriptions: Dict[str, Dict],
                                     uploaded_images: Dict[str, str], _page_identifier: str) -> str:
        """
        Integrate image descriptions into content by replacing original image references.
        
        This method is adapted from image_processor.integrate_image_descriptions
        """
        import re
        
        try:
            enhanced_content = content
            
            # Log what we're processing
            self.logger.info(f"Image integration starting for {_page_identifier}:")
            self.logger.info(f"  - Image descriptions: {list(image_descriptions.keys())}")
            self.logger.info(f"  - Uploaded images: {list(uploaded_images.keys())}")
            self.logger.debug(f"  - Content length: {len(content)} chars")
            
            # First, find all image references in the content
            image_pattern = r'!\[.*?\]\((.*?)\)'
            content_images = re.findall(image_pattern, content)
            self.logger.info(f"Found {len(content_images)} image references in content:")
            for img_ref in content_images[:5]:  # Log first 5
                self.logger.info(f"  - {img_ref}")
            
            # Process each image description
            for filename, desc_info in image_descriptions.items():
                self.logger.info(f"\nChecking image {filename} for replacement")
                if filename in uploaded_images:
                    uploaded_url = uploaded_images[filename]
                    self.logger.info(f"  - Found in uploaded_images: {uploaded_url}")
                    
                    # Extract the hash part from the filename
                    # This handles filenames like: 390561cb34fd3f951b1d25a252bead1c_page_1_44450601...jpg
                    # or mineru_image_xxx.png
                    base_filename = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '')
                    
                    # Try to extract the hash part (usually the long hex string)
                    # For mineru images: mineru_image_XXX -> XXX
                    # For hash-based: XXX_page_N_YYY -> YYY (the last hash)
                    if 'mineru_image_' in filename:
                        ref = base_filename.replace('mineru_image_', '')
                    else:
                        # Look for the last hash-like pattern
                        parts = base_filename.split('_')
                        # Find the longest hex-like string
                        hash_parts = [p for p in parts if len(p) > 20 and all(c in '0123456789abcdef' for c in p)]
                        if hash_parts:
                            ref = hash_parts[-1]  # Use the last hash
                        else:
                            ref = base_filename
                    
                    # Build replacement content based on image type
                    img_type = desc_info.get('type', 'brief_description')
                    title = desc_info.get('title', '')
                    description = desc_info.get('content', '')
                    ocr_content = desc_info.get('ocr_content', '')
                    
                    # Create the replacement markdown
                    if img_type == 'meaningless':
                        # Skip meaningless images
                        continue
                    elif img_type == 'structured_content':
                        # For structured content, include full description
                        replacement = f"\n\n![{title}]({uploaded_url})\n<!--{description}-->\n\n{ocr_content}\n\n"
                    else:
                        # For other types, use a simpler format
                        if description:
                            replacement = f"\n\n![{title}]({uploaded_url})\n<!--{description}-->\n"
                        else:
                            replacement = f"\n\n![{title}]({uploaded_url})\n\n"
                    
                    # Replace various possible image reference patterns
                    # We need to be flexible because the reference in content might be different from our filename
                    patterns = []
                    
                    # If we found a hash reference, try to match it in various formats
                    if ref and len(ref) > 20:  # Likely a hash
                        patterns.extend([
                            f"!\\[.*?\\]\\(.*?{ref}.*?\\)",         # Match hash anywhere in path
                            f"!\\[\\]\\(.*?{ref}.*?\\)",            # Empty alt text with hash
                            f"!\\[.*?\\]\\(images/{ref}\\.[^)]+\\)", # images/hash.ext
                            f"!\\[\\]\\(images/{ref}\\.[^)]+\\)",    # images/hash.ext with empty alt
                        ])
                    
                    # Always try the full filename patterns
                    patterns.extend([
                        f"!\\[.*?\\]\\(.*?{re.escape(filename)}\\)",        # Match exact filename
                        f"!\\[.*?\\]\\(.*?{re.escape(base_filename)}\\)",   # Match base filename
                    ])
                    
                    # Add generic mineru image pattern if applicable
                    if 'mineru_image_' in filename:
                        patterns.append(f"!\\[.*?\\]\\(.*?{filename}\\)")
                        
                    self.logger.info(f"  - extracted ref: '{ref}'")
                    self.logger.info(f"  - trying {len(patterns)} patterns")
                    
                    replaced = False
                    for pattern in patterns:
                        new_content = re.sub(pattern, replacement, enhanced_content)
                        if new_content != enhanced_content:
                            enhanced_content = new_content
                            replaced = True
                            self.logger.info(f"Successfully replaced image {filename} using pattern: {pattern}")
                            break
                    
                    if not replaced:
                        self.logger.warning(f"Failed to replace image reference for: {filename}, ref={ref}")
                        # Log the first few characters of content to help debugging
                        sample = enhanced_content[:500] if len(enhanced_content) > 500 else enhanced_content
                        self.logger.info(f"Content sample: {sample}...")
                        # Also log the exact patterns we tried
                        self.logger.info(f"Tried patterns:")
                        for p in patterns:
                            self.logger.info(f"  - {p}")
                else:
                    self.logger.warning(f"Image {filename} not found in uploaded_images!")
                        
            return enhanced_content
            
        except Exception as e:
            self.logger.error(f"Error integrating images: {str(e)}")
            return content  # Return original content on error
                
    def _mark_task_completed(self, task: PageTask):
        """Mark a task as completed and add to results"""
        self.logger.debug(f"Marking task as completed: page {task.page_idx + 1}, status={task.status}, "
                        f"src_fileid={task.src_fileid[:8]}...")
        
        # Get total pages first (outside of completed_lock to avoid potential deadlock)
        with self.tasks_lock:
            doc_tasks = self.document_tasks.get(task.src_fileid, {})
            total_pages = len(doc_tasks)
        
        try:
            # Save to cache if callback provided and task succeeded
            if task.status == TaskStatus.COMPLETED:
                save_callback = task.save_callback  # Get from non-serializable field
                if save_callback:
                    try:
                        # Prepare page data for caching
                        page_data = {
                            'content': task.refined_content or task.content or '',
                            'images': task.images,
                            'processed_images': task.processed_images,
                            'image_descriptions': task.image_descriptions,
                            'has_tables': task.metadata.get('has_tables', False),
                            'processing_metadata': {k: v for k, v in task.metadata.items() 
                                                  if k not in ['save_callback', 'upload_callback']}
                        }
                        save_callback(task.page_idx, page_data)
                        self.logger.debug(f"Saved page {task.page_idx + 1} to cache")
                    except Exception as e:
                        self.logger.error(f"Failed to save page {task.page_idx + 1} to cache: {e}")
            
            with self.completed_lock:
                self.logger.debug(f"Acquired completed_lock for marking task")
                # Initialize list for this document if needed
                if task.src_fileid not in self.document_completed_tasks:
                    self.document_completed_tasks[task.src_fileid] = []
                    self.logger.debug(f"Initialized completed tasks list for doc {task.src_fileid[:8]}")
                
                self.document_completed_tasks[task.src_fileid].append(task)
                completed_count = len(self.document_completed_tasks[task.src_fileid])
                self.logger.debug(f"Added task to completed list, count now: {completed_count}")
                
            self.logger.info(f"Task completed: page {task.page_idx + 1} "
                           f"[{completed_count}/{total_pages}] for doc {task.src_fileid[:8]}...")
        except Exception as e:
            self.logger.error(f"Error in _mark_task_completed: {e}", exc_info=True)
            
    async def process_document_with_cache(self, pdf_path: str, temp_dir: str, src_fileid: str,
                                        is_ppt_format: bool, total_pages: int,
                                        upload_callback=None, upload_options=None,
                                        cached_pages=None, save_callback=None) -> List[PageTask]:
        """
        Process a document using parallel pipeline with cache support.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory
            src_fileid: Source file ID
            is_ppt_format: Whether document is in PPT format
            total_pages: Total number of pages
            upload_callback: Callback for uploading images
            upload_options: Upload options
            cached_pages: Dictionary of already cached pages {page_idx: page_data}
            save_callback: Callback to save page to cache when completed
            
        Returns:
            List of completed PageTask objects
        """
        # Process with cache support
        return await self._process_document_internal(
            pdf_path, temp_dir, src_fileid, is_ppt_format, total_pages,
            upload_callback, upload_options, cached_pages, save_callback
        )
    
    async def process_document(self, pdf_path: str, temp_dir: str, src_fileid: str,
                             is_ppt_format: bool, total_pages: int,
                             upload_callback=None, upload_options=None) -> List[PageTask]:
        """
        Process a document using parallel pipeline.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory
            src_fileid: Source file ID
            is_ppt_format: Whether document is in PPT format
            total_pages: Total number of pages
            upload_callback: Image upload callback
            upload_options: Upload options
            
        Returns:
            List of completed PageTask objects
        """
        # Process without cache support
        return await self._process_document_internal(
            pdf_path, temp_dir, src_fileid, is_ppt_format, total_pages,
            upload_callback, upload_options, None, None
        )
    
    async def _process_document_internal(self, pdf_path: str, temp_dir: str, src_fileid: str,
                                       is_ppt_format: bool, total_pages: int,
                                       upload_callback=None, upload_options=None,
                                       cached_pages=None, save_callback=None) -> List[PageTask]:
        """
        Internal method to process document with optional cache support.
        """
        cached_pages = cached_pages or {}
        self.logger.info(f"Starting parallel processing for {total_pages} pages, {len(cached_pages)} already cached")
        
        # Initialize async components
        await self.initialize()
        
        # Initialize threads if not already running
        if not self.threads:
            self.initialize_threads()
            # Start queue monitor
            self._start_queue_monitor()
        
        # Initialize document-specific tracking
        with self.tasks_lock:
            self.document_tasks[src_fileid] = {}
        with self.completed_lock:
            self.document_completed_tasks[src_fileid] = []
            
        # Create tasks for each page
        for page_idx in range(total_pages):
            # Check if page is already cached
            if page_idx in cached_pages:
                # Create a completed task from cached data
                cached_data = cached_pages[page_idx]
                task = PageTask(
                    page_idx=page_idx,
                    pdf_path=pdf_path,
                    temp_dir=temp_dir,
                    src_fileid=src_fileid,
                    status=TaskStatus.COMPLETED,
                    content=cached_data.get('content', ''),
                    images=cached_data.get('metadata', {}).get('images', []),
                    refined_content=cached_data.get('content', ''),  # Use cached content as refined
                    processed_images=cached_data.get('metadata', {}).get('processed_images', {}),
                    image_descriptions=cached_data.get('metadata', {}).get('image_descriptions', {}),
                    metadata=cached_data.get('metadata', {}),
                    max_retries=self.config.api_max_retries  # Use retry config from settings
                )
                with self.tasks_lock:
                    self.document_tasks[src_fileid][page_idx] = task
                with self.completed_lock:
                    self.document_completed_tasks[src_fileid].append(task)
                self.logger.info(f"Loaded page {page_idx + 1} from cache")
            else:
                # Create new task for processing
                task = PageTask(
                    page_idx=page_idx,
                    pdf_path=pdf_path,
                    temp_dir=temp_dir,
                    src_fileid=src_fileid,
                    metadata={
                        'is_ppt_format': is_ppt_format
                    },
                    upload_callback=upload_callback,
                    upload_options=upload_options,
                    save_callback=save_callback,  # Store as non-serializable field
                    max_retries=self.config.api_max_retries  # Use retry config from settings
                )
                with self.tasks_lock:
                    self.document_tasks[src_fileid][page_idx] = task
                self.queues.parsing_queue.put(task)
            
        # Wait for all tasks to complete for this document
        start_time = time.time()
        self.logger.info(f"Waiting for {total_pages} pages to complete for document {src_fileid[:8]}...")
        
        while True:
            with self.completed_lock:
                # Debug: log the src_fileid we're looking for
                self.logger.debug(f"Looking for src_fileid: {src_fileid}")
                completed_tasks_for_doc = self.document_completed_tasks.get(src_fileid, [])
                completed_count = len(completed_tasks_for_doc)
                
                # Debug: log the actual keys in document_completed_tasks
                available_docs = list(self.document_completed_tasks.keys())
                if len(available_docs) > 0:
                    # Show full keys for debugging
                    self.logger.debug(f"Looking for: {src_fileid}")
                    self.logger.debug(f"Available docs: {available_docs}")
                    self.logger.debug(f"Tasks for this doc: {completed_count}")
            
            # Log progress every few iterations
            if int(time.time() - start_time) % 5 == 0:
                self.logger.info(f"Progress: {completed_count}/{total_pages} pages completed")
            
            if completed_count >= total_pages:
                self.logger.info(f"All {total_pages} pages completed!")
                break
                
            # Check for timeout
            if time.time() - start_time > self.config.processing_timeout:
                self.logger.error(f"Processing timeout reached after {self.config.processing_timeout}s")
                self.logger.error(f"Only {completed_count}/{total_pages} pages completed")
                break
                
            await asyncio.sleep(0.5)
                
        self.logger.info(f"Parallel processing completed in {time.time() - start_time:.2f}s")
        
        # Get and sort completed tasks for this document (with proper locking)
        with self.completed_lock:
            completed_tasks = list(self.document_completed_tasks.get(src_fileid, []))
            self.logger.info(f"Retrieved {len(completed_tasks)} completed tasks for document")
        
        completed_tasks.sort(key=lambda t: t.page_idx)
        
        # Log task details before cleanup
        try:
            for task in completed_tasks:
                self.logger.debug(f"Completed task: page {task.page_idx + 1}, "
                                f"has_content={bool(task.refined_content)}, "
                                f"images={len(task.processed_images)}")
        except Exception as e:
            self.logger.error(f"Error logging task details: {e}")
        
        # Clean up document-specific data
        with self.tasks_lock:
            if src_fileid in self.document_tasks:
                del self.document_tasks[src_fileid]
        with self.completed_lock:
            if src_fileid in self.document_completed_tasks:
                del self.document_completed_tasks[src_fileid]
        if src_fileid in self.document_languages:
            del self.document_languages[src_fileid]
        
        self.logger.info(f"Returning {len(completed_tasks)} completed tasks")
        return completed_tasks
    
    def _start_queue_monitor(self):
        """Start queue monitoring thread"""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._monitor_stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._queue_monitor_worker,
                name="MinerU-QueueMonitor",
                daemon=True
            )
            self._monitor_thread.start()
            self.logger.info("Queue monitor started")
    
    def _queue_monitor_worker(self):
        """Monitor queue sizes and log statistics"""
        while not self._monitor_stop_event.is_set():
            try:
                # Get queue sizes
                parsing_size = self.queues.parsing_queue.qsize()
                content_size = self.queues.content_refinement_queue.qsize()
                recognition_size = self.queues.image_recognition_queue.qsize()
                upload_size = self.queues.image_upload_queue.qsize()
                
                # Get active documents count
                with self.tasks_lock:
                    active_docs = len(self.document_tasks)
                    total_pending_tasks = sum(len(tasks) for tasks in self.document_tasks.values())
                
                with self.completed_lock:
                    total_completed = sum(len(tasks) for tasks in self.document_completed_tasks.values())
                
                # Log queue status only when there's activity
                if parsing_size > 0 or content_size > 0 or recognition_size > 0 or upload_size > 0 or active_docs > 0:
                    self.logger.info(
                        f"Queue Status | Parse: {parsing_size} | "
                        f"Refine: {content_size} | "
                        f"Recognize: {recognition_size} | "
                        f"Upload: {upload_size} | "
                        f"Docs: {active_docs} | "
                        f"Tasks: {total_pending_tasks}/{total_completed} (pending/completed)"
                    )
                
                # Sleep for monitoring interval
                time.sleep(5)  # Log every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Queue monitor error: {e}")
                time.sleep(5)
        
        self.logger.info("Queue monitor stopped")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get detailed queue status"""
        status = {
            'queues': {
                'parsing': {
                    'size': self.queues.parsing_queue.qsize(),
                    'max_size': self.queues.parsing_queue.maxsize
                },
                'content_refinement': {
                    'size': self.queues.content_refinement_queue.qsize(),
                    'max_size': self.queues.content_refinement_queue.maxsize
                },
                'image_recognition': {
                    'size': self.queues.image_recognition_queue.qsize(),
                    'max_size': self.queues.image_recognition_queue.maxsize
                },
                'image_upload': {
                    'size': self.queues.image_upload_queue.qsize(),
                    'max_size': self.queues.image_upload_queue.maxsize
                }
            },
            'documents': {},
            'threads': {
                'active': len([t for t in self.threads if t.is_alive()]),
                'total': len(self.threads)
            }
        }
        
        # Get per-document status
        with self.tasks_lock:
            for doc_id, tasks in self.document_tasks.items():
                doc_status = {
                    'total_pages': len(tasks),
                    'processing': 0,
                    'pending': 0
                }
                for task in tasks.values():
                    if task.status == TaskStatus.PROCESSING:
                        doc_status['processing'] += 1
                    elif task.status == TaskStatus.PENDING:
                        doc_status['pending'] += 1
                
                with self.completed_lock:
                    completed = len(self.document_completed_tasks.get(doc_id, []))
                    doc_status['completed'] = completed
                
                status['documents'][doc_id[:8] + '...'] = doc_status
        
        return status
        
    async def shutdown(self):
        """Shutdown all processing threads"""
        self.logger.info("Shutting down parallel processor...")
        
        # Signal shutdown
        self.shutdown_event.set()
        self._monitor_stop_event.set()
        
        # Wait for threads to complete
        for thread in self.threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                self.logger.warning(f"Thread {thread.name} did not stop gracefully")
        
        # Stop monitor thread
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        # Clear threads list
        self.threads.clear()
        
        # Cleanup async components
        if self._initialized:
            await self.image_processor.cleanup()
            self._initialized = False
        
        # Clear all document data
        with self.tasks_lock:
            self.document_tasks.clear()
        with self.completed_lock:
            self.document_completed_tasks.clear()
        self.document_languages.clear()
                
        self.logger.info("Parallel processor shutdown complete")


# Import required modules
import os