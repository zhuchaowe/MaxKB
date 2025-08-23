"""
GPTBase-specific utilities and wrappers.

This module encapsulates all GPTBase-specific dependencies like gzero, loader, etc.
"""

import os
from typing import Any, Dict, Optional
from .logger import logger


class GPTBaseUtils:
    """Utilities for GPTBase-specific functionality"""
    
    @staticmethod
    def get_settings() -> Dict[str, Any]:
        """Get GPTBase settings"""
        try:
            from gptbase import settings
            return {
                'api_key': getattr(settings, 'OPENAI_API_KEY', None),
                'api_url': getattr(settings, 'OPENAI_API_URL', 'https://api.openai.com'),
                'model': getattr(settings, 'DEFAULT_MODEL', 'gpt-4o'),
                'advanced_parser_key': getattr(settings, 'ADVANCED_PARSER_KEY_OPENAI', None),
                'max_concurrent_uploads': getattr(settings, 'MAX_CONCURRENT_UPLOADS', 5),
                'max_concurrent_api_calls': getattr(settings, 'MAX_CONCURRENT_API_CALLS', 3),
                'max_image_size_mb': getattr(settings, 'MAX_IMAGE_SIZE_MB', 5.0),
                'compression_quality': getattr(settings, 'COMPRESSION_QUALITY', 85),
                'upload_max_retries': getattr(settings, 'UPLOAD_MAX_RETRIES', 3),
                'upload_retry_delay': getattr(settings, 'UPLOAD_RETRY_DELAY', 1.0),
                'mineru_parser_cache': getattr(settings, 'MINERU_PARSER_CACHE', True),
                'mineru_parser_version': getattr(settings, 'MINERU_PARSER_VERSION', '101'),
            }
        except ImportError:
            logger.warning("gptbase settings not available, using defaults")
            return {}
    
    @staticmethod
    def get_learn_info(learn_type: int) -> dict:
        """Get learn_info configuration"""
        try:
            from loader.learn_infos import get_learn_info
            return get_learn_info(learn_type)
        except ImportError:
            logger.warning(f"loader.learn_infos not available, returning empty dict for learn_type {learn_type}")
            return {}
    
    @staticmethod
    def get_model_config(model_type: int, use_llm: bool = False) -> dict:
        """Get model configuration"""
        try:
            from loader.learn_infos import get_model_config
            return get_model_config(model_type, use_llm)
        except ImportError:
            logger.warning(f"loader.learn_infos not available, returning empty dict for model_type {model_type}")
            return {}
    
    @staticmethod
    async def upload_file_to_s3(filepath: str, options: Dict[str, Any] = None) -> str:
        """
        Upload file (PDF or image) using GPTBase's upload function with S3 configuration.
        
        This handles the special domain replacement logic for GPTBase.
        """
        try:
            from loader.upload import upload_image
            from gptbase import settings
            
            # Extract src_fileid from options if provided
            src_fileid = options.get('src_fileid', '') if options else ''
            
            # Generate filename
            file_ext = os.path.splitext(filepath)[1] or '.pdf'
            file_name = f"mineru_{src_fileid}{file_ext}"
            
            # Prepare S3 options
            s3_options = {
                "region": getattr(settings, 'AWS_S3_REGION', 'us-east-1'),
                "id": getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                "key": getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                "name": getattr(settings, 'AWS_S3_BUCKET_NAME', None)
            }
            
            # Get domain and storage settings
            domain = getattr(settings, 'DOMAIN', None)
            storage = getattr(settings, 'FILE_STORAGE', 'S3')
            
            logger.info(f"mineru-api: uploading file using upload_image: {file_name}")
            
            # Call upload_image directly
            result = await upload_image(
                filepath,
                file_name,
                None,  # file_suffix - will be extracted from filename
                s3_options=s3_options,
                domain=domain,
                storage=storage
            )
            
            # Extract URL from result
            if isinstance(result, tuple):
                file_url = result[0]
            else:
                file_url = result
            
            # GPTBase-specific domain replacement
            if 'https://prd-mygpt.s3.ap-northeast-1.amazonaws.com' in file_url:
                file_url = file_url.replace(
                    'https://prd-mygpt.s3.ap-northeast-1.amazonaws.com',
                    'https://prd-mygpt-s3.gbase.ai'
                )
            
            logger.info(f"mineru-api: file uploaded successfully: {file_url}")
            return file_url
            
        except ImportError as e:
            logger.error(f"Failed to import upload_image: {e}")
            return filepath  # Return original path as fallback
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise
    
    @staticmethod
    def get_image_optimizer():
        """Get GPTBase's ImageOptimizer"""
        try:
            from loader.image_optimizer import ImageOptimizer
            return ImageOptimizer
        except ImportError:
            logger.warning("loader.image_optimizer not available")
            return None
    
    @staticmethod
    def set_trace_id(trace_id: str):
        """Set trace ID for current context"""
        try:
            from loader.trace import set_trace_id
            set_trace_id(trace_id)
        except ImportError:
            logger.debug(f"Trace ID would be set to: {trace_id}")
    
    @staticmethod
    def get_train_utils():
        """Get train utils"""
        try:
            from loader.train import utils
            return utils
        except ImportError:
            logger.warning("loader.train.utils not available")
            return None


class GZeroUtils:
    """Utilities for gzero-specific functionality"""
    
    @staticmethod
    async def gzero_upload(file_path: str, options: Any = None) -> str:
        """Wrapper for gzero_upload"""
        try:
            from loader.gzero import gzero_upload
            if options:
                return await gzero_upload(file_path, options)
            else:
                return await gzero_upload(file_path)
        except ImportError:
            logger.warning("gzero_upload not available, returning original path")
            return file_path
    
    @staticmethod
    async def gzero_lock_enter(temp_dir: str):
        """Wrapper for gzero_lock_enter"""
        try:
            from loader.gzero import gzero_lock_enter
            await gzero_lock_enter(temp_dir=temp_dir)
        except ImportError:
            # Fallback: just ensure directory exists
            os.makedirs(temp_dir, exist_ok=True)
            logger.debug(f"Entered lock for {temp_dir} (fallback)")
    
    @staticmethod
    async def gzero_lock_release(temp_dir: str):
        """Wrapper for gzero_lock_release"""
        try:
            from loader.gzero import gzero_lock_release
            await gzero_lock_release(temp_dir=temp_dir)
        except ImportError:
            logger.debug(f"Released lock for {temp_dir} (fallback)")
    
    @staticmethod
    async def gzero_vllm_proc(*args, **kwargs):
        """Wrapper for gzero_vllm_proc"""
        try:
            from loader.gzero import gzero_vllm_proc
            return await gzero_vllm_proc(*args, **kwargs)
        except ImportError:
            logger.warning("gzero_vllm_proc not available")
            return None
    
    @staticmethod
    async def gzero_vllm_page_filter(*args, **kwargs):
        """Wrapper for gzero_vllm_page_filter"""
        try:
            from loader.gzero import gzero_vllm_page_filter
            return await gzero_vllm_page_filter(*args, **kwargs)
        except ImportError:
            logger.warning("gzero_vllm_page_filter not available")
            return None