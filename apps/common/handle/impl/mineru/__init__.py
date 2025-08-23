"""
MinerU-based PDF/PPT parsing module.

This module provides comprehensive document parsing capabilities using MinerU,
supporting both PPT and PDF files with advanced AI-powered content extraction.

Available adapters:
- maxkb_adapter: For MaxKB platform integration
- gbase_adapter: For GPTBase platform integration
"""

from .base_parser import ProcessingResult
from .config_base import MinerUConfig
from .utils import PDFDetector, FileConverter
from .flowchart_plugin import FlowchartPlugin

__all__ = [
    'ProcessingResult', 
    'MinerUConfig', 
    'PDFDetector', 
    'FileConverter',
    'FlowchartPlugin'
]