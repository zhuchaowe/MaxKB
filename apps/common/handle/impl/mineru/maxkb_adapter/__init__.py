"""
MaxKB adapter package for MinerU integration.

This package contains MaxKB-specific implementations and utilities.
"""

# Lazy import to avoid issues when importing just the logger
try:
    from .adapter import MaxKBAdapter, MinerUExtractor
    __all__ = ['MaxKBAdapter', 'MinerUExtractor']
except ImportError:
    # If Django is not set up, provide lazy import
    def get_adapter():
        """Lazy import adapter when Django is not configured"""
        from .adapter import MaxKBAdapter, MinerUExtractor
        return MaxKBAdapter, MinerUExtractor
    __all__ = ['get_adapter']