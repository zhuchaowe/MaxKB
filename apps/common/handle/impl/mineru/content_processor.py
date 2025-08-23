"""
Content processing module for MinerU-based parsing.

This module handles table detection, content fusion, and LLM-based
content refinement, following patterns from gzero.py.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from .logger import get_module_logger
logger = get_module_logger('content_processor')
import tiktoken

import json
import os
import re
import io
from bs4 import BeautifulSoup
from .config_base import MinerUConfig
from .api_client import MinerUResult
from .context_types import ContentElement, PageContext, ContextMode
from .prompts.markdown_generation import format_markdown_generation_prompt
from .language_detector import LanguageDetector


@dataclass
class ContentProcessingResult:
    """Result from content processing operations"""
    success: bool
    processed_content: str
    has_tables: bool
    processing_metadata: Dict
    error: Optional[str] = None


class MinerUContentProcessor:
    """Content processor for handling tables and content fusion"""
    
    def __init__(self, config: MinerUConfig):
        self.config = config
        self.logger = logger
    
    def detect_tables(self, content: str, _src_fileid: str) -> bool:
        """
        Detect if content contains table structures.
        
        Based on gzero.py's table detection logic.
        """
        table_indicators = [
            '<table>', '<tr>', '<td>', '|---|', 
            '表格', 'Table', '| ', ' |',
            '┌', '└', '├', '┤',  # Table border characters
            '═', '║', '╔', '╗', '╚', '╝'  # More table characters
        ]
        
        content_lower = content.lower()
        found_indicators = []
        
        for indicator in table_indicators:
            if indicator.lower() in content_lower:
                found_indicators.append(indicator)
        
        # Check for pipe-separated table format
        lines = content.split('\n')
        pipe_lines = [line for line in lines if line.count('|') >= 2]
        has_pipe_table = len(pipe_lines) >= 2  # At least header and one data row
        
        has_tables = bool(found_indicators) or has_pipe_table
        
        if has_tables:
            self.logger.info(f"mineru-content:  tables detected - indicators: {found_indicators}, pipe_lines: {len(pipe_lines)}")
        else:
            self.logger.info(f"mineru-content:  no tables detected")
        
        return has_tables
    
    async def process_content(self, mineru_result: MinerUResult, pdf_path: str,
                            temp_dir: str, src_fileid: str, learn_type: int,
                            has_tables: bool) -> ContentProcessingResult:
        """
        [DEPRECATED] Process content with optional multimodal refinement.
        
        This method is deprecated. Use process_page_content() instead for page-by-page processing.
        
        Args:
            mineru_result: Result from MinerU processing
            pdf_path: Path to original PDF
            temp_dir: Temporary directory
            src_fileid: Source file ID
            learn_type: Model type for LLM processing
            has_tables: Whether the content contains tables
            
        Returns:
            ContentProcessingResult with processed content
        """
        try:
            process_type = "with tables" if has_tables else "without tables"
            self.logger.info(f"mineru-content: processing content {process_type}")
            
            # Check if multimodal refinement is enabled
            if not self.config.enable_multimodal_refinement:
                self.logger.info(f"mineru-content: multimodal refinement disabled, returning original content")
                processing_metadata = {
                    'mineru_content_length': len(mineru_result.content),
                    'image_count': len(mineru_result.images),
                    'table_count': len(mineru_result.tables),
                    'multimodal_refinement': False
                }
                
                return ContentProcessingResult(
                    success=True,
                    processed_content=mineru_result.content,
                    has_tables=has_tables,
                    processing_metadata=processing_metadata
                )
            
            # Step 1: Extract plain text from PDF (only if has tables)
            plain_text = ""
            if has_tables:
                plain_text = await self._extract_plain_text(pdf_path, src_fileid)
            
            # Step 2: Extract PDF page images for multimodal processing
            pdf_page_images = await self._extract_pdf_page_images(pdf_path, temp_dir, src_fileid)
            
            # Step 3: Use LLM to refine content with PDF page images
            refined_content = await self._llm_refine_content(
                mineru_result.content, plain_text, pdf_page_images, temp_dir, src_fileid, learn_type, None
            )
            
            processing_metadata = {
                'mineru_content_length': len(mineru_result.content),
                'refined_content_length': len(refined_content),
                'image_count': len(mineru_result.images),
                'table_count': len(mineru_result.tables),
                'pdf_page_images_count': len(pdf_page_images),
                'multimodal_refinement': True
            }
            
            if has_tables:
                processing_metadata['plain_text_length'] = len(plain_text)
            
            self.logger.info(f"mineru-content: content processing completed: {processing_metadata}")
            
            return ContentProcessingResult(
                success=True,
                processed_content=refined_content,
                has_tables=has_tables,
                processing_metadata=processing_metadata
            )
            
        except Exception as e:
            self.logger.error(f"mineru-content: content processing failed: {str(e)}")
            return ContentProcessingResult(
                success=False,
                processed_content=mineru_result.content,  # Fallback to original
                has_tables=has_tables,
                processing_metadata={},
                error=str(e)
            )
    
    async def _extract_plain_text(self, pdf_path: str, _src_fileid: str) -> str:
        """
        Extract plain text from PDF using PyMuPDF.
        """
        try:
            import fitz
            
            text_parts = []
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc):
                    page_text = page.get_text('text')  # Plain text extraction
                    if page_text.strip():
                        text_parts.append(f"=== Page {page_num + 1} ===\n{page_text}")
            
            plain_text = '\n\n'.join(text_parts)
            
            self.logger.info(f"mineru-content:  extracted {len(plain_text)} characters of plain text")
            
            return plain_text
            
        except Exception as e:
            self.logger.error(f"mineru-content:  plain text extraction failed: {str(e)}")
            return ""
    
    async def _extract_pdf_page_images(self, pdf_path: str, temp_dir: str, _src_fileid: str, 
                                     max_pages: int = 10) -> List[str]:
        """
        Extract PDF pages as images for multimodal processing.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for saving images
            _src_fileid: Source file ID
            max_pages: Maximum number of pages to extract (to avoid token limits)
            
        Returns:
            List of paths to page image files
        """
        try:
            import pdf2image
            import os
            
            self.logger.info(f"mineru-content: extracting PDF page images from {pdf_path}")
            
            # Get page count first
            import fitz
            with fitz.open(pdf_path) as doc:
                total_pages = len(doc)
            
            # Determine pages to extract
            pages_to_extract = min(total_pages, max_pages)
            
            # Configure pdf2image options
            options = {
                'pdf_path': pdf_path,
                'dpi': 150,  # Lower DPI for multimodal processing
                'fmt': 'png',
                'output_folder': temp_dir,
                'use_pdftocairo': True,
                'paths_only': True,
                'first_page': 1,
                'last_page': pages_to_extract
            }
            
            # Convert PDF pages to images
            image_paths = pdf2image.convert_from_path(**options)
            
            # Rename images to standard format
            page_images = []
            for idx, img_path in enumerate(image_paths):
                new_name = f"pdf_page_{idx + 1:03d}.png"
                new_path = os.path.join(temp_dir, new_name)
                os.rename(img_path, new_path)
                page_images.append(new_path)
            
            self.logger.info(f"mineru-content: extracted {len(page_images)} page images")
            
            return page_images
            
        except Exception as e:
            self.logger.error(f"mineru-content: PDF page image extraction failed: {str(e)}")
            return []
    

    # def _extract_html_tables(self, content: str) -> List[Tuple[str, int, int]]:
    #     """
    #     Extract HTML tables from content with their positions.
        
    #     Returns:
    #         List of tuples: (table_html, start_pos, end_pos)
    #     """
    #     tables = []
        
    #     # Find all HTML table tags
    #     table_pattern = r'<table[^>]*>.*?</table>'
    #     matches = re.finditer(table_pattern, content, re.DOTALL | re.IGNORECASE)
        
    #     for match in matches:
    #         table_html = match.group(0)
    #         start_pos = match.start()
    #         end_pos = match.end()
    #         tables.append((table_html, start_pos, end_pos))
        
    #     self.logger.info(f"mineru-content: found {len(tables)} HTML tables")
    #     return tables
    
    def _find_related_pdf_content(self, plain_text: str, table_html: str, context_size: int = 500) -> str:
        """
        Find related content in PDF text based on table content.
        
        Args:
            plain_text: Full PDF plain text
            table_html: HTML table to find context for
            context_size: Number of characters before/after to include
            
        Returns:
            Related PDF text chunk
        """
        try:
            # Extract text from HTML table
            soup = BeautifulSoup(table_html, 'html.parser')
            table_text = soup.get_text(separator=' ', strip=True)
            
            # Extract key words from table (first few non-numeric words)
            # 根据标点符号分割文本
            # 修复正则表达式中的字符范围语法错误
            words = re.split(r'[,.!:?;*\-，。！？；、/()（）\s]+', table_text)
            key_words = []
            for word in words:
                # Skip pure numbers and short words
                if len(word) > 3 and word not in key_words:
                    key_words.append(word)
            
            if not key_words:
                self.logger.warning("mineru-content: no key words found in table")
                return ""
            
            # Search for key words in PDF text
            best_match_pos = -1
            best_match_score = 0
            
            # Use sliding window to find best match
            window_size = len(table_text) * 3  # Look for similar sized content
            for i in range(0, len(plain_text) - window_size, 100):  # Step by 100 chars
                window_text = plain_text[i:i + window_size]
                
                # Count matching key words
                match_score = sum(1 for word in key_words if word.lower() in window_text.lower())
                
                if match_score > best_match_score:
                    best_match_score = match_score
                    best_match_pos = i
            
            if best_match_pos >= 0 and best_match_score >= len(key_words) * 0.3:
                # Extract context around the match
                start = max(0, best_match_pos - context_size)
                end = min(len(plain_text), best_match_pos + window_size + context_size)
                
                context = plain_text[start:end]
                self.logger.info(f"mineru-content: found related PDF content with score {best_match_score}/{len(key_words)}")
                return context
            else:
                self.logger.warning(f"mineru-content: no good match found (best score: {best_match_score}/{len(key_words)})")
                return ""
                
        except Exception as e:
            self.logger.error(f"mineru-content: error finding related PDF content: {str(e)}")
            return ""
    
    async def _llm_refine_content(self, content: str, plain_text: str, pdf_page_images: List[str], 
                                  temp_dir: str, src_fileid: str, learn_type: int, language_code: Optional[str] = None) -> str:
        """
        Use LLM to refine content by:
        1. Removing HTML tags from content
        2. Combining content + plain_text + PDF page images
        3. Using AI model to generate markdown output
        4. Storing table existence in metadata
        
        Args:
            content: MinerU extracted content with HTML
            plain_text: Plain text extracted from PDF
            pdf_page_images: List of PDF page image paths (full page screenshots)
            temp_dir: Temporary directory
            src_fileid: Source file ID
            learn_type: Model type for LLM
        """
        import base64
        try:
            # Remove HTML tags from content
            soup = BeautifulSoup(content, 'html.parser')
            content_text = soup.get_text(separator='\n', strip=True)
            
            # Detect if original content had tables (for cache metadata only)
            has_tables_in_html = bool(soup.find_all('table'))
            
            # Use provided language code or detect from content
            if not language_code:
                combined_text = content_text + "\n" + plain_text
                if combined_text.strip():
                    detected_code, confidence = LanguageDetector.detect_language(combined_text)
                    if confidence > 0.7:
                        language_code = detected_code
                        self.logger.info(f"mineru-refine-content: detected language: {language_code} (confidence: {confidence:.2f})")
                    else:
                        self.logger.info(f"mineru-refine-content: language detection confidence too low ({confidence:.2f})")
            
            if language_code:
                self.logger.info(f"mineru-refine-content: will generate content in {LanguageDetector.get_language_name(language_code)}")
            else:
                self.logger.info(f"mineru-refine-content: no language specified, will use default")
            
            # Check for cache
            cache_filepath = os.path.join(temp_dir, f"content_refinement_markdown_v1_{src_fileid}.json")
            
            # Use imported prompt for markdown generation with language
            markdown_generation_prompt = format_markdown_generation_prompt(language_code)

            # Prepare messages with multimodal content
            messages = [
                {"role": "system", "content": markdown_generation_prompt}
            ]
            
            # Create user message with text and images
            user_content = []
            
            # Add text content
            combined_input = f"""## OCR提取的文本：
{content_text}

## PDF原始文本：
{plain_text}

请基于提供的PDF页面图片和以上文本源，生成准确、完整的Markdown格式文档。特别注意识别和重建表格内容。"""
            
            user_content.append({
                "type": "text",
                "text": combined_input
            })
            
            # Add PDF page images if available
            if pdf_page_images:
                self.logger.info(f"mineru-content: including {len(pdf_page_images)} PDF page images in multimodal request")
                # Limit pages to avoid token limits and model constraints
                # Most models have a limit of 4 images per request
                max_pages = min(len(pdf_page_images), 4)
                for idx, page_img_path in enumerate(pdf_page_images[:max_pages]):
                    if os.path.exists(page_img_path):
                        try:
                            with open(page_img_path, 'rb') as img_file:
                                # Use BytesIO to avoid blocking the event loop
                                img_data = img_file.read()
                                img_buffer = io.BytesIO(img_data)
                                img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                                user_content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_base64}"
                                    }
                                })
                                self.logger.info(f"mineru-refine-content: added PDF page {idx + 1} image")
                        except Exception as e:
                            self.logger.warning(f"mineru-refine-content: failed to read PDF page image {page_img_path}: {str(e)}")
                    else:
                        self.logger.warning(f"mineru-refine-content: PDF page image not found: {page_img_path}")
            else:
                self.logger.warning("mineru-refine-content: no PDF page images provided for multimodal processing")
            
            messages.append({
                "role": "user",
                "content": user_content
            })
            
            self.logger.info(f"mineru-refine-content: processing content with LLM for markdown generation")
            
            # Use the unified litellm helper for multimodal request
            response = await self.config.call_litellm(
                model_type=learn_type,
                messages=messages,
                temperature=0.1
            )
            
            # Process response
            refined_content = content
            total_prompt_tokens = 0
            total_completion_tokens = 0
            
            try:
                if (response.choices and 
                    len(response.choices) > 0 and
                    response.choices[0].message and
                    response.choices[0].message.content):
                    refined_content = response.choices[0].message.content.strip()
                    # 从响应中提取markdown内容
                    markdown_start = refined_content.find("```markdown")
                    markdown_end = refined_content.rfind("```")
                    
                    if markdown_start >= 0 and markdown_end > markdown_start:
                        # 提取markdown内容并去除首尾的```标记
                        refined_content = refined_content[markdown_start + 11:markdown_end].strip()
                    else:
                        # 如果没找到markdown标记，使用原始内容
                        self.logger.warning("mineru-refine-content: no markdown block found in response")
                    
                    # Clean hallucination patterns first
                    refined_content = self._clean_hallucination_patterns(refined_content)
                    
                    # Limit content length to prevent OpenSearch indexing errors
                    # OpenSearch has a max field length of 32766 bytes
                    # We use 30000 characters as a safe limit (considering UTF-8 encoding)
                    MAX_CONTENT_LENGTH = 30000
                    if len(refined_content) > MAX_CONTENT_LENGTH:
                        self.logger.warning(f"mineru-refine-content: content too long ({len(refined_content)} chars), truncating to {MAX_CONTENT_LENGTH}")
                        # Try to truncate at a sentence boundary
                        truncated = refined_content[:MAX_CONTENT_LENGTH]
                        # Find last complete sentence
                        for sep in ['. ', '。', '! ', '? ', '\n\n', '\n']:
                            last_sep = truncated.rfind(sep)
                            if last_sep > MAX_CONTENT_LENGTH * 0.9:  # Within last 10%
                                refined_content = truncated[:last_sep + len(sep)]
                                break
                        else:
                            # If no good sentence boundary, just truncate
                            refined_content = truncated + "..."
                    
                    # Track token usage
                    if hasattr(response, 'usage') and response.usage:
                        total_prompt_tokens = response.usage.prompt_tokens
                        total_completion_tokens = response.usage.completion_tokens
                    
                    self.logger.info(
                        f"mineru-refine-content: markdown generation completed - "
                        f"tokens: {total_prompt_tokens}/{total_completion_tokens}"
                    )
                else:
                    self.logger.warning("mineru-refine-content: empty response from LLM, using original content")
                    refined_content = content_text
                    # Also clean fallback content
                    refined_content = self._clean_hallucination_patterns(refined_content)
                    
            except (AttributeError, IndexError, ValueError) as e:
                self.logger.error(f"mineru-refine-content: LLM response parsing failed: {str(e)}")
                refined_content = content_text
                # Clean and apply length limit to fallback content
                refined_content = self._clean_hallucination_patterns(refined_content)
                MAX_CONTENT_LENGTH = 30000
                if len(refined_content) > MAX_CONTENT_LENGTH:
                    self.logger.warning(f"mineru-refine-content: fallback content too long ({len(refined_content)} chars), truncating")
                    refined_content = refined_content[:MAX_CONTENT_LENGTH] + "..."
            
            # Save to cache
            try:
                cache_data = {
                    "refined_content": refined_content,
                    "model": "llm",  # Generic model name since we don't have model_config anymore
                    "input_length": len(content_text) + len(plain_text),
                    "output_length": len(refined_content),
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "has_tables": has_tables_in_html,
                    "used_pdf_page_images": len(pdf_page_images) if pdf_page_images else 0
                }
                with open(cache_filepath, 'w', encoding='utf-8') as file:
                    json.dump(cache_data, file, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.warning(f"mineru-refine-content:  cache write failed: {str(e)}")
            
            return refined_content
            
        except Exception as e:
            self.logger.error(f"mineru-refine-content:  LLM refinement failed: {str(e)}")
            # Fallback: return text without HTML tags
            try:
                soup = BeautifulSoup(content, 'html.parser')
                return soup.get_text(separator='\n', strip=True)
            except:
                return content
    
    def split_content_by_pages(self, mineru_result: MinerUResult) -> Dict[int, Dict]:
        """
        Split MinerU results by page index.
        
        Args:
            mineru_result: MinerU processing result with content_list
            
        Returns:
            Dictionary mapping page_idx to page data
        """
        page_data = {}
        content_list = mineru_result.metadata.get('content_list', [])
        
        # Group content by page
        for item in content_list:
            page_idx = item.get('page_idx', 0)
            if page_idx not in page_data:
                page_data[page_idx] = {
                    'content_items': [],
                    'images': [],
                    'tables': [],
                    'page_idx': page_idx
                }
            
            # Add item to appropriate list
            if item['type'] == 'image':
                page_data[page_idx]['images'].append(item.get('img_path', ''))
            elif item['type'] == 'table':
                page_data[page_idx]['tables'].append(item.get('metadata', {}))
            
            page_data[page_idx]['content_items'].append(item)
        
        # Extract page content from the merged content
        # Try to split by different page markers
        content = mineru_result.content
        
        # Method 1: Split by "## Page X" markers
        if '\n\n## Page ' in content:
            content_parts = content.split('\n\n## Page ')
            for i, part in enumerate(content_parts):
                if i == 0 and not part.startswith('## Page'):
                    # Handle content before first page marker
                    if part.strip() and 0 in page_data:
                        page_data[0]['content'] = part.strip()
                    continue
                
                # Extract page number
                page_match = re.match(r'^(\d+)', part)
                if page_match:
                    page_num = int(page_match.group(1)) - 1  # Convert to 0-based index
                    if page_num in page_data:
                        # Remove page number line and get content
                        lines = part.split('\n', 1)
                        if len(lines) > 1:
                            page_data[page_num]['content'] = lines[1].strip()
        else:
            # Method 2: If no clear page markers, try to reconstruct from content_list
            current_content = []
            current_page = -1
            
            for item in content_list:
                item_page = item.get('page_idx', 0)
                
                # If we moved to a new page, save previous content
                if item_page != current_page and current_page >= 0:
                    if current_page in page_data:
                        page_data[current_page]['content'] = '\n\n'.join(current_content)
                    current_content = []
                
                current_page = item_page
                
                # Add text content
                if item['type'] in ['text', 'title']:
                    text = item.get('text', '') or item.get('content', '')
                    if text.strip():
                        if item['type'] == 'title':
                            current_content.append(f"## {text.strip()}")
                        else:
                            current_content.append(text.strip())
                elif item['type'] == 'table':
                    current_content.append("[Table content]")  # Placeholder for table
            
            # Save last page content
            if current_page >= 0 and current_page in page_data:
                page_data[current_page]['content'] = '\n\n'.join(current_content)
        
        return page_data
    
    async def process_page_content(self, page_content: str, page_images: List[str], 
                                 pdf_path: str, page_idx: int, temp_dir: str, 
                                 src_fileid: str, learn_type: int, language_code: Optional[str] = None) -> Dict:
        """
        Process content for a single page.
        
        Args:
            page_content: Content text for the page
            page_images: Images found on the page
            pdf_path: Path to PDF file
            page_idx: Page index (0-based)
            temp_dir: Temporary directory
            src_fileid: Source file ID
            learn_type: Model type for LLM
            
        Returns:
            Dictionary with processed page data
        """
        try:
            # Handle empty content gracefully
            if not page_content or not page_content.strip():
                self.logger.info(f"mineru-content: page {page_idx} has no text content")
                return {
                    'page_idx': page_idx,
                    'content': '',
                    'images': page_images,
                    'has_tables': False,
                    'processing_metadata': {
                        'original_length': 0,
                        'refined_length': 0,
                        'multimodal_used': False,
                        'empty_page': True
                    }
                }
            
            # Detect tables in this page's content
            has_tables = self.detect_tables(page_content, f"{src_fileid}_page_{page_idx}")
            
            # Extract single page image if multimodal is enabled
            pdf_page_images = []
            if self.config.enable_multimodal_refinement:
                # Extract just this page as image
                pdf_page_images = await self._extract_single_pdf_page_image(
                    pdf_path, page_idx, temp_dir, src_fileid
                )
            plain_text = ""
            if self.config.enable_multimodal_refinement and has_tables:
                plain_text = await self._extract_page_plain_text(pdf_path, page_idx, src_fileid)

            # Process content with multimodal refinement if enabled, has image 、has table、no text
            if self.config.enable_multimodal_refinement and \
                (plain_text == "" or has_tables or len(page_images) > 0): 
                # Refine content for this page
                refined_content = await self._llm_refine_content(
                    page_content, plain_text, pdf_page_images, temp_dir, 
                    f"{src_fileid}_page_{page_idx}", learn_type, language_code
                )
            else:
                refined_content = page_content
            
            # Clean hallucination patterns and apply length limit to all content
            refined_content = self._clean_hallucination_patterns(refined_content)
            MAX_CONTENT_LENGTH = 30000
            if len(refined_content) > MAX_CONTENT_LENGTH:
                self.logger.warning(f"mineru-content: page {page_idx} content too long ({len(refined_content)} chars), truncating")
                refined_content = refined_content[:MAX_CONTENT_LENGTH] + "..."
            
            return {
                'page_idx': page_idx,
                'content': refined_content,
                'images': page_images,
                'has_tables': has_tables,
                'processing_metadata': {
                    'original_length': len(page_content),
                    'refined_length': len(refined_content),
                    'multimodal_used': self.config.enable_multimodal_refinement and (has_tables or len(page_images) > 0)
                }
            }
            
        except Exception as e:
            self.logger.error(f"mineru-content: page {page_idx} processing failed: {str(e)}")
            return {
                'page_idx': page_idx,
                'content': page_content,  # Fallback to original
                'images': page_images,
                'has_tables': False,
                'processing_metadata': {'error': str(e)}
            }
    
    async def _extract_single_pdf_page_image(self, pdf_path: str, page_idx: int, 
                                           temp_dir: str, _src_fileid: str) -> List[str]:
        """Extract a single PDF page as image."""
        try:
            import pdf2image
            
            options = {
                'pdf_path': pdf_path,
                'dpi': 150,
                'fmt': 'png',
                'output_folder': temp_dir,
                'use_pdftocairo': True,
                'paths_only': True,
                'first_page': page_idx + 1,  # pdf2image uses 1-based indexing
                'last_page': page_idx + 1
            }
            
            image_paths = pdf2image.convert_from_path(**options)
            
            if image_paths:
                new_name = f"pdf_page_{page_idx + 1:03d}.png"
                new_path = os.path.join(temp_dir, new_name)
                os.rename(image_paths[0], new_path)
                return [new_path]
            
            return []
            
        except Exception as e:
            self.logger.error(f"mineru-content: failed to extract page {page_idx} image: {str(e)}")
            return []
    
    async def _extract_page_plain_text(self, pdf_path: str, page_idx: int, _src_fileid: str) -> str:
        """Extract plain text from a specific PDF page."""
        try:
            import fitz
            
            with fitz.open(pdf_path) as doc:
                if page_idx < len(doc):
                    page = doc[page_idx]
                    return page.get_text('text')
            
            return ""
            
        except Exception as e:
            self.logger.error(f"mineru-content: failed to extract page {page_idx} text: {str(e)}")
            return ""
    
    def create_page_chunks(self, content: str, _src_fileid: str) -> List[Dict]:
        """
        Split content into page-based chunks for compatibility with gzero.py format.
        
        Args:
            content: Processed content
            src_fileid: Source file ID
            
        Returns:
            List of page dictionaries
        """
        try:
            # Split content by page markers
            page_separators = ['=== Page ', '__PAGE_OF_PORTION_']
            
            pages = []
            current_content = content
            
            # Try to split by existing page markers
            page_parts = []
            for separator in page_separators:
                if separator in current_content:
                    page_parts = current_content.split(separator)
                    break
            
            if len(page_parts) > 1:
                # Content already has page separators
                for i, part in enumerate(page_parts):
                    if i == 0 and not part.strip():
                        continue  # Skip empty first part
                    
                    pages.append({
                        'index': len(pages),
                        'content': part.strip(),
                        'image_map': {},
                        'summary': '',
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'dura': 0.0
                    })
            else:
                # Single page content
                pages.append({
                    'index': 0,
                    'content': content,
                    'image_map': {},
                    'summary': '',
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'dura': 0.0
                })
            
            self.logger.info(f"mineru-content:  created {len(pages)} page chunks")
            
            return pages
            
        except Exception as e:
            self.logger.error(f"mineru-content:  page chunking failed: {str(e)}")
            # Fallback to single page
            return [{
                'index': 0,
                'content': content,
                'image_map': {},
                'summary': '',
                'input_tokens': 0,
                'output_tokens': 0,
                'dura': 0.0
            }]
    
    def extract_page_contexts(self, content_list: List[Dict], _src_fileid: str) -> List[PageContext]:
        """
        Extract page context information from MinerU content list.
        
        Args:
            content_list: List of content items from MinerU with page_idx and type
            src_fileid: Source file ID
            
        Returns:
            List of PageContext objects
        """
        try:
            self.logger.info(f"mineru-content: extracting page contexts from {len(content_list)} items")
            
            # Group content by page
            page_groups = {}
            for idx, item in enumerate(content_list):
                page_idx = item.get('page_idx', 0)
                if page_idx not in page_groups:
                    page_groups[page_idx] = []
                page_groups[page_idx].append((idx, item))
            
            # Create PageContext for each page
            page_contexts = []
            for page_idx in sorted(page_groups.keys()):
                page_items = page_groups[page_idx]
                
                # Determine page type
                has_title = any(item[1].get('type') == 'title' for item in page_items)
                text_count = sum(1 for item in page_items if item[1].get('type') == 'text')
                
                if has_title and text_count > 0:
                    page_type = 'mixed'
                elif has_title:
                    page_type = 'title'
                else:
                    page_type = 'content'
                
                # Extract title if available
                page_title = None
                for _, item in page_items:
                    if item.get('type') == 'title':
                        page_title = item.get('text', '').strip()
                        break
                
                # Create content elements
                content_elements = []
                text_parts = []
                
                for position, item in page_items:
                    element_type = item.get('type', 'unknown')
                    content = item.get('text', '') or item.get('content', '')
                    
                    if element_type == 'text' and content:
                        text_parts.append(content)
                    
                    content_elements.append(ContentElement(
                        type=element_type,
                        content=content,
                        page_idx=page_idx,
                        position=position,
                        bbox=item.get('bbox'),
                        metadata=item.get('metadata', {})
                    ))
                
                # Join text content
                text_content = '\n'.join(text_parts)
                
                # Count tokens
                token_count = self._count_tokens(text_content)
                
                page_context = PageContext(
                    page_idx=page_idx,
                    page_type=page_type,
                    title=page_title,
                    content_elements=content_elements,
                    text_content=text_content,
                    token_count=token_count
                )
                
                page_contexts.append(page_context)
            
            self.logger.info(f"mineru-content: extracted {len(page_contexts)} page contexts")
            return page_contexts
            
        except Exception as e:
            self.logger.error(f"mineru-content: page context extraction failed: {str(e)}")
            return []
    
    def extract_context_for_position(self, content_list: List[Dict], position: int,
                                   mode: ContextMode = ContextMode.PAGE,
                                   window_size: int = 2,
                                   max_tokens: int = 1000) -> str:
        """
        Extract context around a specific position in the content list.
        
        Args:
            content_list: MinerU content list
            position: Position in the content list
            mode: Context extraction mode (PAGE or CHUNK)
            window_size: Number of pages/chunks to include
            max_tokens: Maximum tokens to include
            
        Returns:
            Extracted context string
        """
        try:
            if position >= len(content_list):
                return ""
            
            target_item = content_list[position]
            
            if mode == ContextMode.PAGE:
                # Extract based on page boundaries
                target_page_idx = target_item.get('page_idx', 0)
                min_page = max(0, target_page_idx - window_size)
                max_page = target_page_idx + window_size
                
                context_items = []
                for idx, item in enumerate(content_list):
                    item_page = item.get('page_idx', 0)
                    if min_page <= item_page <= max_page and item.get('type') in ['text', 'title']:
                        # Add page marker
                        if item_page != target_page_idx:
                            page_marker = f"[Page {item_page + 1}]"
                            if not context_items or context_items[-1] != page_marker:
                                context_items.append(page_marker)
                        
                        text = item.get('text', '').strip()
                        if text:
                            context_items.append(text)
                
            else:  # ContextMode.CHUNK
                # Extract based on chunk position
                min_pos = max(0, position - window_size)
                max_pos = min(len(content_list) - 1, position + window_size)
                
                context_items = []
                for idx in range(min_pos, max_pos + 1):
                    if idx == position:
                        continue  # Skip the target item itself
                    
                    item = content_list[idx]
                    if item.get('type') in ['text', 'title', 'table']:
                        text = item.get('text', '').strip()
                        if text:
                            if idx < position:
                                context_items.append(f"[Before] {text}")
                            else:
                                context_items.append(f"[After] {text}")
            
            # Join and truncate by tokens
            context_text = '\n'.join(context_items)
            return self._truncate_by_tokens(context_text, max_tokens)
            
        except Exception as e:
            self.logger.error(f"mineru-content: context extraction failed: {str(e)}")
            return ""
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # Fallback to character-based estimation
            return len(text) // 4
    
    def _truncate_by_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit while preserving sentence boundaries."""
        if not text:
            return ""
        
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            tokens = encoding.encode(text)
            
            if len(tokens) <= max_tokens:
                return text
            
            # Truncate to max tokens
            truncated_tokens = tokens[:max_tokens]
            truncated_text = encoding.decode(truncated_tokens)
            
            # Try to find a sentence boundary
            for sep in ['. ', '。', '! ', '? ', '\n']:
                last_sep = truncated_text.rfind(sep)
                if last_sep > len(truncated_text) * 0.8:  # Within last 20%
                    return truncated_text[:last_sep + len(sep)]
            
            return truncated_text + "..."
            
        except:
            # Fallback to character-based truncation
            char_limit = max_tokens * 4
            if len(text) > char_limit:
                return text[:char_limit] + "..."
            return text
    
    def _clean_hallucination_patterns(self, content: str) -> str:
        """
        Clean common AI hallucination patterns from content.
        
        Args:
            content: The content to clean
            
        Returns:
            Cleaned content
        """
        if not content:
            return content
        
        original_length = len(content)
        
        # Pattern 1: Remove excessive dots (more than 10 consecutive dots)
        content = re.sub(r'\.{10,}', '...', content)
        
        # Pattern 2: Remove other excessive repeated characters (more than 10)
        # This handles patterns like "--------" or "========="
        content = re.sub(r'(.)\1{9,}', r'\1\1\1', content)
        
        # Pattern 3: Remove excessive repeated words or patterns
        # For example: "................................................................"
        # repeated many times
        content = re.sub(r'(\.{3,}[\s\n]*){5,}', '...\n', content)
        
        # Pattern 4: Remove number sequences that appear to be counting
        # Like ", 68\n, 72\n, 73\n, 73\n, 73\n" repeated many times
        content = re.sub(r'(,\s*\d+\s*\n?\s*){20,}', '', content)
        
        # Pattern 5: Remove table of contents with excessive dots
        # Like "8.2 macOS 系统安装无线驱动程序................................................"
        content = re.sub(r'([^\n]+)(\.{20,})', r'\1', content)
        
        # Pattern 6: Clean up multiple consecutive empty lines
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        
        # Pattern 7: Remove excessive dots or comma-separated numbers at the end
        # But preserve normal punctuation
        content = re.sub(r'[\s\n]*[,\d\s]{10,}$', '', content)
        content = re.sub(r'\.{4,}$', '...', content)
        
        cleaned_length = len(content)
        if cleaned_length < original_length:
            reduction = original_length - cleaned_length
            self.logger.info(f"mineru-content: cleaned {reduction} characters of hallucination patterns "
                           f"(from {original_length} to {cleaned_length})")
        
        return content.strip()