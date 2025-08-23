"""
GPTBase adapter package for MinerU integration.

This package contains GPTBase-specific implementations and utilities.
"""

from .adapter import GPTBaseAdapter, MinerUExtractor
from ..base_parser import ProcessingResult

__all__ = ['GPTBaseAdapter', 'MinerUExtractor', 'ProcessingResult']