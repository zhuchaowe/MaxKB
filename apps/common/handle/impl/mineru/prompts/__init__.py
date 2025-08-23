"""
Prompts module for MinerU.

This module contains all prompts used by the MinerU parser for various LLM tasks.
"""

from .image_classification import (
    format_image_classification_prompt,
    IMAGE_CLASSIFICATION_SIMPLE,
    IMAGE_CLASSIFICATION_CONTEXT_BASE
)

from .markdown_generation import (
    MARKDOWN_GENERATION_PROMPT,
    format_markdown_generation_prompt
)

__all__ = [
    'format_image_classification_prompt',
    'IMAGE_CLASSIFICATION_SIMPLE',
    'IMAGE_CLASSIFICATION_CONTEXT_BASE',
    'MARKDOWN_GENERATION_PROMPT',
    'format_markdown_generation_prompt',
]