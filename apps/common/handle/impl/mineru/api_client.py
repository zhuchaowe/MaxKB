"""
MinerU API client module.

This module handles communication with the MinerU service for document parsing,
following the architecture patterns from gzero.py and implementing the real API.
"""

import os
import asyncio
import aiohttp
import zipfile
import fitz
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from .logger import get_module_logger
logger = get_module_logger('api_client')

from .config_base import MinerUConfig


@dataclass
class MinerUPageResult:
    """Result from MinerU processing for a single page"""
    page_idx: int
    success: bool
    content: str
    images: List[str]
    tables: List[Dict]
    metadata: Dict[str, Any]
    error: Optional[str] = None

@dataclass
class MinerUResult:
    """Result from MinerU processing"""
    success: bool
    content: str  # Backward compatibility - merged content
    images: List[str]  # All images
    tables: List[Dict]  # All tables
    metadata: Dict[str, Any]
    error: Optional[str] = None
    page_results: Optional[List[MinerUPageResult]] = None  # Individual page results


class MinerUAPIClient:
    """Client for interacting with MinerU API"""
    
    def __init__(self, config: MinerUConfig, platform_adapter=None):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logger
        self.platform_adapter = platform_adapter
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600)  # 10 minute timeout
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def process_document(self, pdf_path: str, temp_dir: str, src_fileid: str, 
                             is_ppt_converted: bool = False, batch_size: int = 20) -> MinerUResult:
        """
        Process document using MinerU API with batch processing support.
        
        Can process the entire document at once or in batches for large PDFs.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for processing
            src_fileid: Source file ID for logging/tracing
            is_ppt_converted: Whether the PDF was converted from PPT
            batch_size: Maximum pages per batch (0 for no batching)
            
        Returns:
            MinerUResult with parsed content
        """
        try:
            # Check PDF page count
            page_count = self._get_pdf_page_count(pdf_path)
            self.logger.info(f"mineru-api: PDF has {page_count} pages, batch_size={batch_size}")
            
            # Decide whether to use batch processing
            if batch_size > 0 and page_count > batch_size:
                self.logger.info(f"mineru-api: using batch processing (batch_size={batch_size})")
                return await self._process_document_in_batches(
                    pdf_path, temp_dir, src_fileid, is_ppt_converted, batch_size
                )
            else:
                self.logger.info(f"mineru-api: processing full document at once")
                return await self._process_document_full(
                    pdf_path, temp_dir, src_fileid, is_ppt_converted
                )
            
        except Exception as e:
            self.logger.error(f"mineru-api: document processing failed: {str(e)}")
            return MinerUResult(
                success=False,
                content="",
                images=[],
                tables=[],
                metadata={},
                error=str(e)
            )
    
    async def _process_document_full(self, pdf_path: str, temp_dir: str, src_fileid: str,
                                    is_ppt_converted: bool) -> MinerUResult:
        """Process full document at once (original implementation)."""
        self.logger.info(f"mineru-api: starting full document processing")
        
        # Choose processing method based on API type
        if self.config.mineru_api_type == "self_hosted":
            self.logger.info(f"mineru-api: using self-hosted MinerU API")
            result = await self._process_full_document_self_hosted(pdf_path, temp_dir, src_fileid, is_ppt_converted)
        elif self.config.mineru_api_key and self.config.mineru_api_key.strip():
            self.logger.info(f"mineru-api: using cloud MinerU API")
            result = await self._process_full_document_cloud(pdf_path, temp_dir, src_fileid, is_ppt_converted)
        else:
            self.logger.warning(f"mineru-api: no API configuration, using mock processing")
            result = await self._mock_mineru_processing(pdf_path, temp_dir, src_fileid, is_ppt_converted)
        
        self.logger.info(f"mineru-api: document processing completed")
        return result
    
    async def _process_document_in_batches(self, pdf_path: str, temp_dir: str, src_fileid: str,
                                          is_ppt_converted: bool, batch_size: int) -> MinerUResult:
        """
        Process document in batches of pages.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for processing
            src_fileid: Source file ID for logging/tracing
            is_ppt_converted: Whether the PDF was converted from PPT
            batch_size: Maximum pages per batch
            
        Returns:
            MinerUResult with merged results from all batches
        """
        try:
            page_count = self._get_pdf_page_count(pdf_path)
            num_batches = (page_count + batch_size - 1) // batch_size
            
            self.logger.info(f"mineru-api: splitting {page_count} pages into {num_batches} batches")
            
            # Process each batch
            batch_results = []
            for batch_idx in range(num_batches):
                start_page = batch_idx * batch_size
                end_page = min(start_page + batch_size, page_count)
                
                self.logger.info(f"mineru-api: processing batch {batch_idx + 1}/{num_batches} "
                               f"(pages {start_page + 1}-{end_page})")
                
                # Split PDF for this batch
                batch_pdf_path = await self._split_pdf(
                    pdf_path, temp_dir, start_page, end_page, batch_idx
                )
                
                # Process batch based on API type
                if self.config.mineru_api_type == "self_hosted":
                    batch_result = await self._process_batch_self_hosted(
                        batch_pdf_path, temp_dir, src_fileid, batch_idx,
                        start_page, end_page, is_ppt_converted
                    )
                elif self.config.mineru_api_key and self.config.mineru_api_key.strip():
                    batch_result = await self._process_batch_cloud(
                        batch_pdf_path, temp_dir, src_fileid, batch_idx,
                        start_page, end_page, is_ppt_converted
                    )
                else:
                    batch_result = await self._mock_mineru_processing(
                        batch_pdf_path, temp_dir, src_fileid, is_ppt_converted
                    )
                
                if batch_result.success:
                    batch_results.append((start_page, batch_result))
                else:
                    self.logger.error(f"mineru-api: batch {batch_idx + 1} failed: {batch_result.error}")
                    # Continue with other batches even if one fails
            
            # Merge all batch results
            return self._merge_batch_results(batch_results, page_count, is_ppt_converted)
            
        except Exception as e:
            self.logger.error(f"mineru-api: batch processing failed: {str(e)}")
            raise
    
    def _get_pdf_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF."""
        with fitz.open(pdf_path) as doc:
            return len(doc)
    
    async def _split_pdf(self, pdf_path: str, temp_dir: str, start_page: int, 
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
        batch_pdf_path = os.path.join(temp_dir, f"batch_{batch_idx}.pdf")
        
        with fitz.open(pdf_path) as src_doc:
            batch_doc = fitz.open()  # Create new PDF
            
            # Copy pages to new document
            for page_idx in range(start_page, end_page):
                batch_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)
            
            batch_doc.save(batch_pdf_path)
            batch_doc.close()
        
        self.logger.info(f"mineru-api: created batch PDF with {end_page - start_page} pages: {batch_pdf_path}")
        return batch_pdf_path
    
    
    
    
    
    
    
    
    
    
    async def _process_full_document_self_hosted(self, pdf_path: str, temp_dir: str, src_fileid: str, is_ppt_converted: bool) -> MinerUResult:
        """
        Process full PDF document at once using self-hosted MinerU API with content_list support.
        
        This method uploads the entire document and gets back content_list for all pages.
        """
        try:
            self.logger.info(f"mineru-api: processing full document with self-hosted API")
            
            if not self.session:
                raise RuntimeError("API client not initialized")
            
            start_time = asyncio.get_event_loop().time()
            
            # Prepare multipart form data
            form_data = aiohttp.FormData()
            
            # API parameters - enable content_list for full document processing
            form_data.add_field('return_middle_json', 'false')
            form_data.add_field('return_model_output', 'false') 
            form_data.add_field('return_md', 'true')
            form_data.add_field('return_images', 'true')
            form_data.add_field('return_content_list', 'true')  # Enable content_list
            form_data.add_field('end_page_id', '99999')
            form_data.add_field('parse_method', 'auto')
            form_data.add_field('start_page_id', '0')
            form_data.add_field('output_dir', './output')
            form_data.add_field('server_url', 'string')
            form_data.add_field('backend', 'pipeline')
            form_data.add_field('table_enable', 'true')
            form_data.add_field('formula_enable', 'true')
            
            # Add the PDF file
            with open(pdf_path, 'rb') as f:
                form_data.add_field('files', f, filename=os.path.basename(pdf_path), content_type='application/pdf')
                
                # Make API request
                async with self.session.post(
                    f"{self.config.mineru_api_url}/file_parse",
                    data=form_data,
                    headers={'accept': 'application/json'}
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Self-hosted MinerU API error: {response.status} - {error_text}")
                    
                    result = await response.json()
                    
                    # Log the top-level keys to understand response structure
                    self.logger.info(f"mineru-api: response top-level keys: {list(result.keys())}")
                    
                    # Extract content_list from response
                    results = result.get('results', {})
                    if not results:
                        raise Exception("No results in API response")
                    
                    # Get the first result (should be our PDF file)
                    file_result = next(iter(results.values()))
                    self.logger.info(f"mineru-api: file_result keys: {list(file_result.keys())}")
                    
                    # Extract content_list
                    content_list_str = file_result.get('content_list', '')
                    self.logger.info(f"mineru-api: content_list type: {type(content_list_str)}, length: {len(str(content_list_str))}")
                    if not content_list_str:
                        self.logger.error(f"mineru-api: No content_list in API response. File result keys: {list(file_result.keys())}")
                        # Log a sample of the file_result to understand what we're getting
                        sample_result = str(file_result)[:500] if file_result else 'None'
                        self.logger.error(f"mineru-api: File result sample: {sample_result}")
                        raise Exception("No content_list in API response")
                    
                    # Parse content_list to markdown
                    markdown_content, all_images, all_tables, page_data = self._parse_content_list_to_markdown(
                        content_list_str, temp_dir, src_fileid
                    )
                    
                    # Also get markdown content if available for language detection
                    md_content = file_result.get('md_content', '')
                    
                    # Extract base64 images if provided
                    images_data = file_result.get('images', {})
                    if images_data and isinstance(images_data, dict):
                        self.logger.info(f"mineru-api: saving {len(images_data)} base64 images")
                        saved_images = self._save_base64_images(images_data, temp_dir, src_fileid)
                        self.logger.info(f"mineru-api: saved images: {saved_images}")
                        # Merge with images from content_list
                        for img in saved_images:
                            if img not in all_images:
                                all_images.append(img)
                    else:
                        self.logger.info(f"mineru-api: no base64 images in 'images' field")
                    
                    # Check if there's an 'images' field at the top level of result
                    if 'images' in result and isinstance(result['images'], dict):
                        self.logger.info(f"mineru-api: found images at top level: {len(result['images'])} images")
                        # Save these images
                        for img_name, img_data in result['images'].items():
                            if img_name not in all_images:
                                # Save the image
                                try:
                                    if isinstance(img_data, str) and img_data.startswith('data:'):
                                        # Base64 encoded
                                        saved = self._save_base64_images({img_name: img_data}, temp_dir, src_fileid)
                                        all_images.extend(saved)
                                    self.logger.info(f"mineru-api: saved top-level image: {img_name}")
                                except Exception as e:
                                    self.logger.error(f"mineru-api: failed to save top-level image {img_name}: {e}")
                    
                    processing_time = asyncio.get_event_loop().time() - start_time
                    
                    # Detect language from the combined md_content
                    detected_language = None
                    if md_content and md_content.strip():
                        from .language_detector import LanguageDetector
                        language_code, confidence = LanguageDetector.detect_language(md_content)
                        if confidence > 0.7:
                            detected_language = language_code
                            self.logger.info(f"mineru-api: detected document language: {detected_language} (confidence: {confidence:.2f})")
                    
                    # If no md_content, detect from markdown_content as fallback
                    if not detected_language and markdown_content and markdown_content.strip():
                        from .language_detector import LanguageDetector
                        language_code, confidence = LanguageDetector.detect_language(markdown_content)
                        if confidence > 0.7:
                            detected_language = language_code
                            self.logger.info(f"mineru-api: detected document language from content_list: {detected_language} (confidence: {confidence:.2f})")
                    
                    # Create metadata
                    import json
                    metadata = {
                        "processing_time": processing_time,
                        "total_pages": len(page_data),
                        "images_found": len(all_images),
                        "tables_found": len(all_tables),
                        "is_ppt_source": is_ppt_converted,
                        "processing_mode": "full_document_self_hosted",
                        "api_version": "self_hosted",
                        "api_type": "self_hosted",
                        "page_data": page_data,
                        "content_list": json.loads(content_list_str) if isinstance(content_list_str, str) else content_list_str,
                        "detected_language": detected_language  # Add detected language to metadata
                    }
                    
                    # Create page results for compatibility
                    mineru_page_results = []
                    for page_idx, pdata in page_data.items():
                        mineru_page_results.append(MinerUPageResult(
                            page_idx=page_idx,
                            success=True,
                            content=pdata['content'],
                            images=pdata['images'],
                            tables=pdata['tables'],
                            metadata=pdata['metadata']
                        ))
                    
                    self.logger.info(f"mineru-api: full document self-hosted processing completed in {processing_time:.2f}s")
                    
                    return MinerUResult(
                        success=True,
                        content=markdown_content,
                        images=all_images,
                        tables=all_tables,
                        metadata=metadata,
                        page_results=mineru_page_results
                    )
                    
        except Exception as e:
            self.logger.error(f"mineru-api: full document self-hosted processing failed: {str(e)}")
            raise
    
    def _parse_self_hosted_response(self, api_response: Dict, temp_dir: str, page_id: str, page_num: int) -> Tuple[str, List[str], List[Dict]]:
        """
        Parse response from self-hosted MinerU API.
        
        Expected response format:
        {
            "backend": "pipeline",
            "version": "2.1.10", 
            "results": {
                "page_xxx": {
                    "md_content": "# Content...",
                    "images": {
                        "filename.jpg": "data:image/jpeg;base64,xxx...",
                        ...
                    },
                    "middle_json": {...},
                    "model_output": {...}
                }
            }
        }
        """
        try:
            content = ""
            images = []
            tables = []
            
            # Extract results
            results = api_response.get('results', {})
            
            if results:
                # Get the first result (should be our PDF file)
                file_result = next(iter(results.values())) if results else {}
                
                # Extract markdown content
                md_content = file_result.get('md_content', '')
                if md_content:
                    content = md_content
                else:
                    content = f"# Page {page_num}\n\nNo content extracted from self-hosted API"
                
                # Extract images from the images field (base64 encoded)
                images_data = file_result.get('images', {})
                if images_data and isinstance(images_data, dict):
                    images = self._save_base64_images(images_data, temp_dir, page_id)
                else:
                    # Fallback to extracting from markdown if no images field
                    images = self._extract_images_from_markdown(md_content, temp_dir, page_id)
                
                # Extract table information if available in middle_json
                middle_json = file_result.get('middle_json', {})
                if middle_json and isinstance(middle_json, dict):
                    tables = self._extract_tables_from_middle_json(middle_json, page_num)
                
            self.logger.debug(f"mineru-api: [{page_id}] parsed self-hosted response - content: {len(content)} chars, images: {len(images)}, tables: {len(tables)}")
            
            return content, images, tables
            
        except Exception as e:
            self.logger.error(f"mineru-api: [{page_id}] failed to parse self-hosted response: {str(e)}")
            return f"# Page {page_num}\n\nError parsing API response: {str(e)}", [], []
    
    def _save_base64_images(self, images_data: Dict[str, str], temp_dir: str, page_id: str) -> List[str]:
        """
        Save base64 encoded images to files.
        
        Args:
            images_data: Dictionary with image filename as key and base64 data as value
            temp_dir: Directory to save images
            page_id: Page identifier for logging
            
        Returns:
            List of saved image filenames
        """
        import base64
        
        saved_images = []
        
        for filename, base64_data in images_data.items():
            try:
                # Extract base64 data (remove data URI prefix if present)
                if base64_data.startswith('data:'):
                    # Format: data:image/jpeg;base64,xxx...
                    base64_data = base64_data.split(',', 1)[1]
                
                # Decode base64 to binary
                image_data = base64.b64decode(base64_data)
                
                # Use the original filename without prefix to match content_list references
                image_filename = filename
                image_path = os.path.join(temp_dir, image_filename)
                
                # Save image file
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                
                saved_images.append(image_filename)
                self.logger.info(f"mineru-api: [{page_id}] saved base64 image: {image_filename} ({len(image_data)} bytes)")
                
            except Exception as e:
                self.logger.error(f"mineru-api: [{page_id}] failed to save base64 image {filename}: {str(e)}")
        
        return saved_images
    
    def _extract_images_from_markdown(self, md_content: str, temp_dir: str, page_id: str) -> List[str]:
        """
        Extract image references from markdown content and handle them.
        
        Self-hosted MinerU typically includes images as markdown references like ![alt](path)
        """
        import re
        
        images = []
        
        # Find all markdown image references
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        matches = re.findall(image_pattern, md_content)
        
        for _, image_path in matches:
            try:
                # Handle different image path formats
                if image_path.startswith('./') or image_path.startswith('../'):
                    # Relative path - assume it's in the same directory structure
                    actual_path = os.path.normpath(os.path.join(temp_dir, image_path))
                elif os.path.isabs(image_path):
                    # Absolute path
                    actual_path = image_path
                else:
                    # Relative to temp directory
                    actual_path = os.path.join(temp_dir, image_path)
                
                # Check if image file exists and copy to our temp directory if needed
                if os.path.exists(actual_path):
                    # Generate new filename for our processing
                    image_filename = f"self_hosted_{page_id}_{os.path.basename(image_path)}"
                    dest_path = os.path.join(temp_dir, image_filename)
                    
                    if actual_path != dest_path:
                        import shutil
                        shutil.copy(actual_path, dest_path)
                    
                    images.append(image_filename)
                    self.logger.debug(f"mineru-api: [{page_id}] extracted image: {image_filename}")
                else:
                    self.logger.warning(f"mineru-api: [{page_id}] image file not found: {actual_path}")
                    
            except Exception as e:
                self.logger.error(f"mineru-api: [{page_id}] error processing image {image_path}: {str(e)}")
        
        return images
    
    def _extract_tables_from_middle_json(self, middle_json: Dict, page_num: int) -> List[Dict]:
        """
        Extract table information from middle_json if available.
        """
        tables = []
        
        try:
            # This structure depends on the actual format returned by self-hosted MinerU
            # Adjust based on the actual response structure
            if 'tables' in middle_json:
                table_data = middle_json['tables']
                if isinstance(table_data, list):
                    for i, table in enumerate(table_data):
                        tables.append({
                            'page': page_num,
                            'table_id': i,
                            'content': str(table),
                            'source': 'self_hosted_middle_json'
                        })
                elif isinstance(table_data, dict):
                    tables.append({
                        'page': page_num,
                        'content': str(table_data),
                        'source': 'self_hosted_middle_json'
                    })
        
        except Exception as e:
            self.logger.debug(f"mineru-api: page {page_num} table extraction from middle_json failed: {str(e)}")
        
        return tables
    
    async def _upload_file_to_accessible_url(self, pdf_path: str, src_fileid: str) -> str:
        """
        Upload file to a publicly accessible URL for MinerU processing.
        
        Uses platform adapter's upload_file method
        """
        try:
            # Use platform adapter for upload if available
            if hasattr(self, 'platform_adapter') and self.platform_adapter:
                # The adapter will handle the upload
                return await self.platform_adapter.upload_file(pdf_path, {
                    'src_fileid': src_fileid
                })
            
            # Fallback: return local path if no adapter
            logger.warning("No platform adapter available for upload, returning local path")
            return pdf_path
            
        except Exception as e:
            self.logger.error(f"mineru-api: file upload failed: {str(e)}")
            raise
    
    
    async def _poll_task_completion(self, task_id: str, src_fileid: str, 
                                  max_wait_time: int = 600) -> str:
        """
        Poll MinerU task until completion.
        
        Args:
            task_id: Task ID to poll
            src_fileid: Source file ID for logging
            max_wait_time: Maximum wait time in seconds
            
        Returns:
            Result ZIP file URL
        """
        if not self.session:
            raise RuntimeError("API client not initialized")
        
        headers = {
            'Authorization': f'Bearer {self.config.mineru_api_key}',
            'Accept': '*/*'
        }
        
        start_time = asyncio.get_event_loop().time()
        poll_interval = 5  # Start with 5 seconds
        max_poll_interval = 30  # Max 30 seconds between polls
        
        while True:
            current_time = asyncio.get_event_loop().time()
            if current_time - start_time > max_wait_time:
                raise Exception(f"Task polling timeout after {max_wait_time} seconds")
            
            try:
                async with self.session.get(
                    f"{self.config.mineru_api_url}/api/v4/extract/task/{task_id}",
                    headers=headers
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"MinerU polling error: {response.status} - {error_text}")
                    
                    result = await response.json()
                    
                    if result.get('code') != 0:
                        raise Exception(f"MinerU polling error: {result.get('msg', 'Unknown error')}")
                    
                    data = result['data']
                    state = data['state']
                    
                    if state == 'done':
                        full_zip_url = data['full_zip_url']
                        self.logger.info(f"mineru-api: task completed: {task_id}")
                        return full_zip_url
                    
                    elif state == 'failed':
                        error_msg = data.get('err_msg', 'Unknown error')
                        raise Exception(f"MinerU task failed: {error_msg}")
                    
                    elif state in ['pending', 'running', 'converting']:
                        # Log progress if available
                        if 'extract_progress' in data:
                            progress = data['extract_progress']
                            extracted = progress.get('extracted_pages', 0)
                            total = progress.get('total_pages', 0)
                            start_time_str = progress.get('start_time', 'N/A')
                            self.logger.info(f"mineru-api: task {state}: {extracted}/{total} pages (started: {start_time_str})")
                        else:
                            self.logger.info(f"mineru-api: task {state}")
                        
                        # Wait before next poll
                        await asyncio.sleep(poll_interval)
                        
                        # Gradually increase poll interval
                        poll_interval = min(poll_interval * 1.2, max_poll_interval)
                    
                    else:
                        raise Exception(f"Unknown task state: {state}")
            
            except aiohttp.ClientError as e:
                self.logger.warning(f"mineru-api: polling connection error: {str(e)}")
                await asyncio.sleep(poll_interval)
    
    async def _process_full_document_cloud(self, pdf_path: str, temp_dir: str, src_fileid: str, is_ppt_converted: bool) -> MinerUResult:
        """
        Process full PDF document at once using cloud MinerU API.
        
        This method uploads the entire document and extracts content_list from the result.
        """
        try:
            self.logger.info(f"mineru-api: processing full document with cloud API")
            
            start_time = asyncio.get_event_loop().time()
            
            # Step 1: Upload file to accessible URL
            file_url = await self._upload_file_to_accessible_url(pdf_path, src_fileid)
            self.logger.info(f"mineru-api: uploaded file URL: {file_url}")
            if not file_url.startswith(('http://', 'https://')):
                self.logger.warning(f"mineru-api: URL may not be valid for Cloud API: {file_url}")
            # Step 2: Create task for full document
            task_id = await self._create_mineru_task_full_document(file_url, src_fileid)
            
            # Step 3: Poll for completion
            result_url = await self._poll_task_completion(task_id, src_fileid, max_wait_time=900)  # 15 min for full doc
            
            # Step 4: Download and extract results with content_list
            markdown_content, all_images, all_tables, page_data, full_md_content = await self._download_and_extract_results_with_content_list(
                result_url, temp_dir, src_fileid
            )
            
            processing_time = asyncio.get_event_loop().time() - start_time
            
            # Detect language from full.md first, then fallback to markdown_content
            detected_language = None
            if full_md_content and full_md_content.strip():
                from .language_detector import LanguageDetector
                language_code, confidence = LanguageDetector.detect_language(full_md_content)
                if confidence > 0.7:
                    detected_language = language_code
                    self.logger.info(f"mineru-api: detected document language from full.md: {detected_language} (confidence: {confidence:.2f})")
            
            # Fallback to content_list markdown if no full.md or low confidence
            if not detected_language and markdown_content and markdown_content.strip():
                from .language_detector import LanguageDetector
                language_code, confidence = LanguageDetector.detect_language(markdown_content)
                if confidence > 0.7:
                    detected_language = language_code
                    self.logger.info(f"mineru-api: detected document language from content_list: {detected_language} (confidence: {confidence:.2f})")
            
            # Create metadata
            metadata = {
                "processing_time": processing_time,
                "total_pages": len(page_data),
                "images_found": len(all_images),
                "tables_found": len(all_tables),
                "is_ppt_source": is_ppt_converted,
                "processing_mode": "full_document_cloud",
                "api_version": "v4",
                "api_type": "cloud",
                "page_data": page_data,
                "detected_language": detected_language  # Add detected language to metadata
            }
            
            # Create page results for compatibility
            mineru_page_results = []
            for page_idx, pdata in page_data.items():
                mineru_page_results.append(MinerUPageResult(
                    page_idx=page_idx,
                    success=True,
                    content=pdata['content'],
                    images=pdata['images'],
                    tables=pdata['tables'],
                    metadata=pdata['metadata']
                ))
            
            self.logger.info(f"mineru-api: full document cloud processing completed in {processing_time:.2f}s")
            
            return MinerUResult(
                success=True,
                content=markdown_content,
                images=all_images,
                tables=all_tables,
                metadata=metadata,
                page_results=mineru_page_results
            )
            
        except Exception as e:
            self.logger.error(f"mineru-api: full document cloud processing failed: {str(e)}")
            raise
    
    async def _create_mineru_task_full_document(self, file_url: str, src_fileid: str) -> str:
        """
        Create MinerU task for full document processing.
        """
        if not self.session:
            raise RuntimeError("API client not initialized")
        
        headers = {
            'Authorization': f'Bearer {self.config.mineru_api_key}',
            'Content-Type': 'application/json',
            'Accept': '*/*'
        }
        
        # Configure processing options for full document
        payload = {
            'url': file_url,
            'is_ocr': True,
            'enable_formula': True,
            'enable_table': True,
            'language': 'auto',
            'data_id': src_fileid,
            'model_version': 'v1',
            'extra_formats': ['html']  # Request content_list format
        }
        
        try:
            async with self.session.post(
                f"{self.config.mineru_api_url}/api/v4/extract/task",
                headers=headers,
                json=payload
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"MinerU API error: {response.status} - {error_text}")
                
                result = await response.json()
                
                if result.get('code') != 0:
                    raise Exception(f"MinerU API error: {result.get('msg', 'Unknown error')}")
                
                task_id = result['data']['task_id']
                self.logger.info(f"mineru-api: full document task created: {task_id}")
                
                return task_id
                
        except aiohttp.ClientError as e:
            raise Exception(f"MinerU API connection error: {str(e)}")
    
    async def _download_and_extract_results_with_content_list(self, result_url: str, temp_dir: str, 
                                                            src_fileid: str) -> Tuple[str, List[str], List[Dict], Dict[int, Dict], str]:
        """
        Download and extract MinerU processing results including content_list.
        
        Returns:
            Tuple of (markdown_content, images, tables, page_data, full_md_content)
        """
        if not self.session:
            raise RuntimeError("API client not initialized")
        
        # Download ZIP file
        zip_path = os.path.join(temp_dir, f"mineru_result_{src_fileid}.zip")
        
        try:
            async with self.session.get(result_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Download error: {response.status} - {error_text}")
                
                with open(zip_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                
                self.logger.info(f"mineru-api: downloaded result ZIP: {zip_path}")
        
        except aiohttp.ClientError as e:
            raise Exception(f"Download connection error: {str(e)}")
        
        # Extract ZIP file
        extract_dir = os.path.join(temp_dir, f"mineru_extracted_{src_fileid}")
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        self.logger.info(f"mineru-api: extracted results to: {extract_dir}")
        
        # Look for content_list file and full.md
        content_list = None
        markdown_content = ""
        full_md_content = ""  # For language detection
        images = []
        tables = []
        
        for root, _, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Look for content_list JSON file
                if file.endswith('_content_list.json'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        import json
                        content_list = json.load(f)
                    self.logger.info(f"mineru-api: found content_list with {len(content_list)} items")
                
                elif file == 'full.md':
                    # Read full.md for language detection
                    with open(file_path, 'r', encoding='utf-8') as f:
                        full_md_content = f.read()
                    self.logger.info(f"mineru-api: found full.md with {len(full_md_content)} characters")
                
                elif file.endswith('.md') and not markdown_content:
                    # Backup: use other markdown files if no content_list
                    with open(file_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()
        
        # Parse content_list if found
        if content_list:
            markdown_content, all_images, all_tables, page_data = self._parse_content_list_to_markdown(
                content_list, temp_dir, src_fileid
            )
            
            self.logger.info(f"mineru-api: all_images from content_list: {all_images[:5]}...")  # Show first 5 images
            
            # Copy images referenced in content_list from images/ directory
            images_dir = os.path.join(extract_dir, 'images')
            self.logger.info(f"mineru-api: checking for images directory: {images_dir}")
            
            # List all directories in extract_dir for debugging
            if os.path.exists(extract_dir):
                self.logger.info(f"mineru-api: contents of extract_dir: {os.listdir(extract_dir)}")
            
            if os.path.exists(images_dir):
                self.logger.info(f"mineru-api: found images directory: {images_dir}")
                # List files in images directory
                image_files = os.listdir(images_dir)
                self.logger.info(f"mineru-api: found {len(image_files)} files in images directory")
                self.logger.info(f"mineru-api: image files in directory: {image_files[:10]}")  # Show first 10 files
                
                # Copy ALL image files from images directory to temp_dir
                import shutil
                for img_file in image_files:
                    if img_file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        src_img_path = os.path.join(images_dir, img_file)
                        dest_img_path = os.path.join(temp_dir, img_file)
                        shutil.copy(src_img_path, dest_img_path)
                        self.logger.info(f"mineru-api: copied image {img_file} to temp_dir")
                
                # Also try to copy specific images referenced in content_list
                for img_filename in all_images:
                    # Try different possible paths and names
                    possible_names = [
                        img_filename,
                        img_filename.replace('.png', '.jpg'),
                        img_filename.replace('.jpg', '.png'),
                        os.path.basename(img_filename)  # Just the filename without path
                    ]
                    
                    copied = False
                    for name in possible_names:
                        src_img_path = os.path.join(images_dir, name)
                        if os.path.exists(src_img_path):
                            dest_img_path = os.path.join(temp_dir, img_filename)
                            if not os.path.exists(dest_img_path):
                                shutil.copy(src_img_path, dest_img_path)
                                self.logger.info(f"mineru-api: copied referenced image {name} as {img_filename}")
                                copied = True
                                break
                    
                    if not copied:
                        # Try to find similar files
                        base_name = os.path.splitext(img_filename)[0]
                        matching_files = [f for f in image_files if base_name in f]
                        if matching_files:
                            self.logger.warning(f"mineru-api: image {img_filename} not found, but similar files exist: {matching_files}")
                        else:
                            self.logger.warning(f"mineru-api: image {img_filename} not found in images dir")
            else:
                self.logger.warning(f"mineru-api: images directory not found: {images_dir}")
            
            # For single-page documents, assign unassigned images to page 0
            if len(page_data) == 1 and 0 in page_data:
                # Check if any images are not yet assigned to pages
                assigned_images = set()
                for pd in page_data.values():
                    assigned_images.update(pd.get('images', []))
                
                unassigned_images = [img for img in all_images if img not in assigned_images]
                if unassigned_images:
                    self.logger.info(f"mineru-api: assigning {len(unassigned_images)} unassigned images to page 0")
                    page_data[0]['images'].extend(unassigned_images)
        else:
            # Fallback: parse markdown to create page data
            self.logger.warning("mineru-api: no content_list found, using markdown fallback")
            page_data = self._parse_markdown_to_page_data(markdown_content)
            
            # Copy all images from extract_dir to temp_dir (without mineru_ prefix)
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    if file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        file_path = os.path.join(root, file)
                        dest_path = os.path.join(temp_dir, file)
                        
                        import shutil
                        shutil.copy(file_path, dest_path)
                        images.append(file)
                        self.logger.info(f"mineru-api: copied image {file} to temp_dir (fallback)")
            
            all_images = images
            all_tables = tables
        
        # Clean up ZIP file
        os.remove(zip_path)
        
        self.logger.info(f"mineru-api: parsed results - {len(page_data)} pages, "
                        f"{len(all_images)} images, {len(all_tables)} tables")
        
        return markdown_content, all_images, all_tables, page_data, full_md_content
    
    def _parse_markdown_to_page_data(self, markdown_content: str) -> Dict[int, Dict]:
        """
        Parse markdown content to create page data structure.
        
        This is a fallback when content_list is not available.
        """
        page_data = {}
        
        # Split by page markers
        import re
        page_pattern = r'## Page (\d+)'
        parts = re.split(page_pattern, markdown_content)
        
        if len(parts) > 1:
            # Skip the first part (before first page marker)
            for i in range(1, len(parts), 2):
                if i < len(parts) - 1:
                    page_num = int(parts[i])
                    page_content = parts[i + 1].strip()
                    page_idx = page_num - 1
                    
                    page_data[page_idx] = {
                        'content': page_content,
                        'images': [],
                        'tables': [],
                        'metadata': {'page_num': page_num}
                    }
        else:
            # No page markers, treat as single page
            page_data[0] = {
                'content': markdown_content,
                'images': [],
                'tables': [],
                'metadata': {'page_num': 1}
            }
        
        return page_data
    
    async def _download_and_extract_results(self, result_url: str, temp_dir: str, 
                                          src_fileid: str) -> Tuple[str, List[str], List[Dict]]:
        """
        Download and extract MinerU processing results.
        
        Args:
            result_url: URL to result ZIP file
            temp_dir: Temporary directory for extraction
            src_fileid: Source file ID for logging
            
        Returns:
            Tuple of (content, images, tables)
        """
        if not self.session:
            raise RuntimeError("API client not initialized")
        
        # Download ZIP file
        zip_path = os.path.join(temp_dir, f"mineru_result_{src_fileid}.zip")
        
        try:
            async with self.session.get(result_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Download error: {response.status} - {error_text}")
                
                with open(zip_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                
                self.logger.info(f"mineru-api: downloaded result ZIP: {zip_path}")
        
        except aiohttp.ClientError as e:
            raise Exception(f"Download connection error: {str(e)}")
        
        # Extract ZIP file
        extract_dir = os.path.join(temp_dir, f"mineru_extracted_{src_fileid}")
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        self.logger.info(f"mineru-api: extracted results to: {extract_dir}")
        
        # Parse extracted content
        content = ""
        images = []
        tables = []
        
        # Look for markdown file and other assets
        for root, _, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                if file.endswith('.md'):
                    # Read markdown content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.logger.info(f"mineru-api: loaded markdown content: {len(content)} chars")
                
                elif file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    # Copy image to temp directory and add to list
                    image_name = f"mineru_{file}"
                    dest_path = os.path.join(temp_dir, image_name)
                    
                    import shutil
                    shutil.copy(file_path, dest_path)
                    images.append(image_name)
                    
                elif file.endswith('.html'):
                    # Parse HTML for additional table information if needed
                    with open(file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    # Extract table information from HTML
                    table_count = html_content.count('<table')
                    if table_count > 0:
                        tables.append({
                            "source": "html",
                            "table_count": table_count,
                            "content": "Tables extracted from HTML format"
                        })
        
        # Clean up ZIP file
        os.remove(zip_path)
        
        self.logger.info(f"mineru-api: parsed results - content: {len(content)} chars, images: {len(images)}, tables: {len(tables)}")
        
        return content, images, tables
    
    async def _mock_mineru_processing(self, pdf_path: str, temp_dir: str, 
                                    src_fileid: str, is_ppt_converted: bool) -> MinerUResult:
        """
        Mock MinerU processing for development/testing.
        
        Provides realistic output structure for development without API calls.
        """
        try:
            # Simulate processing delay
            await asyncio.sleep(0.5)
            
            # Extract basic information from PDF for mock response
            content_parts = []
            images = []
            tables = []
            content_list = []  # For context extraction
            
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc):
                    # Extract text
                    page_text = page.get_text()
                    if page_text.strip():
                        content_parts.append(f"## Page {page_num + 1}\\n\\n{page_text}\\n")
                        # Add to content_list
                        content_list.append({
                            'page_idx': page_num,
                            'type': 'text',
                            'text': page_text,
                            'metadata': {}
                        })
                    
                    # Mock image extraction (would be done by MinerU)
                    for img in page.get_images(full=True):
                        xref = img[0]
                        bbox = page.get_image_bbox(img)
                        if bbox.width > 0 and bbox.height > 0:
                            image_filename = f"mineru_image_{xref}.png"
                            image_path = os.path.join(temp_dir, image_filename)
                            
                            # Extract and save image
                            try:
                                pix = fitz.Pixmap(doc, xref)
                                if pix.n - pix.alpha < 4:  # GRAY or RGB
                                    pix.save(image_path)
                                    images.append(image_filename)
                                    # Add to content_list
                                    content_list.append({
                                        'page_idx': page_num,
                                        'type': 'image',
                                        'img_path': image_filename,
                                        'metadata': {}
                                    })
                                pix = None  # Free memory
                            except Exception:
                                pass
                    
                    # Mock table detection
                    if "table" in page_text.lower() or "|" in page_text:
                        tables.append({
                            "page": page_num,
                            "content": "Mock table content detected",
                            "bbox": [0, 0, page.rect.width, page.rect.height]
                        })
                        # Add to content_list
                        content_list.append({
                            'page_idx': page_num,
                            'type': 'table',
                            'content': 'Mock table content',
                            'metadata': {}
                        })
            
            # Combine content with mock markdown structure
            mock_content = self._create_mock_markdown_content(content_parts, images)
            
            # Detect language from the combined content
            detected_language = None
            if mock_content and mock_content.strip():
                from .language_detector import LanguageDetector
                language_code, confidence = LanguageDetector.detect_language(mock_content)
                if confidence > 0.7:
                    detected_language = language_code
                    self.logger.info(f"mineru-api: detected document language (mock): {detected_language} (confidence: {confidence:.2f})")
            
            # Mock metadata
            metadata = {
                "processing_time": 0.5,
                "pages_processed": len(doc),
                "images_found": len(images),
                "tables_found": len(tables),
                "is_ppt_source": is_ppt_converted,
                "api_version": "mock",
                "content_list": content_list,  # Include content list for context extraction
                "detected_language": detected_language  # Add detected language to metadata
            }
            
            self.logger.info(f"mineru-api: mock processing complete: {metadata}")
            
            return MinerUResult(
                success=True,
                content=mock_content,
                images=images,
                tables=tables,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"mineru-api: mock processing error: {str(e)}")
            raise
    
    def _create_mock_markdown_content(self, content_parts: List[str], images: List[str]) -> str:
        """
        Create mock markdown content that simulates MinerU output structure.
        """
        mock_parts = []
        
        # Add document header
        mock_parts.append("# Document Content (MinerU Mock)")
        mock_parts.append("")
        
        # Add content parts
        for part in content_parts:
            mock_parts.append(part)
        
        # Add image references
        if images:
            mock_parts.append("## Images")
            mock_parts.append("")
            for img in images:
                mock_parts.append(f"![Image](./{img})")
                mock_parts.append("")
        
        return "\\n".join(mock_parts)
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute a function with exponential backoff retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result from the function
            
        Raises:
            Exception from the last retry attempt
        """
        max_retries = self.config.api_max_retries
        retry_delay = self.config.api_retry_delay
        backoff = self.config.api_retry_backoff
        max_delay = self.config.api_retry_max_delay
        retry_on_errors = self.config.retry_on_errors
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                
                # Check if result indicates success
                if hasattr(result, 'success') and not result.success:
                    # Check if this is a retryable error
                    if result.error and retry_on_errors:
                        should_retry = any(err_type in str(result.error) for err_type in retry_on_errors)
                        if not should_retry and attempt < max_retries:
                            self.logger.warning(f"Non-retryable error: {result.error}")
                            return result
                    
                    if attempt < max_retries:
                        self.logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {result.error}")
                        last_exception = Exception(result.error or "API call failed")
                    else:
                        return result
                else:
                    # Success
                    if attempt > 0:
                        self.logger.info(f"API call succeeded after {attempt + 1} attempts")
                    return result
                    
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                # Network-related errors are always retryable
                last_exception = e
                if attempt < max_retries:
                    self.logger.warning(f"Network error (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                else:
                    self.logger.error(f"Network error after {max_retries + 1} attempts: {str(e)}")
                    raise
                    
            except Exception as e:
                # Check if this is a retryable error type
                if retry_on_errors:
                    should_retry = any(err_type in str(e) for err_type in retry_on_errors)
                    if not should_retry:
                        self.logger.error(f"Non-retryable error: {str(e)}")
                        raise
                
                last_exception = e
                if attempt < max_retries:
                    self.logger.warning(f"API error (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                else:
                    self.logger.error(f"API error after {max_retries + 1} attempts: {str(e)}")
                    raise
            
            # If we need to retry, wait with exponential backoff
            if attempt < max_retries:
                delay = min(retry_delay * (backoff ** attempt), max_delay)
                self.logger.info(f"Retrying in {delay:.1f} seconds...")
                await asyncio.sleep(delay)
        
        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        else:
            raise Exception("Maximum retries exceeded")
    
    async def _process_batch_self_hosted_impl(self, batch_pdf_path: str, temp_dir: str, src_fileid: str,
                                        batch_idx: int, start_page: int, end_page: int,
                                        is_ppt_converted: bool) -> MinerUResult:
        """
        Process a batch of pages using self-hosted MinerU API.
        
        Args:
            batch_pdf_path: Path to batch PDF file
            temp_dir: Temporary directory
            src_fileid: Source file ID
            batch_idx: Batch index
            start_page: Original start page index
            end_page: Original end page index
            is_ppt_converted: Whether PDF is from PPT
            
        Returns:
            MinerUResult for this batch
        """
        try:
            if not self.session:
                raise RuntimeError("API client not initialized")
            
            # Prepare multipart form data
            form_data = aiohttp.FormData()
            
            # API parameters
            form_data.add_field('return_middle_json', 'false')
            form_data.add_field('return_model_output', 'false')
            form_data.add_field('return_md', 'true')
            form_data.add_field('return_images', 'true')
            form_data.add_field('return_content_list', 'true')
            form_data.add_field('end_page_id', str(end_page - start_page))
            form_data.add_field('parse_method', 'auto')
            form_data.add_field('start_page_id', '0')
            form_data.add_field('output_dir', './output')
            form_data.add_field('server_url', 'string')
            form_data.add_field('backend', 'pipeline')
            form_data.add_field('table_enable', 'true')
            form_data.add_field('formula_enable', 'true')
            
            # Add the batch PDF file
            with open(batch_pdf_path, 'rb') as f:
                form_data.add_field('files', f, filename=f"batch_{batch_idx}.pdf", 
                                  content_type='application/pdf')
                
                # Make API request
                async with self.session.post(
                    f"{self.config.mineru_api_url}/file_parse",
                    data=form_data,
                    headers={'accept': 'application/json'}
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Self-hosted MinerU API error: {response.status} - {error_text}")
                    
                    result = await response.json()
                    
                    # Process the batch result
                    results = result.get('results', {})
                    if not results:
                        raise Exception("No results in API response")
                    
                    file_result = next(iter(results.values()))
                    content_list_str = file_result.get('content_list', '')
                    
                    if not content_list_str:
                        raise Exception("No content_list in API response")
                    
                    # Parse content_list with adjusted page indices
                    markdown_content, images, tables, page_data = self._parse_content_list_to_markdown_batch(
                        content_list_str, temp_dir, src_fileid, start_page
                    )
                    
                    # Save batch images if provided
                    images_data = file_result.get('images', {})
                    if images_data and isinstance(images_data, dict):
                        saved_images = self._save_base64_images(images_data, temp_dir, 
                                                               f"{src_fileid}_batch_{batch_idx}")
                        images.extend([img for img in saved_images if img not in images])
                    
                    metadata = {
                        "batch_idx": batch_idx,
                        "start_page": start_page,
                        "end_page": end_page,
                        "pages_in_batch": end_page - start_page,
                        "is_ppt_source": is_ppt_converted,
                        "page_data": page_data  # Add page_data so it can be extracted per page
                    }
                    
                    return MinerUResult(
                        success=True,
                        content=markdown_content,
                        images=images,
                        tables=tables,
                        metadata=metadata,
                        page_results=None
                    )
                    
        except Exception as e:
            self.logger.error(f"mineru-api: batch {batch_idx} processing failed: {str(e)}")
            return MinerUResult(
                success=False,
                content="",
                images=[],
                tables=[],
                metadata={"batch_idx": batch_idx, "error": str(e)},
                error=str(e)
            )
    
    async def _process_batch_self_hosted(self, batch_pdf_path: str, temp_dir: str, src_fileid: str,
                                        batch_idx: int, start_page: int, end_page: int,
                                        is_ppt_converted: bool) -> MinerUResult:
        """
        Process a batch WITHOUT retry logic.
        Batch failures will fallback to single-page processing where retry happens.
        """
        # Direct call without retry wrapper
        return await self._process_batch_self_hosted_impl(
            batch_pdf_path, temp_dir, src_fileid, batch_idx, start_page, end_page, is_ppt_converted
        )
    
    async def _process_batch_cloud_impl(self, batch_pdf_path: str, temp_dir: str, src_fileid: str,
                                  batch_idx: int, start_page: int, end_page: int,
                                  is_ppt_converted: bool) -> MinerUResult:
        """
        Implementation of batch processing using cloud MinerU API.
        """
        try:
            # Upload batch PDF
            file_url = await self._upload_file_to_accessible_url(batch_pdf_path, 
                                                                f"{src_fileid}_batch_{batch_idx}")
            
            # Create task for batch
            task_id = await self._create_mineru_task_full_document(file_url, 
                                                                  f"{src_fileid}_batch_{batch_idx}")
            
            # Poll for completion
            result_url = await self._poll_task_completion(task_id, src_fileid, max_wait_time=300)
            
            # Download and extract results
            markdown_content, images, tables, page_data, _ = await self._download_and_extract_results_with_content_list(
                result_url, temp_dir, f"{src_fileid}_batch_{batch_idx}"
            )
            
            # Adjust page indices to match original document
            adjusted_page_data = {}
            for page_idx, pdata in page_data.items():
                adjusted_idx = page_idx + start_page
                adjusted_page_data[adjusted_idx] = pdata
                adjusted_page_data[adjusted_idx]['metadata']['original_page_num'] = adjusted_idx + 1
            
            metadata = {
                "batch_idx": batch_idx,
                "start_page": start_page,
                "end_page": end_page,
                "pages_in_batch": end_page - start_page,
                "is_ppt_source": is_ppt_converted,
                "page_data": adjusted_page_data
            }
            
            return MinerUResult(
                success=True,
                content=markdown_content,
                images=images,
                tables=tables,
                metadata=metadata,
                page_results=None
            )
            
        except Exception as e:
            self.logger.error(f"mineru-api: cloud batch {batch_idx} processing failed: {str(e)}")
            return MinerUResult(
                success=False,
                content="",
                images=[],
                tables=[],
                metadata={"batch_idx": batch_idx, "error": str(e)},
                error=str(e)
            )
    
    async def _process_batch_cloud(self, batch_pdf_path: str, temp_dir: str, src_fileid: str,
                                  batch_idx: int, start_page: int, end_page: int,
                                  is_ppt_converted: bool) -> MinerUResult:
        """
        Process a batch using cloud API WITHOUT retry logic.
        Batch failures will fallback to single-page processing where retry happens.
        """
        # Direct call without retry wrapper
        return await self._process_batch_cloud_impl(
            batch_pdf_path, temp_dir, src_fileid, batch_idx, start_page, end_page, is_ppt_converted
        )
    
    def _merge_batch_results(self, batch_results: List[Tuple[int, MinerUResult]], 
                            total_pages: int, is_ppt_converted: bool) -> MinerUResult:
        """
        Merge results from multiple batches into a single MinerUResult.
        
        Args:
            batch_results: List of (start_page, MinerUResult) tuples
            total_pages: Total number of pages in original document
            is_ppt_converted: Whether the PDF was converted from PPT
            
        Returns:
            Merged MinerUResult
        """
        if not batch_results:
            return MinerUResult(
                success=False,
                content="",
                images=[],
                tables=[],
                metadata={},
                error="No successful batches"
            )
        
        # Sort batches by start page
        batch_results.sort(key=lambda x: x[0])
        
        # Merge content
        merged_content_parts = []
        all_images = []
        all_tables = []
        all_page_data = {}
        all_page_results = []
        
        for start_page, batch_result in batch_results:
            # Add batch content
            merged_content_parts.append(batch_result.content)
            
            # Collect images (avoid duplicates)
            for img in batch_result.images:
                if img not in all_images:
                    all_images.append(img)
            
            # Collect tables
            all_tables.extend(batch_result.tables)
            
            # Merge page data if available
            if batch_result.metadata and 'page_data' in batch_result.metadata:
                all_page_data.update(batch_result.metadata['page_data'])
            
            # Create page results if needed
            if batch_result.page_results:
                all_page_results.extend(batch_result.page_results)
        
        # Join content with page separators
        merged_content = "\n\n".join(merged_content_parts)
        
        # Create merged metadata
        merged_metadata = {
            "processing_mode": "batch_processing",
            "total_pages": total_pages,
            "batch_count": len(batch_results),
            "images_found": len(all_images),
            "tables_found": len(all_tables),
            "is_ppt_source": is_ppt_converted,
            "page_data": all_page_data if all_page_data else None
        }
        
        self.logger.info(f"mineru-api: merged {len(batch_results)} batches - "
                        f"{len(all_images)} images, {len(all_tables)} tables")
        
        return MinerUResult(
            success=True,
            content=merged_content,
            images=all_images,
            tables=all_tables,
            metadata=merged_metadata,
            page_results=all_page_results if all_page_results else None
        )
    
    def _parse_content_list_to_markdown_batch(self, content_list: Any, temp_dir: str, 
                                             src_fileid: str, page_offset: int) -> Tuple[str, List[str], List[Dict], Dict[int, Dict]]:
        """
        Parse content_list for a batch with page offset adjustment.
        
        Args:
            content_list: Content list from API
            temp_dir: Temporary directory
            src_fileid: Source file ID
            page_offset: Offset to add to page indices
            
        Returns:
            Tuple of (markdown, images, tables, page_data)
        """
        # Parse normally first
        markdown, images, tables, page_data = self._parse_content_list_to_markdown(
            content_list, temp_dir, src_fileid
        )
        
        # Adjust page indices in page_data
        adjusted_page_data = {}
        for page_idx, pdata in page_data.items():
            adjusted_idx = page_idx + page_offset
            adjusted_page_data[adjusted_idx] = pdata
            # Update page number in metadata
            if 'metadata' in pdata:
                pdata['metadata']['page_num'] = adjusted_idx + 1
        
        # Adjust page numbers in tables
        for table in tables:
            if 'page' in table:
                table['page'] += page_offset
        
        return markdown, images, tables, adjusted_page_data
    
    def _parse_content_list_to_markdown(self, content_list: List[Dict], temp_dir: str, src_fileid: str) -> Tuple[str, List[str], List[Dict], Dict[int, Dict]]:
        """
        Parse content_list JSON format to markdown organized by pages.
        
        Args:
            content_list: List of content items with page_idx, type, and content
            temp_dir: Temporary directory for saving images
            src_fileid: Source file ID for logging
            
        Returns:
            Tuple of (markdown_content, image_list, table_list, page_data_dict)
        """
        try:
            import json
            import base64
            
            # If content_list is a string, parse it as JSON
            if isinstance(content_list, str):
                self.logger.info(f"mineru-api: Parsing content_list string of length {len(content_list)}")
                try:
                    content_list = json.loads(content_list)
                    self.logger.info(f"mineru-api: Parsed content_list to {type(content_list)} with {len(content_list) if isinstance(content_list, list) else 'N/A'} items")
                except json.JSONDecodeError as e:
                    self.logger.error(f"mineru-api: Failed to parse content_list JSON: {str(e)}")
                    self.logger.error(f"mineru-api: Content_list sample: {content_list[:500]}")
                    raise
            
            # Log content_list structure
            if isinstance(content_list, list):
                self.logger.info(f"mineru-api: Content list has {len(content_list)} items")
                if content_list:
                    self.logger.debug(f"mineru-api: First item sample: {content_list[0] if content_list else 'None'}")
            else:
                self.logger.warning(f"mineru-api: Content list is not a list, type: {type(content_list)}")
            
            # Group content by page
            page_groups = {}
            for item in content_list:
                page_idx = item.get('page_idx', 0)
                if page_idx not in page_groups:
                    page_groups[page_idx] = []
                page_groups[page_idx].append(item)
            
            # Sort pages
            sorted_pages = sorted(page_groups.keys())
            
            # Build markdown and collect resources
            markdown_parts = []
            all_images = []
            all_tables = []
            page_data = {}
            
            for page_idx in sorted_pages:
                page_num = page_idx + 1  # Convert to 1-based
                page_items = page_groups[page_idx]
                
                # Page header - only add if there's content
                # We'll add this after checking for content
                
                page_content_parts = []
                page_images = []
                page_tables = []
                
                for item in page_items:
                    item_type = item.get('type', 'text')
                    
                    if item_type == 'text':
                        text = item.get('text', '').strip()
                        text_level = item.get('text_level', 0)
                        
                        if text:
                            # Apply heading levels
                            if text_level > 0:
                                # Convert to markdown heading
                                heading_prefix = '#' * min(text_level, 6)
                                page_content_parts.append(f"{heading_prefix} {text}")
                            else:
                                page_content_parts.append(text)
                    
                    elif item_type == 'image':
                        img_path = item.get('img_path', '')
                        img_caption = item.get('img_caption', [])
                        img_footnote = item.get('img_footnote', [])
                        
                        self.logger.info(f"mineru-api: processing image item - img_path: {img_path[:100] if img_path else 'None'}")
                        
                        # Handle image path/data
                        if img_path:
                            if img_path.startswith('data:'):
                                # Base64 encoded image
                                try:
                                    # Extract format and data
                                    header, data = img_path.split(',', 1)
                                    fmt = header.split('/')[1].split(';')[0]
                                    
                                    # Decode and save
                                    img_data = base64.b64decode(data)
                                    img_filename = f"content_list_img_{src_fileid}_p{page_num}_{len(page_images)}.{fmt}"
                                    img_file_path = os.path.join(temp_dir, img_filename)
                                    
                                    with open(img_file_path, 'wb') as f:
                                        f.write(img_data)
                                    
                                    page_images.append(img_filename)
                                    all_images.append(img_filename)
                                    
                                    # Add to markdown
                                    page_content_parts.append(f"![Image]({img_filename})")
                                    
                                except Exception as e:
                                    self.logger.error(f"Failed to decode base64 image: {str(e)}")
                            else:
                                # Regular image path - need to check if it's a file that needs to be created
                                img_filename = os.path.basename(img_path)
                                
                                # For self-hosted API, images might be referenced but not yet saved
                                # We'll add them to the list and expect them to be in the 'images' field
                                page_images.append(img_filename)
                                all_images.append(img_filename)
                                
                                # Use relative path for image reference
                                img_ref = f"images/{img_filename}" if not img_path.startswith('images/') else img_path
                                page_content_parts.append(f"![Image]({img_ref})")
                                self.logger.info(f"mineru-api: added image reference: ![Image]({img_ref})")
                                self.logger.info(f"mineru-api: expecting image file: {img_filename} to be provided by API")
                            
                            # Add captions if present
                            if img_caption:
                                caption_text = ' '.join(img_caption)
                                page_content_parts.append(f"*{caption_text}*")
                            
                            if img_footnote:
                                footnote_text = ' '.join(img_footnote)
                                page_content_parts.append(f"**Note:** {footnote_text}")
                    
                    elif item_type == 'table':
                        table_body = item.get('table_body', '')
                        table_caption = item.get('table_caption', [])
                        table_footnote = item.get('table_footnote', [])
                        
                        # Add table caption
                        if table_caption:
                            caption_text = ' '.join(table_caption)
                            page_content_parts.append(f"**{caption_text}**")
                        
                        # Add table content
                        if table_body:
                            # If HTML table, add directly
                            if table_body.strip().startswith('<'):
                                page_content_parts.append(table_body)
                            else:
                                page_content_parts.append(f"```\n{table_body}\n```")
                        
                        # Add footnote
                        if table_footnote:
                            footnote_text = ' '.join(table_footnote)
                            page_content_parts.append(f"*Note: {footnote_text}*")
                        
                        # Store table data
                        table_data = {
                            'page': page_num,
                            'content': table_body,
                            'caption': table_caption,
                            'footnote': table_footnote
                        }
                        page_tables.append(table_data)
                        all_tables.append(table_data)
                    
                    elif item_type == 'equation':
                        eq_text = item.get('text', '')
                        eq_format = item.get('text_format', 'latex')
                        
                        if eq_text:
                            if eq_format == 'latex':
                                # Use display math for equations
                                page_content_parts.append(f"$$\n{eq_text}\n$$")
                            else:
                                page_content_parts.append(f"```{eq_format}\n{eq_text}\n```")
                
                # Combine page content
                # Filter out empty parts to avoid excessive newlines
                non_empty_parts = [part for part in page_content_parts if part.strip()]
                page_content = '\n'.join(non_empty_parts) if non_empty_parts else ''
                
                # Only add page header and content if there's actual content
                if page_content:
                    markdown_parts.append(f"\n\n## Page {page_num}\n\n")
                    markdown_parts.append(page_content)
                
                # Store page data
                page_data[page_idx] = {
                    'content': page_content,
                    'images': page_images,
                    'tables': page_tables,
                    'metadata': {'page_num': page_num}
                }
            
            # Combine all markdown
            final_markdown = ''.join(markdown_parts)
            
            self.logger.info(f"mineru-api: parsed content_list - {len(sorted_pages)} pages, "
                           f"{len(all_images)} images, {len(all_tables)} tables")
            
            return final_markdown, all_images, all_tables, page_data
            
        except Exception as e:
            self.logger.error(f"mineru-api: content_list parsing failed: {str(e)}")
            raise
    
    def detect_tables(self, content: str) -> bool:
        """
        Detect if content contains table structures.
        
        Based on gzero.py's table detection logic.
        """
        table_indicators = [
            '<table>', '<tr>', '<td>', '|---|', 
            '表格', 'Table', '| ', ' |',
            '┌', '└', '├', '┤'  # Table border characters
        ]
        
        content_lower = content.lower()
        for indicator in table_indicators:
            if indicator.lower() in content_lower:
                return True
        
        # Check for pipe-separated table format
        lines = content.split('\\n')
        pipe_lines = [line for line in lines if line.count('|') >= 2]
        if len(pipe_lines) >= 2:  # At least header and one data row
            return True
            
        return False
    
    async def extract_plain_text(self, pdf_path: str, src_fileid: str) -> str:
        """
        Extract plain text from PDF using PyMuPDF.
        
        This provides text content for comparison with MinerU results.
        """
        try:
            text_parts = []
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    page_text = page.get_text()
                    if page_text.strip():
                        text_parts.append(page_text)
            
            plain_text = '\\n\\n'.join(text_parts)
            
            self.logger.info(f"mineru-api: extracted {len(plain_text)} characters of plain text")
            
            return plain_text
            
        except Exception as e:
            self.logger.error(f"mineru-api: plain text extraction failed: {str(e)}")
            return ""
    
    def merge_content(self, plain_text: str, mineru_content: str, src_fileid: str) -> str:
        """
        Merge plain text with MinerU structured content.
        
        This combines the reliability of plain text extraction with 
        MinerU's structured parsing capabilities.
        """
        try:
            # Simple merge strategy - could be enhanced with more sophisticated logic
            if not mineru_content.strip():
                self.logger.warning(f"mineru-api: MinerU content empty, using plain text")
                return plain_text
            
            if not plain_text.strip():
                self.logger.warning(f"mineru-api: plain text empty, using MinerU content")
                return mineru_content
            
            # For now, prefer MinerU content as it should be more structured
            # In practice, you might want more sophisticated merging logic
            self.logger.info(f"mineru-api: using MinerU structured content")
            return mineru_content
            
        except Exception as e:
            self.logger.error(f"mineru-api: content merge failed: {str(e)}")
            # Fallback to plain text
            return plain_text if plain_text else mineru_content