"""
Image processing module for MinerU-based parsing.

This module handles image recognition, classification, and processing
using multimodal AI models, following patterns from gzero.py.
"""

import os
import json
import base64
import asyncio
import time
import io
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from .logger import get_module_logger
logger = get_module_logger('image_processor')
import tiktoken

from .config_base import MinerUConfig
from .context_types import ImageContext, ContentElement, PageContext
from .prompts import format_image_classification_prompt
from .language_detector import LanguageDetector
from .image_optimizer import ImageOptimizer


@dataclass
class ImageProcessingResult:
    """Result from image processing operations"""
    success: bool
    processed_images: Dict[str, str]  # filename -> uploaded_url
    image_descriptions: Dict[str, Dict]  # filename -> classification_result
    error: Optional[str] = None


class MinerUImageProcessor:
    """Image processing handler for MinerU pipeline"""
    
    def __init__(self, config: MinerUConfig):
        self.config = config
        self.logger = logger
        self.image_optimizer = None
        self.platform_adapter = None  # Will be set by parser if available
        
    async def initialize(self):
        """Initialize image optimizer"""
        self.image_optimizer = ImageOptimizer(
            max_concurrent_uploads=self.config.max_concurrent_uploads,
            max_concurrent_api_calls=self.config.max_concurrent_api_calls,
            max_image_size_mb=self.config.max_image_size_mb,
            compression_quality=self.config.compression_quality,
            upload_max_retries=self.config.upload_max_retries,
            upload_retry_delay=self.config.upload_retry_delay
        )
    
    async def cleanup(self):
        """Cleanup image optimizer resources"""
        if self.image_optimizer:
            await self.image_optimizer.cleanup()
    
    def _should_skip_recognition(self, image_path: str) -> Tuple[bool, str]:
        """
        Check if an image should skip AI recognition based on size and dimensions.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Tuple of (should_skip, reason)
        """
        try:
            # Check file size
            file_size = os.path.getsize(image_path)
            file_size_kb = file_size / 1024
            
            if file_size_kb < self.config.min_image_size_kb:
                return True, f"File size too small: {file_size_kb:.1f}KB < {self.config.min_image_size_kb}KB"
            
            # Check image dimensions using PIL
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
                
                # Check minimum dimensions
                if width < self.config.min_image_width or height < self.config.min_image_height:
                    return True, f"Image too small: {width}x{height} < {self.config.min_image_width}x{self.config.min_image_height}"
                
                # Check maximum dimensions
                if width > self.config.max_image_width or height > self.config.max_image_height:
                    return True, f"Image too large: {width}x{height} > {self.config.max_image_width}x{self.config.max_image_height}"
            
            return False, "Image meets all requirements"
            
        except Exception as e:
            self.logger.error(f"mineru-image: error checking image {image_path}: {str(e)}")
            return False, f"Error checking image: {str(e)}"
    
    def filter_images_by_limits(self, images: List[str], temp_dir: str, 
                                page_idx: Optional[int] = None,
                                total_pages: int = 1) -> Tuple[List[str], List[str]]:
        """
        Filter images based on configured limits (similar to gzero.py).
        
        Args:
            images: List of image filenames
            temp_dir: Directory containing images
            page_idx: Current page index (for per-page filtering)
            total_pages: Total number of pages in document
            
        Returns:
            Tuple of (selected_images, filtered_out_images)
        """
        # If no images, return empty lists
        if not images:
            return [], []
        
        # Sort images by size (larger first, like gzero.py)
        image_info = []
        for img_filename in images:
            img_path = os.path.join(temp_dir, img_filename)
            try:
                # Get image size
                from PIL import Image
                with Image.open(img_path) as img:
                    width, height = img.size
                    area = width * height
                    file_size = os.path.getsize(img_path)
                    
                    image_info.append({
                        'filename': img_filename,
                        'area': area,
                        'width': width,
                        'height': height,
                        'file_size': file_size
                    })
            except Exception as e:
                self.logger.warning(f"mineru-image: failed to get info for {img_filename}: {e}")
                # Include failed images with minimal info
                image_info.append({
                    'filename': img_filename,
                    'area': 0,
                    'width': 0,
                    'height': 0,
                    'file_size': 0
                })
        
        # Sort by area (largest first) then by file size
        image_info.sort(key=lambda x: (x['area'], x['file_size']), reverse=True)
        
        # Apply size filters
        filtered_images = []
        for info in image_info:
            # Check minimum size
            if info['area'] < self.config.min_image_size:
                self.logger.debug(f"mineru-image: filtering out {info['filename']} - too small ({info['area']} pixels)")
                continue
            
            # Check maximum size
            if info['area'] > self.config.max_image_size:
                self.logger.debug(f"mineru-image: filtering out {info['filename']} - too large ({info['area']} pixels)")
                continue
            
            # Check dimensions
            if info['width'] < self.config.min_image_width or info['height'] < self.config.min_image_height:
                self.logger.debug(f"mineru-image: filtering out {info['filename']} - dimensions too small")
                continue
            
            if info['width'] > self.config.max_image_width or info['height'] > self.config.max_image_height:
                self.logger.debug(f"mineru-image: filtering out {info['filename']} - dimensions too large")
                continue
            
            filtered_images.append(info)
        
        # Apply per-page limit (similar to gzero.py's probe_page_thres)
        if page_idx is not None:
            # For individual pages, apply per-page limit
            page_limit = self.config.max_images_per_page
            if len(filtered_images) > page_limit:
                self.logger.info(f"mineru-image: page {page_idx + 1} has {len(filtered_images)} images, limiting to {page_limit}")
                selected = filtered_images[:page_limit]
                filtered_out = filtered_images[page_limit:]
            else:
                selected = filtered_images
                filtered_out = []
        else:
            # For document-level processing, apply document limit
            doc_limit = min(self.config.max_images_per_document, 
                          total_pages * self.config.max_images_per_page)
            if len(filtered_images) > doc_limit:
                self.logger.info(f"mineru-image: document has {len(filtered_images)} images, limiting to {doc_limit}")
                selected = filtered_images[:doc_limit]
                filtered_out = filtered_images[doc_limit:]
            else:
                selected = filtered_images
                filtered_out = []
        
        # Extract filenames
        selected_files = [info['filename'] for info in selected]
        filtered_out_files = [info['filename'] for info in filtered_out] + \
                           [img for img in images if img not in [i['filename'] for i in image_info]]
        
        self.logger.info(f"mineru-image: selected {len(selected_files)} images, filtered out {len(filtered_out_files)}")
        
        return selected_files, filtered_out_files
    
    async def process_images(self, images: List[str], temp_dir: str, src_fileid: str,
                           learn_type: int, upload_callback, upload_options,
                           page_contexts: Optional[List[PageContext]] = None,
                           content_list: Optional[List[Dict]] = None,
                           page_idx: Optional[int] = None,
                           source_text: Optional[str] = None,
                           language_code: Optional[str] = None) -> ImageProcessingResult:
        """
        Process images: classify, recognize content, and upload.
        
        Args:
            images: List of image filenames
            temp_dir: Temporary directory containing images
            src_fileid: Source file ID for logging
            learn_type: Model type for AI processing
            upload_callback: Function to upload images
            upload_options: Upload configuration
            page_contexts: Optional page context information
            content_list: Optional content list from MinerU
            page_idx: Optional page index for page-specific processing
            source_text: Optional source text for language detection
            language_code: Optional language code (will override detection)
            
        Returns:
            ImageProcessingResult with processed images and descriptions
        """
        try:
            if not self.image_optimizer:
                await self.initialize()
                
            # Apply image filtering first (similar to gzero.py)
            total_pages = 1  # Default, should be provided in metadata if available
            if page_contexts:
                total_pages = len(page_contexts)
            
            selected_images, filtered_out_images = self.filter_images_by_limits(
                images, temp_dir, page_idx, total_pages
            )
            
            if filtered_out_images:
                self.logger.info(f"mineru-image: filtered out {len(filtered_out_images)} images due to limits")
            
            page_info = f" for page {page_idx + 1}" if page_idx is not None else ""
            self.logger.info(f"mineru-image:  processing {len(selected_images)} images{page_info} (after filtering)")
            
            # Use provided language code or detect from source text
            if not language_code and source_text:
                detected_code, confidence = LanguageDetector.detect_language(source_text)
                if confidence > 0.7:  # Only use detected language if confidence is high
                    language_code = detected_code
                    self.logger.info(f"mineru-image: detected language: {language_code} (confidence: {confidence:.2f})")
            
            if language_code:
                self.logger.info(f"mineru-image: will generate descriptions in {LanguageDetector.get_language_name(language_code)}")
            else:
                self.logger.info(f"mineru-image: no language specified, will use default")
            
            # Step 1: Load image information and filter based on size/dimensions
            images_to_process = []
            images_skipped = []  # Images that don't need AI recognition
            
            for img_filename in selected_images:
                img_filepath = os.path.join(temp_dir, img_filename)
                if os.path.exists(img_filepath):
                    # Check if image should skip recognition
                    if self.config.skip_recognition_for_small_images:
                        should_skip, reason = self._should_skip_recognition(img_filepath)
                        if should_skip:
                            self.logger.info(f"mineru-image: skipping recognition for {img_filename}: {reason}")
                            # Still add to skipped list for upload without AI processing
                            xref = img_filename.replace('.png', '').replace('mineru_image_', '')
                            image_info = await self.image_optimizer.load_image_info(
                                img_filepath, img_filename, xref
                            )
                            images_skipped.append(image_info)
                            continue
                    
                    # Use filename as xref for consistency
                    xref = img_filename.replace('.png', '').replace('mineru_image_', '')
                    image_info = await self.image_optimizer.load_image_info(
                        img_filepath, img_filename, xref
                    )
                    images_to_process.append(image_info)
                else:
                    self.logger.warning(f"mineru-image:  image file not found: {img_filepath}")
            
            if not images_to_process and not images_skipped:
                self.logger.warning(f"mineru-image:  no valid images to process")
                return ImageProcessingResult(success=True, processed_images={}, image_descriptions={})
            
            # Step 2: Extract context for images if available
            image_contexts = {}
            if page_contexts and content_list:
                self.logger.info("mineru-image: extracting context for images")
                for img_info in images_to_process:
                    context = self._extract_image_context(
                        img_info.filename, content_list, page_contexts
                    )
                    if context:
                        image_contexts[img_info.xref] = context
            
            # Step 3: Classify images using AI with context
            self.logger.info(f"mineru-image:  classifying {len(images_to_process)} images sequentially")
            
            # Create a wrapper to pass context and language to classification
            async def classify_with_context(learn_type, image_filepath: str, temp_dir: str,
                                          src_name: str, hint: str = "") -> Dict:
                # Extract xref from image filepath
                filename = os.path.basename(image_filepath)
                xref = filename.replace('.png', '').replace('mineru_image_', '')
                context = image_contexts.get(xref)
                return await self._classify_single_image_with_context(
                    learn_type, image_filepath, temp_dir, src_name, hint, context, language_code
                )
            
            # Note: batch_classify_images now processes images sequentially to avoid pressure on multimodal service
            classification_results = await self.image_optimizer.batch_classify_images(
                images_to_process,
                classify_with_context,
                learn_type,  # Pass the learn_type instead of model_config
                temp_dir,
                src_fileid
            )
            
            # Step 4: Filter meaningful images
            meaningful_images = []
            meaningful_classifications = {}
            
            for image_info in images_to_process:
                filename = image_info.filename
                xref = image_info.xref
                
                if xref in classification_results:
                    result = classification_results[xref]
                    
                    # Apply meaningless filter if configured
                    if self.config.filter_meaningless_images and result.get('type') == 'meaningless':
                        self.logger.info(f"mineru-image:  image {filename} classified as meaningless, filtering out")
                        # Store classification but don't add to meaningful_images
                        meaningful_classifications[filename] = result
                    else:
                        # Either filter is disabled or image is meaningful
                        meaningful_images.append(image_info)
                        meaningful_classifications[filename] = result
                        self.logger.info(f"mineru-image:  image {filename} classified as {result.get('type')}, keeping")
            
            if self.config.filter_meaningless_images:
                self.logger.info(f"mineru-image:  filtered to {len(meaningful_images)} meaningful images (meaningless filter enabled)")
            else:
                self.logger.info(f"mineru-image:  keeping all {len(meaningful_images)} classified images (meaningless filter disabled)")
            
            # Step 5: Upload meaningful images and skipped images
            uploaded_images = {}
            all_images_to_upload = meaningful_images + images_skipped
            
            if all_images_to_upload:
                self.logger.info(f"mineru-image:  uploading {len(all_images_to_upload)} images ({len(meaningful_images)} with AI, {len(images_skipped)} without AI)")
                self.logger.info(f"mineru-image:  upload_callback={upload_callback}, upload_options={upload_options}")
                
                upload_results = await self.image_optimizer.batch_upload_images(
                    all_images_to_upload,
                    upload_callback,
                    upload_options
                )
                
                self.logger.info(f"mineru-image:  upload_results: {upload_results}")
                
                # Map results back to filenames
                for image_info in all_images_to_upload:
                    xref = image_info.xref
                    self.logger.info(f"mineru-image:  checking upload result for {image_info.filename} (xref={xref})")
                    if xref in upload_results and upload_results[xref]:
                        uploaded_images[image_info.filename] = upload_results[xref]
                        self.logger.info(f"mineru-image:  uploaded {image_info.filename} -> {upload_results[xref]}")
                    else:
                        self.logger.warning(f"mineru-image:  upload failed for {image_info.filename}")
            
            # For skipped images, add a simple description
            for image_info in images_skipped:
                if image_info.filename in uploaded_images:
                    meaningful_classifications[image_info.filename] = {
                        'type': 'skipped',
                        'content': 'Image skipped due to size/dimension filters',
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'dura': 0.0
                    }
            
            return ImageProcessingResult(
                success=True,
                processed_images=uploaded_images,
                image_descriptions=meaningful_classifications
            )
            
        except Exception as e:
            self.logger.error(f"mineru-image:  image processing failed: {str(e)}")
            return ImageProcessingResult(
                success=False,
                processed_images={},
                image_descriptions={},
                error=str(e)
            )
    
    def _extract_image_context(self, image_filename: str, content_list: List[Dict],
                             page_contexts: List[PageContext]) -> Optional[ImageContext]:
        """
        Extract context information for an image from the content list.
        
        Args:
            image_filename: The image filename
            content_list: MinerU content list with page_idx and type
            page_contexts: List of page context information
            
        Returns:
            ImageContext object or None if not found
        """
        try:
            # Find the image in content list
            image_page_idx = None
            image_position = None
            
            for idx, item in enumerate(content_list):
                if item.get('type') == 'image' and image_filename in str(item.get('img_path', '')):
                    image_page_idx = item.get('page_idx', 0)
                    image_position = idx
                    break
            
            if image_page_idx is None:
                return None
            
            # Get page context
            page_context = None
            for pc in page_contexts:
                if pc.page_idx == image_page_idx:
                    page_context = pc
                    break
            
            if not page_context:
                return None
            
            # Extract surrounding text with configurable window
            window_size = self.config.context_window_size if hasattr(self.config, 'context_window_size') else 2
            surrounding_text = self._extract_surrounding_text(
                content_list, image_position, window_size, image_page_idx
            )
            
            # Get before and after text from page
            before_text, after_text = "", ""
            if hasattr(page_context, 'get_text_around_position'):
                before_text, after_text = page_context.get_text_around_position(image_position)
            
            # Count tokens
            token_count = self._count_tokens(surrounding_text)
            
            return ImageContext(
                page_idx=image_page_idx,
                surrounding_text=surrounding_text,
                page_type=page_context.page_type if page_context else 'content',
                chunk_idx=image_position,
                token_count=token_count,
                before_text=before_text,
                after_text=after_text,
                page_title=page_context.title if page_context else None
            )
            
        except Exception as e:
            self.logger.error(f"mineru-image: failed to extract context for {image_filename}: {str(e)}")
            return None
    
    def _extract_surrounding_text(self, content_list: List[Dict], position: int,
                                window_size: int, target_page_idx: int) -> str:
        """
        Extract text content around a specific position in the content list.
        """
        texts = []
        
        # Look backward
        for i in range(max(0, position - window_size), position):
            item = content_list[i]
            if item.get('page_idx') == target_page_idx and item.get('type') == 'text':
                text = item.get('text', '').strip()
                if text:
                    texts.append(f"[Before] {text}")
        
        # Look forward
        for i in range(position + 1, min(len(content_list), position + window_size + 1)):
            item = content_list[i]
            if item.get('page_idx') == target_page_idx and item.get('type') == 'text':
                text = item.get('text', '').strip()
                if text:
                    texts.append(f"[After] {text}")
        
        return '\n'.join(texts)
    
    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.
        """
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # Fallback to character-based estimation
            return len(text) // 4
    
    async def _classify_single_image_with_context(self, learn_type, image_filepath: str, temp_dir: str,
                                                src_name: str, hint: str = "",
                                                context: Optional[ImageContext] = None,
                                                language_code: Optional[str] = None) -> Dict:
        """
        Classify a single image using multimodal AI with optional context.
        
        This is an enhanced version that uses context when available.
        """
        self.logger.info(f"mineru-image: _classify_single_image_with_context called for {os.path.basename(image_filepath)}")
        
        # If no context, fall back to original method
        if not context:
            self.logger.info(f"mineru-image: no context, falling back to original method")
            return await self._classify_single_image(learn_type, image_filepath, temp_dir, src_name, hint)
        
        try:
            self.logger.info(f"mineru-image: processing with context for {os.path.basename(image_filepath)}")
            
            if not os.path.exists(image_filepath):
                raise FileNotFoundError(f"Image file not found: {image_filepath}")
            
            with open(image_filepath, 'rb') as file:
                image_data = file.read()
            
            # Use BytesIO to avoid blocking the event loop
            image_buffer = io.BytesIO(image_data)
            image_base64 = base64.b64encode(image_buffer.getvalue()).decode("utf-8")
            
            # Build context-aware prompt with language
            prompt = self._build_context_aware_prompt(context, language_code)
            
            # Log the final prompt for debugging
            self.logger.info(f"mineru-image: Final prompt for {os.path.basename(image_filepath)}:\n{prompt[:1000]}...")
            
            messages = [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': '请分析这张图片并按照要求输出JSON格式结果。'},
                    {'type': 'image_url', 'image_url': {
                        'url': f"data:image/png;base64,{image_base64}"
                    }}
                ]}
            ]
            
            # Call litellm using unified helper
            start_time = time.time()
            
            try:
                self.logger.info(f"mineru-image: calling vision model for {os.path.basename(image_filepath)}")
                response = await self.config.call_litellm(
                    model_type=learn_type,
                    messages=messages,
                    temperature=0.0,
                    timeout=120.0  # Increased timeout to 120 seconds for vision models
                )
                self.logger.info(f"mineru-image: received response from vision model")
                
                duration = time.time() - start_time
                
                # Log raw response for debugging
                raw_response = response.choices[0].message.content if response.choices else ""
                self.logger.info(f"mineru-image: raw AI response (first 500 chars): {raw_response[:500] if raw_response else 'Empty response'}")
                # Log complete response for debugging
                self.logger.info(f"mineru-image: FULL AI response for {os.path.basename(image_filepath)}:\n{raw_response}")
                
                # Log usage info
                if hasattr(response, 'usage'):
                    self.logger.info(f"mineru-image: usage - prompt_tokens={getattr(response.usage, 'prompt_tokens', 0)}, "
                                   f"completion_tokens={getattr(response.usage, 'completion_tokens', 0)}")
                else:
                    self.logger.warning(f"mineru-image: no usage info in response")
                
                # Parse enhanced response
                result = self._parse_context_aware_response(
                    raw_response,
                    response.usage if hasattr(response, 'usage') else None,
                    duration
                )
                
                # Add context information to result
                result['has_context'] = True
                result['page_idx'] = context.page_idx
                
                # Log successful classification
                self.logger.info(f"mineru-image: classified {os.path.basename(image_filepath)} as {result.get('type', 'unknown')} "
                                f"(tokens: in={result.get('input_tokens', 0)}, out={result.get('output_tokens', 0)})")
                
            except Exception as e:
                self.logger.error(f"mineru-image: classification error: {str(e)}")
                self.logger.info(f"mineru-image: classification failed for {os.path.basename(image_filepath)}, returning meaningless")
                result = {
                    'type': 'meaningless',
                    'content': f'Classification error: {str(e)}',
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'dura': time.time() - start_time,
                    'has_context': True,
                    'error': str(e)
                }
            
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-image: context classification failed: {str(e)}")
            # Fall back to non-context classification
            return await self._classify_single_image(learn_type, image_filepath, temp_dir, src_name, hint)
    
    def _build_context_aware_prompt(self, context: ImageContext, language_code: Optional[str] = None) -> str:
        """
        Build an enhanced prompt that includes context information and language instruction.
        """
        # Format page title info
        page_title_info = ""
        if context.page_title:
            page_title_info = f"页面标题：{context.page_title}"
        
        # Truncate surrounding text if too long
        max_context_tokens = getattr(self.config, 'max_context_tokens', 1000)
        surrounding_text = self._truncate_text_by_tokens(context.surrounding_text, max_context_tokens)
        
        # Build context dictionary
        context_data = {
            'page_idx': context.page_idx + 1,  # Human-readable page number
            'page_type': context.page_type,
            'page_title_info': page_title_info,
            'surrounding_text': surrounding_text
        }
        
        # Check if we have text content for language detection
        has_text_content = bool(context.surrounding_text and context.surrounding_text.strip())
        
        # Use the optimized prompt with context and language
        return format_image_classification_prompt(context=context_data, language_code=language_code, has_text_content=has_text_content)
    
    def _truncate_text_by_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to fit within token limit.
        """
        if not text:
            return ""
        
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            tokens = encoding.encode(text)
            
            if len(tokens) <= max_tokens:
                return text
            
            # Truncate and decode
            truncated_tokens = tokens[:max_tokens]
            return encoding.decode(truncated_tokens) + "...[已截断]"
        except:
            # Fallback to character-based truncation
            char_limit = max_tokens * 4
            if len(text) > char_limit:
                return text[:char_limit] + "...[已截断]"
            return text
    
    def _parse_context_aware_response(self, response_content: str, usage: Any, duration: float) -> Dict:
        """
        Parse the enhanced response from context-aware classification.
        """
        try:
            # Extract JSON from markdown if present
            if '```json' in response_content and '```' in response_content:
                json_start = response_content.find('```json') + 7
                json_end = response_content.find('```', json_start)
                response_content = response_content[json_start:json_end].strip()
            
            # Parse JSON
            result_json = json.loads(response_content)
            
            # Log the raw classification response for debugging
            self.logger.info(f"mineru-image: parsed JSON response: {result_json}")
            
            # Build result dictionary
            result = {
                'type': result_json.get('type', 'meaningless'),
                'title': result_json.get('title', ''),
                'content': result_json.get('description', ''),
                'input_tokens': usage.prompt_tokens if usage and hasattr(usage, 'prompt_tokens') else 0,
                'output_tokens': usage.completion_tokens if usage and hasattr(usage, 'completion_tokens') else 0,
                'dura': duration
            }
            
            # Add OCR content if available
            if result_json.get('ocr_content'):
                result['ocr_content'] = result_json['ocr_content']
            
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-image: failed to parse context response: {str(e)}")
            self.logger.debug(f"mineru-image: response that failed to parse: {response_content[:500] if response_content else 'Empty'}")
            # Return a basic result
            return {
                'type': 'brief_description',
                'title': '',
                'content': response_content[:200] if response_content else '',
                'input_tokens': usage.prompt_tokens if usage and hasattr(usage, 'prompt_tokens') else 0,
                'output_tokens': usage.completion_tokens if usage and hasattr(usage, 'completion_tokens') else 0,
                'dura': duration
            }
    
    async def _classify_single_image(self, learn_type, image_filepath: str, temp_dir: str,
                                   src_name: str, hint: str = "") -> Dict:
        """
        Classify a single image using multimodal AI.
        
        This follows the gzero.py pattern for image classification.
        
        Args:
            learn_type: The learn type for model selection
            image_filepath: Path to the image file to classify
            temp_dir: Temporary directory (currently unused but kept for API compatibility)
            src_name: Source name (currently unused but kept for API compatibility) 
            hint: Additional hint for classification (currently unused but kept for API compatibility)
        """
        try:
            if not os.path.exists(image_filepath):
                raise FileNotFoundError(f"Image file not found: {image_filepath}")
            
            with open(image_filepath, 'rb') as file:
                image_data = file.read()
            
            # Use BytesIO to avoid blocking the event loop
            image_buffer = io.BytesIO(image_data)
            image_base64 = base64.b64encode(image_buffer.getvalue()).decode("utf-8")
            
            # Use the optimized prompt without context
            # For simple classification, we don't have text content
            prompt = format_image_classification_prompt(context=None, language_code=None, has_text_content=False)
            
            messages = [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': '请分析这张图片并按照要求输出JSON格式结果。'},
                    {'type': 'image_url', 'image_url': {
                        'url': f"data:image/png;base64,{image_base64}"
                    }}
                ]}
            ]
            
            # Call litellm using unified helper
            start_time = time.time()
            
            try:
                # Set timeout to avoid long waits
                response = await self.config.call_litellm(
                    model_type=learn_type,
                    messages=messages,
                    temperature=0.0,
                    timeout=120.0  # Increased timeout to 120 seconds for vision models
                )
                
                duration = time.time() - start_time
                
                # Parse response
                response_content = response.choices[0].message.content
                
                # Log complete response for debugging
                self.logger.info(f"mineru-image: FULL AI response for {os.path.basename(image_filepath)} (no context):\n{response_content}")
                
                # Extract JSON from markdown code block if present
                if '```json' in response_content and '```' in response_content:
                    try:
                        json_start = response_content.find('```json') + 7
                        json_end = response_content.find('```', json_start)
                        response_content = response_content[json_start:json_end].strip()
                    except:
                        pass
                
                # Try to parse JSON response
                try:
                    result_json = json.loads(response_content)
                    img_type = result_json.get('type', 'meaningless')
                    title = result_json.get('title', '')
                    description = result_json.get('description', '')
                    ocr_content = result_json.get('ocr_content', '')
                except json.JSONDecodeError:
                    # Fallback parsing if not valid JSON
                    if 'structured_content' in response_content:
                        img_type = 'structured_content'
                    elif 'brief_description' in response_content:
                        img_type = 'brief_description'
                    else:
                        img_type = 'meaningless'
                    title = ''
                    description = response_content
                    ocr_content = ''  # Default value for fallback case
                
                result = {
                    'type': img_type,
                    'content': description,
                    'input_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                    'output_tokens': response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                    'dura': duration,
                }
                # Add title if it exists
                if title:
                    result['title'] = title
                # Only add ocr_content if it exists
                if ocr_content:
                    result['ocr_content'] = ocr_content
                
            except asyncio.TimeoutError:
                self.logger.warning(f"mineru-image: classification timeout for {image_filepath}")
                result = {
                    'type': 'meaningless',
                    'content': 'Classification timeout',
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'dura': time.time() - start_time,
                }
            except Exception as e:
                self.logger.error(f"mineru-image: classification error for {image_filepath}: {str(e)}")
                result = {
                    'type': 'meaningless',
                    'content': f'Classification error: {str(e)}',
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'dura': time.time() - start_time,
                }
            
            # Enhanced logging to debug meaningless classification
            self.logger.info(f"mineru-image: classified {image_filepath} as {result.get('type', 'unknown')} - tokens: in={result.get('input_tokens', 0)}, out={result.get('output_tokens', 0)}, error={result.get('error', 'None')}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"mineru-image: image classification failed for {image_filepath}: {str(e)}")
            return {
                'type': 'meaningless',
                'content': '',
                'input_tokens': 0,
                'output_tokens': 0,
                'dura': 0.0,
                'error': str(e)
            }
    
    def integrate_image_descriptions(self, content: str, image_descriptions: Dict[str, Dict], 
                                   uploaded_images: Dict[str, str], src_fileid: str) -> str:
        """
        Integrate image descriptions into content by replacing original image references.
        
        Args:
            content: Original content with image references like ![](images/xxxxx.jpg)
            image_descriptions: Image classification results
            uploaded_images: Mapping of filename to uploaded URL
            src_fileid: Source file ID for logging
            
        Returns:
            Content with replaced image descriptions
        """
        import re
        
        try:
            enhanced_content = content
            
            # Log the image descriptions we're working with
            self.logger.info(f"mineru-image:  integrate_image_descriptions called:")
            self.logger.info(f"  - {len(image_descriptions)} image descriptions: {list(image_descriptions.keys())}")
            self.logger.info(f"  - {len(uploaded_images)} uploaded images: {list(uploaded_images.keys())}")
            self.logger.info(f"  - src_fileid: {src_fileid}")
            self.logger.debug(f"  - content length: {len(content)} chars")
            
            # Create a mapping of processed images with their enhanced markdown
            image_replacements = {}
            
            for filename, description_data in image_descriptions.items():
                img_url = uploaded_images.get(filename, f"placeholder_{filename}")
                
                # Extract title
                title = description_data.get('title', '')
                
                # Limit title length
                if title and len(title) > 15:
                    title = title[:15] + "..."
                
                if description_data['type'] == 'skipped':
                    # For skipped images, just keep the original image reference with URL
                    img_markdown = f"![Image]({img_url})"
                    
                elif description_data['type'] == 'structured_content':
                    # Parse structured content
                    description = description_data.get('content', '')
                    ocr_content = description_data.get('ocr_content', '')
                    
                    # Escape quotes in description
                    if description:
                        description = description.replace('"', '\\"')
                    
                    # Use title or default
                    if not title:
                        title = "Structured content image"
                    
                    if description:
                        img_markdown = f"![{title}]({img_url})\n<!--{description}-->\n"
                        if ocr_content:
                            img_markdown += f"\n\n{ocr_content}"
                    elif ocr_content:
                        img_markdown = f"![{title}]({img_url})\n\n{ocr_content}"
                    else:
                        img_markdown = f"![{title}]({img_url})"
                        
                elif description_data['type'] == 'brief_description':
                    description = description_data.get('content', '')
                    
                    # Escape quotes in description
                    if description:
                        description = description.replace('"', '\\"')
                    
                    # Use title or default
                    if not title:
                        title = "Image"
                    
                    if description:
                        img_markdown = f"![{title}]({img_url})\n<!--{description}-->\n"
                    else:
                        img_markdown = f"![{title}]({img_url})"
                    
                else:
                    # Default format for meaningless type
                    img_markdown = f"![Image]({img_url})"
                
                image_replacements[filename] = img_markdown
                self.logger.info(f"mineru-image:  prepared replacement for {filename}: {img_markdown[:100]}...")
            
            # Replace original image references with enhanced versions
            # Pattern to match ![any_text](images/filename) or ![](images/filename)
            def replace_image_reference(match):
                full_match = match.group(0)
                image_path = match.group(2)
                
                # Extract filename from path (e.g., "images/xxxxx.jpg" -> "xxxxx.jpg")
                filename = image_path.split('/')[-1]
                
                # Direct match first
                if filename in image_replacements:
                    self.logger.info(f"mineru-image:  FOUND direct match for {filename}")
                    self.logger.info(f"mineru-image:  replacing '{full_match}' with '{image_replacements[filename][:100]}...'")
                    return image_replacements[filename]
                
                # Try to find a match by checking if any key ends with the filename
                # This handles cases where the stored key has a prefix
                for stored_filename, replacement in image_replacements.items():
                    if stored_filename.endswith(filename) or filename.endswith(stored_filename):
                        self.logger.info(f"mineru-image:  replacing reference for {filename} (matched with {stored_filename})")
                        return replacement
                
                # Also try matching by partial filename patterns
                # Handle case where filename might be like "mineru_image_1.png" 
                # and we have "17888edb327f3b95ee826f5d02a9c264_page_1_afc32c3bbdbe2eafb44ebb66c01028fedb5523292bb954eb58154392aa447ebf.jpg"
                filename_base = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '')
                for stored_filename, replacement in image_replacements.items():
                    if filename_base in stored_filename:
                        self.logger.info(f"mineru-image:  replacing reference for {filename} (partial match with {stored_filename})")
                        return replacement
                
                # Keep original if no replacement available
                self.logger.warning(f"mineru-image:  no replacement found for {filename} in image_replacements")
                self.logger.info(f"mineru-image:  available replacements: {list(image_replacements.keys())}")
                return full_match
            
            # Regex pattern to match markdown image syntax: ![alt_text](path)
            # This handles both ![](images/xxx.jpg) and ![alt text](images/xxx.jpg)
            image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            
            # Log all image references found in content for debugging
            import re
            found_images = re.findall(image_pattern, enhanced_content)
            if found_images:
                self.logger.info(f"mineru-image:  found {len(found_images)} image references in content")
                for alt_text, img_path in found_images[:10]:  # Log first 10
                    self.logger.info(f"mineru-image:  image reference: ![{alt_text}]({img_path})")
            else:
                self.logger.warning(f"mineru-image:  NO image references found in content!")
            
            enhanced_content = re.sub(image_pattern, replace_image_reference, enhanced_content)
            
            # Log summary of replacements
            self.logger.info(f"mineru-image:  completed image integration, processed {len(image_replacements)} images")
            
            return enhanced_content
            
        except Exception as e:
            self.logger.error(f"mineru-image:  image description integration failed: {str(e)}")
            return content
    
    def create_image_references(self, image_descriptions: Dict[str, Dict], 
                              uploaded_images: Dict[str, str]) -> Dict[str, str]:
        """
        Create image reference placeholders for content replacement.
        
        Returns:
            Dictionary mapping placeholder to final image markdown
        """
        image_refs = {}
        
        for filename, description_data in image_descriptions.items():
            img_url = uploaded_images.get(filename, f"placeholder_{filename}")
            placeholder = f"[===[{filename}]===]"
            
            # Extract title
            title = description_data.get('title', '')
            
            # Limit title length
            if title and len(title) > 15:
                title = title[:15] + "..."
            
            if description_data['type'] == 'skipped':
                # For skipped images, just keep the original image reference
                img_markdown = f"![Image]({img_url})"
                
            elif description_data['type'] == 'structured_content':
                try:
                    # Try to parse as JSON if content is JSON string
                    content_data = description_data
                    if isinstance(description_data.get('content'), str) and description_data['content'].startswith('{'):
                        try:
                            content_data = json.loads(description_data['content'])
                        except:
                            pass
                    
                    description = content_data.get('description', content_data.get('content', ''))
                    ocr_content = content_data.get('ocr_content', description_data.get('ocr_content', ''))
                    
                    # Escape quotes in description
                    if description:
                        description = description.replace('"', '\\"')
                    
                    # Use title or default
                    if not title:
                        title = "Structured content image"
                    
                    if description:
                        img_markdown = f"![{title}]({img_url})\n<!--{description}-->\n"
                        if ocr_content:
                            img_markdown += f"\n\n{ocr_content}"
                    elif ocr_content:
                        img_markdown = f"![{title}]({img_url})\n\n{ocr_content}"
                    else:
                        img_markdown = f"![{title}]({img_url})"
                        
                except Exception as e:
                    img_markdown = f"![Structured content image]({img_url})"
                    
            elif description_data['type'] == 'brief_description':
                description = description_data.get('content', '')
                
                # Escape quotes in description
                if description:
                    description = description.replace('"', '\\"')
                
                # Use title or default
                if not title:
                    title = "Image"
                
                if description:
                    img_markdown = f"![{title}]({img_url})\n<!--{description}-->\n"
                else:
                    img_markdown = f"![{title}]({img_url})"
                
            else:
                img_markdown = f"![Image]({img_url})"
            
            image_refs[placeholder] = img_markdown
            
        return image_refs