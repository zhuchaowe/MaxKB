"""
GPTBase-specific configuration extensions.

This module extends the base configuration with GPTBase-specific settings.
"""

from ..config_base import MinerUConfig
from .gptbase_utils import GPTBaseUtils


class GPTBaseMinerUConfig(MinerUConfig):
    """GPTBase-specific configuration for MinerU"""
    
    def __post_init__(self):
        """Initialize with GPTBase-specific settings"""
        # Call parent initialization first
        super().__post_init__()
        
        # Get GPTBase settings
        platform_settings = GPTBaseUtils.get_settings()
        
        # Update configuration with GPTBase settings
        if platform_settings:
            # API keys
            self.llm_api_key = platform_settings.get('advanced_parser_key') or self.llm_api_key
            self.multimodal_api_key = platform_settings.get('advanced_parser_key') or self.multimodal_api_key
            
            # Processing parameters
            self.max_concurrent_uploads = platform_settings.get('max_concurrent_uploads', self.max_concurrent_uploads)
            self.max_concurrent_api_calls = platform_settings.get('max_concurrent_api_calls', self.max_concurrent_api_calls)
            self.max_image_size_mb = platform_settings.get('max_image_size_mb', self.max_image_size_mb)
            self.compression_quality = platform_settings.get('compression_quality', self.compression_quality)
            self.upload_max_retries = platform_settings.get('upload_max_retries', self.upload_max_retries)
            self.upload_retry_delay = platform_settings.get('upload_retry_delay', self.upload_retry_delay)
            
            # Cache settings
            self.enable_cache = platform_settings.get('mineru_parser_cache', self.enable_cache)
            self.cache_version = platform_settings.get('mineru_parser_version', self.cache_version)
    
    def get_learn_info(self, learn_type: int) -> dict:
        """Get learn_info configuration from GPTBase"""
        return GPTBaseUtils.get_learn_info(learn_type)
    
    def get_model_config(self, model_type: int, use_llm: bool = False) -> dict:
        """Get model configuration from GPTBase"""
        return GPTBaseUtils.get_model_config(model_type, use_llm)