"""
Utility functions for MinerU-based parsing.

This module provides helper functions for file detection, conversion,
and common operations used throughout the parsing system.
"""

import os
import subprocess
import tempfile
import fitz
import hashlib
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from .logger import get_module_logger
logger = get_module_logger('utils')

# Platform-specific utils import (if available)
try:
    from loader.train import utils as train_utils
except ImportError:
    train_utils = None


class PDFDetector:
    """PDF format detection utilities"""
    
    @staticmethod
    def is_pdf_from_ppt(pdf_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Detect if PDF was converted from PowerPoint presentation.
        
        Based on gzero.py's is_pdf_from_ppt detection logic.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (is_from_ppt, metadata_dict)
        """
        try:
            with fitz.open(pdf_path) as doc:
                metadata = doc.metadata
                
                # Check Creator/Producer fields for PPT indicators
                creator = metadata.get('creator', '').lower()
                producer = metadata.get('producer', '').lower()
                
                ppt_indicators = [
                    'powerpoint', 'microsoft office', 'presentation',
                    'impress', 'libreoffice', 'openoffice'
                ]
                
                is_from_ppt = any(indicator in creator or indicator in producer 
                                 for indicator in ppt_indicators)
                
                # Check page aspect ratios (PPT typically uses 16:9 or 4:3)
                if not is_from_ppt and len(doc) > 0:
                    page = doc[0]
                    aspect_ratio = page.rect.width / page.rect.height if page.rect.height > 0 else 0
                    
                    # Common PPT aspect ratios: 16:9 ≈ 1.78, 4:3 ≈ 1.33
                    ppt_ratios = [16/9, 4/3]  # Include portrait orientations
                    tolerance = 0.1
                    
                    is_from_ppt = any(abs(aspect_ratio - ratio) < tolerance 
                                     for ratio in ppt_ratios)
                
                return is_from_ppt, {
                    'creator': metadata.get('creator', ''),
                    'producer': metadata.get('producer', ''),
                    'page_count': len(doc),
                    'aspect_ratio': page.rect.width / page.rect.height if len(doc) > 0 and page.rect.height > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"Error detecting PPT format from PDF {pdf_path}: {str(e)}")
            return False, {}
    
    @staticmethod
    def extract_pdf_pages(pdf_path: str) -> list:
        """
        Extract page information from PDF file.
        
        Based on gzero.py's page extraction logic.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of page information dictionaries
        """
        pages = []
        try:
            with fitz.open(pdf_path) as doc:
                for page_index, page in enumerate(doc):
                    page_info = {
                        'index': page_index,
                        'rotation': page.rotation,
                        'text': page.get_text('text'),
                        'width': page.rect.width,
                        'height': page.rect.height,
                        'images': []
                    }
                    
                    # Extract image information
                    for img in page.get_images(full=True):
                        bbox = page.get_image_bbox(img)
                        if bbox.width > 0 and bbox.height > 0:
                            img_info = {
                                'xref': img[0],
                                'smask': img[1],
                                'width': img[2],
                                'height': img[3],
                                'bbox_x': bbox.x0,
                                'bbox_y': bbox.y0,
                                'bbox_w': bbox.width,
                                'bbox_h': bbox.height,
                                'bbox_r': (bbox.width * bbox.height) / (page_info['width'] * page_info['height'])
                            }
                            page_info['images'].append(img_info)
                    
                    pages.append(page_info)
                    
        except Exception as e:
            logger.error(f"Error extracting pages from PDF {pdf_path}: {str(e)}")
            
        return pages


class FileConverter:
    """File conversion utilities"""
    
    @staticmethod
    async def convert_ppt_to_pdf(ppt_path: str, output_dir: Optional[str] = None) -> str:
        """
        Convert PPT/PPTX file to PDF format.
        
        Based on gzero.py's conversion logic with LibreOffice.
        
        Args:
            ppt_path: Path to PPT/PPTX file
            output_dir: Output directory (defaults to temp directory)
            
        Returns:
            Path to converted PDF file
        """
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        
        pdf_filename = Path(ppt_path).stem + "_converted.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        try:
            # Use LibreOffice for conversion (primary method)
            cmd = [
                'libreoffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', output_dir,
                ppt_path
            ]
            
            logger.info(f"mineru-converter: converting PPT to PDF: {ppt_path} -> {pdf_path}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"LibreOffice conversion failed: {result.stderr}")
            
            # LibreOffice generates file with original name
            generated_pdf = os.path.join(output_dir, Path(ppt_path).stem + ".pdf")
            if os.path.exists(generated_pdf) and generated_pdf != pdf_path:
                os.rename(generated_pdf, pdf_path)
            
            if not os.path.exists(pdf_path):
                raise Exception("PDF file was not generated")
                
            logger.info(f"mineru-converter: PPT conversion successful: {pdf_path}")
            return pdf_path
            
        except subprocess.TimeoutExpired:
            raise Exception("PPT conversion timeout")
        except FileNotFoundError:
            # LibreOffice not available, try alternative method
            logger.warning("LibreOffice not found, trying alternative conversion method")
            return await FileConverter._convert_ppt_alternative(ppt_path, output_dir)
        except Exception as e:
            logger.error(f"mineru-converter: PPT conversion failed: {str(e)}")
            raise
    
    @staticmethod
    async def _convert_ppt_alternative(ppt_path: str, output_dir: str) -> str:
        """
        Alternative PPT to PDF conversion method using python-pptx + reportlab.
        
        Args:
            ppt_path: Path to PPT file
            output_dir: Output directory
            
        Returns:
            Path to converted PDF file
        """
        try:
            from pptx import Presentation
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            
            pdf_filename = Path(ppt_path).stem + "_converted.pdf"
            pdf_path = os.path.join(output_dir, pdf_filename)
            
            # Read PPT file
            prs = Presentation(ppt_path)
            
            # Create PDF
            c = canvas.Canvas(pdf_path, pagesize=A4)
            
            for slide_idx, slide in enumerate(prs.slides):
                if slide_idx > 0:
                    c.showPage()
                
                # Extract slide content (simplified version)
                y_position = 750
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        # Truncate long text to fit on page
                        text = shape.text[:100]
                        c.drawString(50, y_position, text)
                        y_position -= 30
                        if y_position < 50:
                            break
            
            c.save()
            logger.info(f"mineru-converter: alternative PPT conversion successful: {pdf_path}")
            return pdf_path
            
        except ImportError:
            raise Exception("Alternative PPT conversion requires python-pptx and reportlab libraries")
        except Exception as e:
            raise Exception(f"Alternative PPT conversion failed: {str(e)}")
    
    @staticmethod
    async def convert_doc_to_pdf(doc_path: str, output_dir: Optional[str] = None) -> str:
        """
        Convert DOC/DOCX file to PDF format.
        
        Args:
            doc_path: Path to DOC/DOCX file
            output_dir: Output directory (defaults to temp directory)
            
        Returns:
            Path to converted PDF file
        """
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        
        pdf_filename = Path(doc_path).stem + "_converted.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        try:
            # Use LibreOffice for conversion (same as PPT)
            cmd = [
                'libreoffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', output_dir,
                doc_path
            ]
            
            logger.info(f"mineru-converter: converting DOC to PDF: {doc_path} -> {pdf_path}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"LibreOffice conversion failed: {result.stderr}")
            
            # LibreOffice generates file with original name
            generated_pdf = os.path.join(output_dir, Path(doc_path).stem + ".pdf")
            if os.path.exists(generated_pdf) and generated_pdf != pdf_path:
                os.rename(generated_pdf, pdf_path)
            
            if not os.path.exists(pdf_path):
                raise Exception("PDF file was not generated")
                
            logger.info(f"mineru-converter: DOC conversion successful: {pdf_path}")
            return pdf_path
            
        except subprocess.TimeoutExpired:
            raise Exception("DOC conversion timeout")
        except FileNotFoundError:
            # LibreOffice not available, try alternative method
            logger.warning("LibreOffice not found, trying alternative conversion method")
            return await FileConverter._convert_doc_alternative(doc_path, output_dir)
        except Exception as e:
            logger.error(f"mineru-converter: DOC conversion failed: {str(e)}")
            raise
    
    @staticmethod
    async def _convert_doc_alternative(doc_path: str, output_dir: str) -> str:
        """
        Alternative DOC to PDF conversion method using python-docx.
        
        Args:
            doc_path: Path to DOC file
            output_dir: Output directory
            
        Returns:
            Path to converted PDF file
        """
        try:
            from docx import Document
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import inch
            
            pdf_filename = Path(doc_path).stem + "_converted.pdf"
            pdf_path = os.path.join(output_dir, pdf_filename)
            
            # Read DOC file
            doc = Document(doc_path)
            
            # Create PDF
            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            
            y_position = height - inch
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    # Handle text wrapping
                    text = paragraph.text
                    if len(text) > 80:  # Approximate line length
                        lines = [text[i:i+80] for i in range(0, len(text), 80)]
                        for line in lines:
                            if y_position < inch:
                                c.showPage()
                                y_position = height - inch
                            c.drawString(inch, y_position, line)
                            y_position -= 20
                    else:
                        if y_position < inch:
                            c.showPage()
                            y_position = height - inch
                        c.drawString(inch, y_position, text)
                        y_position -= 20
            
            c.save()
            logger.info(f"mineru-converter: alternative DOC conversion successful: {pdf_path}")
            return pdf_path
            
        except ImportError:
            raise Exception("Alternative DOC conversion requires python-docx and reportlab libraries")
        except Exception as e:
            raise Exception(f"Alternative DOC conversion failed: {str(e)}")
    
    @staticmethod
    async def convert_image_to_pdf(image_path: str, output_dir: Optional[str] = None) -> str:
        """
        Convert image file to PDF format.
        
        Args:
            image_path: Path to image file
            output_dir: Output directory (defaults to temp directory)
            
        Returns:
            Path to converted PDF file
        """
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        
        pdf_filename = Path(image_path).stem + "_converted.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        try:
            from PIL import Image
            
            logger.info(f"mineru-converter: converting image to PDF: {image_path} -> {pdf_path}")
            
            # Open image
            img = Image.open(image_path)
            
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if img.mode in ('RGBA', 'LA'):
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                else:
                    background.paste(img, mask=img.split()[1])  # LA mode
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Save as PDF
            img.save(pdf_path, 'PDF', resolution=100.0)
            
            logger.info(f"mineru-converter: image conversion successful: {pdf_path}")
            return pdf_path
            
        except ImportError:
            raise Exception("Image conversion requires Pillow library")
        except Exception as e:
            logger.error(f"mineru-converter: image conversion failed: {str(e)}")
            raise
    
    @staticmethod
    def detect_file_type(file_path: str) -> str:
        """
        Detect file type from file extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            File type string ('pdf', 'ppt', 'pptx', 'doc', 'docx', 'image', etc.)
        """
        extension = Path(file_path).suffix.lower()
        type_map = {
            '.pdf': 'pdf',
            '.ppt': 'ppt', 
            '.pptx': 'pptx',
            '.doc': 'doc',
            '.docx': 'docx',
            '.png': 'image',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.gif': 'image',
            '.bmp': 'image',
            '.tiff': 'image',
            '.tif': 'image',
            '.webp': 'image',
            '.svg': 'image'
        }
        return type_map.get(extension, 'unknown')
    
    @staticmethod
    def validate_file_size(file_path: str, max_size_mb: float) -> bool:
        """
        Validate file size against maximum allowed size.
        
        Args:
            file_path: Path to file
            max_size_mb: Maximum size in MB
            
        Returns:
            True if file size is acceptable
        """
        try:
            file_size = os.path.getsize(file_path)
            max_size_bytes = max_size_mb * 1024 * 1024
            return file_size <= max_size_bytes
        except Exception as e:
            logger.error(f"Error checking file size for {file_path}: {str(e)}")
            return False
        

def clean_filename(filename: str) -> str:
    """
    Clean filename for safe file system operations.
    
    Args:
        filename: Original filename
        
    Returns:
        Cleaned filename
    """
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    cleaned = filename
    for char in invalid_chars:
        cleaned = cleaned.replace(char, '_')
    
    # Limit length
    if len(cleaned) > 200:
        name, ext = os.path.splitext(cleaned)
        cleaned = name[:200-len(ext)] + ext
    
    return cleaned


def create_temp_directory(base_dir: str, prefix: str = "mineru_") -> str:
    """
    Create temporary directory for processing.
    
    Args:
        base_dir: Base directory path
        prefix: Prefix for temp directory name
        
    Returns:
        Path to created temporary directory
    """
    temp_dir = tempfile.mkdtemp(prefix=prefix, dir=base_dir)
    logger.debug(f"mineru-utils: created temporary directory: {temp_dir}")
    return temp_dir


def get_file_hash(filepath: str) -> str:
    """
    Generate MD5 hash of a file for tracing and identification.
    
    Args:
        filepath: Path to the file
        
    Returns:
        MD5 hash string of the file
    """
    hash_obj = hashlib.md5()
    with open(filepath, 'rb') as file:
        while chunk := file.read(8192):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def get_temp_dir(src_fileid: str, learn_type: int, cache_version: str = 'v1') -> str:
    """
    Setup processing environment with standardized directory structure.
    
    Args:
        src_fileid: Source file ID (typically file hash)
        learn_type: Model type index for processing
        cache_version: Cache version string (default: 'v1')
        
    Returns:
        Path to the created temporary directory
    """
    # Get cache directory - use platform utils if available, else use temp
    if train_utils:
        cache_dir = train_utils.parser_cache_dir()
    else:
        import tempfile
        cache_dir = tempfile.gettempdir()
    
    temp_dir = os.path.join(
        cache_dir, 
        cache_version, 
        f"{src_fileid}_{learn_type}_mineru"
    )
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir