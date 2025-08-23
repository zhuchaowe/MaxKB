"""
Platform-independent configuration module for MinerU-based parsing.

This module provides default configuration that can be overridden by platform adapters.
"""

import os
from typing import List, Optional
from dataclasses import dataclass
from .logger import get_module_logger
logger = get_module_logger('config_base')


@dataclass
class MinerUConfig:
    """Configuration class for MinerU parsing system - platform independent"""
    
    # API Configuration
    mineru_api_key: Optional[str] = None
    mineru_api_url: str = "https://mineru.net"
    mineru_api_type: str = "cloud"  # "cloud" or "self_hosted"
    
    # LLM Configuration
    llm_api_key: Optional[str] = None
    llm_api_url: str = "https://api.openai.com"
    llm_model: str = "gpt-4o"
    
    # Multimodal Model Configuration
    multimodal_api_key: Optional[str] = None
    multimodal_api_url: str = "https://api.openai.com"
    multimodal_model: str = "gpt-4-vision-preview"
    
    # File Processing Configuration
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    supported_formats: List[str] = None
    
    # PPT Conversion Configuration
    libreoffice_path: str = "libreoffice"
    conversion_timeout: int = 300  # 5 minutes
    
    # Processing Parameters
    max_concurrent_uploads: int = 5
    max_concurrent_api_calls: int = 3
    max_image_size_mb: float = 5.0
    compression_quality: int = 85
    upload_max_retries: int = 3
    upload_retry_delay: float = 1.0
    
    # Batch Processing Configuration
    batch_processing_enabled: bool = True
    batch_size: int = 20
    batch_processing_threshold: int = 20
    
    # Retry Configuration
    api_max_retries: int = 3
    api_retry_delay: float = 2.0
    api_retry_backoff: float = 2.0
    api_retry_max_delay: float = 30.0
    retry_on_errors: List[str] = None
    
    # Context-aware Processing Configuration
    enable_context_extraction: bool = True
    context_window_size: int = 2
    context_extraction_mode: str = "page"
    max_context_tokens: int = 1000
    filter_content_types: List[str] = None
    use_context_for_images: bool = True
    
    # Image Processing Configuration
    max_images_per_page: int = 10
    max_images_per_document: int = 200
    filter_meaningless_images: bool = True
    min_image_size: int = 10000
    max_image_size: int = 10000000
    min_image_width: int = 100
    min_image_height: int = 100
    min_image_size_kb: float = 10.0
    max_image_width: int = 10000
    max_image_height: int = 10000
    skip_recognition_for_small_images: bool = True
    
    # Multimodal Content Processing
    enable_multimodal_refinement: bool = True
    
    # Prompt Configuration
    use_enhanced_prompts: bool = True
    prompt_temperature: float = 0.0
    
    # Logging Configuration
    log_level: str = "INFO"
    
    # Cache settings
    enable_cache: bool = True
    cache_version: str = "101"
    
    # Queue Processing Configuration
    queue_size: int = 50
    processing_timeout: int = 600
    num_parser_threads: int = 1
    num_refiner_threads: int = 1
    num_recognizer_threads: int = 1
    num_uploader_threads: int = 1
    
    def __post_init__(self):
        """Initialize configuration from environment variables"""
        if self.supported_formats is None:
            self.supported_formats = ['pdf', 'ppt', 'pptx', 'doc', 'docx', 
                                    'png', 'jpg', 'jpeg', 'gif', 'bmp', 
                                    'tiff', 'tif', 'webp', 'svg']
        
        if self.filter_content_types is None:
            self.filter_content_types = ['text', 'title']
        
        # Load from environment variables (platform-independent)
        self.mineru_api_key = os.getenv('MINERU_API_KEY', self.mineru_api_key)
        self.mineru_api_url = os.getenv('MINERU_API_URL', self.mineru_api_url)
        self.mineru_api_type = os.getenv('MINERU_API_TYPE', self.mineru_api_type)
        
        self.max_file_size = int(os.getenv('MAX_FILE_SIZE', str(self.max_file_size)))
        self.libreoffice_path = os.getenv('LIBREOFFICE_PATH', self.libreoffice_path)
        self.conversion_timeout = int(os.getenv('CONVERSION_TIMEOUT', str(self.conversion_timeout)))
        
        # Batch processing
        self.batch_processing_enabled = os.getenv('MINERU_BATCH_PROCESSING', 'true').lower() == 'true'
        self.batch_size = int(os.getenv('MINERU_BATCH_SIZE', str(self.batch_size)))
        self.batch_processing_threshold = int(os.getenv('MINERU_BATCH_THRESHOLD', str(self.batch_processing_threshold)))
        
        # Retry configuration
        self.api_max_retries = int(os.getenv('MINERU_API_MAX_RETRIES', str(self.api_max_retries)))
        self.api_retry_delay = float(os.getenv('MINERU_API_RETRY_DELAY', str(self.api_retry_delay)))
        self.api_retry_backoff = float(os.getenv('MINERU_API_RETRY_BACKOFF', str(self.api_retry_backoff)))
        self.api_retry_max_delay = float(os.getenv('MINERU_API_RETRY_MAX_DELAY', str(self.api_retry_max_delay)))
        
        if self.retry_on_errors is None:
            retry_errors = os.getenv('MINERU_RETRY_ON_ERRORS', '')
            self.retry_on_errors = [e.strip() for e in retry_errors.split(',') if e.strip()] if retry_errors else []
        
        # Context-aware processing
        self.enable_context_extraction = os.getenv('ENABLE_CONTEXT_EXTRACTION', 'true').lower() == 'true'
        self.context_window_size = int(os.getenv('CONTEXT_WINDOW_SIZE', str(self.context_window_size)))
        self.context_extraction_mode = os.getenv('CONTEXT_EXTRACTION_MODE', self.context_extraction_mode)
        self.max_context_tokens = int(os.getenv('MAX_CONTEXT_TOKENS', str(self.max_context_tokens)))
        self.use_context_for_images = os.getenv('USE_CONTEXT_FOR_IMAGES', 'true').lower() == 'true'
        self.use_enhanced_prompts = os.getenv('USE_ENHANCED_PROMPTS', 'true').lower() == 'true'
        
        # Image processing
        self.min_image_width = int(os.getenv('MINERU_MIN_IMAGE_WIDTH', str(self.min_image_width)))
        self.min_image_height = int(os.getenv('MINERU_MIN_IMAGE_HEIGHT', str(self.min_image_height)))
        self.min_image_size_kb = float(os.getenv('MINERU_MIN_IMAGE_SIZE_KB', str(self.min_image_size_kb)))
        self.max_image_width = int(os.getenv('MINERU_MAX_IMAGE_WIDTH', str(self.max_image_width)))
        self.max_image_height = int(os.getenv('MINERU_MAX_IMAGE_HEIGHT', str(self.max_image_height)))
        self.skip_recognition_for_small_images = os.getenv('MINERU_SKIP_SMALL_IMAGES', 'true').lower() == 'true'
        
        # Multimodal
        self.enable_multimodal_refinement = os.getenv('MINERU_MULTIMODAL_REFINEMENT', 'true').lower() == 'true'
        
        # Image filtering
        self.max_images_per_page = int(os.getenv('MINERU_MAX_IMAGES_PER_PAGE', str(self.max_images_per_page)))
        self.max_images_per_document = int(os.getenv('MINERU_MAX_IMAGES_PER_DOCUMENT', str(self.max_images_per_document)))
        self.filter_meaningless_images = os.getenv('MINERU_FILTER_MEANINGLESS', 'true').lower() == 'true'
        self.min_image_size = int(os.getenv('MINERU_MIN_IMAGE_SIZE', str(self.min_image_size)))
        self.max_image_size = int(os.getenv('MINERU_MAX_IMAGE_SIZE', str(self.max_image_size)))
        
        # Queue processing
        self.queue_size = int(os.getenv('MINERU_QUEUE_SIZE', str(self.queue_size)))
        self.processing_timeout = int(os.getenv('MINERU_PROCESSING_TIMEOUT', str(self.processing_timeout)))
        self.num_parser_threads = int(os.getenv('MINERU_PARSER_THREADS', str(self.num_parser_threads)))
        self.num_refiner_threads = int(os.getenv('MINERU_REFINER_THREADS', str(self.num_refiner_threads)))
        self.num_recognizer_threads = int(os.getenv('MINERU_RECOGNIZER_THREADS', str(self.num_recognizer_threads)))
        self.num_uploader_threads = int(os.getenv('MINERU_UPLOADER_THREADS', str(self.num_uploader_threads)))
        
        self.log_level = os.getenv('LOG_LEVEL', self.log_level)
    
    def update_from_platform(self, platform_settings: dict):
        """Update configuration from platform-specific settings"""
        if not platform_settings:
            return
        
        # Update API keys if provided
        if 'llm_api_key' in platform_settings:
            self.llm_api_key = platform_settings['llm_api_key']
        if 'multimodal_api_key' in platform_settings:
            self.multimodal_api_key = platform_settings['multimodal_api_key']
        
        # Update processing parameters
        for key in ['max_concurrent_uploads', 'max_concurrent_api_calls', 
                   'max_image_size_mb', 'compression_quality', 
                   'upload_max_retries', 'upload_retry_delay']:
            if key in platform_settings:
                setattr(self, key, platform_settings[key])
        
        # Update cache settings
        if 'enable_cache' in platform_settings:
            self.enable_cache = platform_settings['enable_cache']
        if 'cache_version' in platform_settings:
            self.cache_version = platform_settings['cache_version']
    
    def validate(self) -> bool:
        """Validate configuration settings"""
        # For self-hosted MinerU, API key is not required
        if self.mineru_api_type == "cloud" and not self.mineru_api_key:
            logger.warning("MINERU_API_KEY not configured for cloud API")
            return False
        
        if self.max_file_size <= 0:
            logger.error("Invalid max_file_size configuration")
            return False
        
        if self.mineru_api_type not in ["cloud", "self_hosted"]:
            logger.error(f"Invalid mineru_api_type: {self.mineru_api_type}")
            return False
        
        return True
    
    # Platform-specific methods - should be overridden by adapters
    def get_learn_info(self, learn_type: int) -> dict:
        """Get learn_info configuration - override in platform adapter"""
        return {}
    
    def get_model_config(self, model_type: int, use_llm: bool = False) -> dict:
        """Get model configuration - override in platform adapter"""
        return {}
    
    async def call_litellm(self, model_type: int, messages: list, use_llm: bool = False, **kwargs) -> any:
        """Call litellm - override in platform adapter if needed"""
        import os
        import litellm
        
        # Get model config from adapter
        model_config = self.get_model_config(model_type, use_llm)
        if not model_config:
            raise ValueError(f"No model config for type {model_type}")
        
        # Set environment variables
        if 'key' in model_config and 'keyname' in model_config:
            os.environ[model_config['keyname']] = model_config['key']
        if model_config.get('base') and model_config.get('basename'):
            os.environ[model_config['basename']] = model_config['base']
        
        # Prepare call kwargs
        call_kwargs = {}
        if model_config.get('base'):
            call_kwargs['api_base'] = model_config['base']
        
        call_kwargs.update(kwargs)
        
        # Handle response_format for non-GPT models
        if 'response_format' in call_kwargs and 'gpt' not in model_config.get('model', '').lower():
            call_kwargs.pop('response_format', None)
        
        # Call litellm
        response = await litellm.acompletion(
            model=model_config['model'],
            messages=messages,
            **call_kwargs
        )
        
        return response