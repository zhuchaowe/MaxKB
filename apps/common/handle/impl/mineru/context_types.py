"""
Context-aware data types for MinerU parsing.

This module defines data structures for storing and passing context information
throughout the parsing pipeline.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class ContextMode(Enum):
    """Context extraction mode"""
    PAGE = "page"  # Extract context based on page boundaries
    CHUNK = "chunk"  # Extract context based on content chunks


@dataclass
class ImageContext:
    """Context information for an image during processing"""
    page_idx: int
    surrounding_text: str
    page_type: str  # 'title', 'content', 'mixed'
    chunk_idx: Optional[int] = None
    token_count: int = 0
    # Additional metadata
    before_text: Optional[str] = None  # Text before the image
    after_text: Optional[str] = None  # Text after the image
    page_title: Optional[str] = None  # Title of the current page if available
    section_headers: List[str] = field(default_factory=list)  # Hierarchical section headers
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'page_idx': self.page_idx,
            'surrounding_text': self.surrounding_text,
            'page_type': self.page_type,
            'chunk_idx': self.chunk_idx,
            'token_count': self.token_count,
            'before_text': self.before_text,
            'after_text': self.after_text,
            'page_title': self.page_title,
            'section_headers': self.section_headers
        }


@dataclass
class ContentElement:
    """Represents a single content element with position information"""
    type: str  # 'text', 'image', 'table', 'equation', etc.
    content: Any  # The actual content
    page_idx: int
    position: int  # Position within the page
    bbox: Optional[List[float]] = None  # Bounding box if available
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageContext:
    """Context information for a complete page"""
    page_idx: int
    page_type: str  # 'title', 'content', 'mixed'
    title: Optional[str] = None
    content_elements: List[ContentElement] = field(default_factory=list)
    text_content: str = ""  # Full text content of the page
    token_count: int = 0
    
    def get_text_around_position(self, position: int, window_size: int = 500) -> tuple[str, str]:
        """Get text before and after a specific position"""
        # Find text elements around the position
        before_texts = []
        after_texts = []
        
        for element in self.content_elements:
            if element.type == 'text':
                if element.position < position:
                    before_texts.append(element.content)
                elif element.position > position:
                    after_texts.append(element.content)
        
        # Join and truncate to window size
        before_text = ' '.join(before_texts)[-window_size:] if before_texts else ""
        after_text = ' '.join(after_texts)[:window_size] if after_texts else ""
        
        return before_text, after_text


@dataclass
class EnhancedProcessingResult:
    """Enhanced processing result with context information"""
    success: bool
    content: str  # The main processed content
    chunks: List[Dict[str, Any]]  # Content chunks with metadata
    images: Dict[str, str]  # Image mappings
    image_contexts: Dict[str, ImageContext] = field(default_factory=dict)  # Image context data
    page_contexts: List[PageContext] = field(default_factory=list)  # Page-level context
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def get_image_context(self, image_id: str) -> Optional[ImageContext]:
        """Get context for a specific image"""
        return self.image_contexts.get(image_id)
    
    def get_page_context(self, page_idx: int) -> Optional[PageContext]:
        """Get context for a specific page"""
        for page_ctx in self.page_contexts:
            if page_ctx.page_idx == page_idx:
                return page_ctx
        return None