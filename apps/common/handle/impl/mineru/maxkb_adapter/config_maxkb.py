"""
MaxKB-specific configuration extensions.

This module extends the base configuration with MaxKB-specific settings.
"""

import os
from typing import Dict, Any
from ..config_base import MinerUConfig


class MaxKBMinerUConfig(MinerUConfig):
    """MaxKB-specific configuration for MinerU"""
    
    def __post_init__(self):
        """Initialize with MaxKB-specific settings"""
        # Call parent initialization first
        super().__post_init__()
        
        # MaxKB specific settings from environment or defaults
        # 如果环境变量中设置了具体的UUID，使用UUID；否则使用默认值或自动检测
        self.llm_model_id = os.getenv('MAXKB_LLM_MODEL_ID', self._get_default_llm_model_id())
        self.vision_model_id = os.getenv('MAXKB_VISION_MODEL_ID', self._get_default_vision_model_id())
        
        # MaxKB API settings
        self.maxkb_api_key = os.getenv('MAXKB_API_KEY')
        self.maxkb_api_url = os.getenv('MAXKB_API_URL', 'https://api.maxkb.com')
        
        # File storage settings
        self.file_storage_type = os.getenv('MAXKB_STORAGE_TYPE', 'local')  # local, s3, oss
        self.file_storage_path = os.getenv('MAXKB_STORAGE_PATH', '/tmp/maxkb/storage')
        self.file_storage_bucket = os.getenv('MAXKB_STORAGE_BUCKET')
        
        # Model client settings
        self.model_client_timeout = int(os.getenv('MAXKB_MODEL_TIMEOUT', '60'))
        self.model_client_max_retries = int(os.getenv('MAXKB_MODEL_MAX_RETRIES', '3'))
        
        # Image optimizer settings
        self.image_optimizer_enabled = os.getenv('MAXKB_IMAGE_OPTIMIZER', 'true').lower() == 'true'
        self.image_optimizer_quality = int(os.getenv('MAXKB_IMAGE_QUALITY', '85'))
        self.image_optimizer_max_width = int(os.getenv('MAXKB_IMAGE_MAX_WIDTH', '2048'))
        self.image_optimizer_max_height = int(os.getenv('MAXKB_IMAGE_MAX_HEIGHT', '2048'))
        
        # Override base settings if MaxKB specific values exist
        if self.maxkb_api_key:
            self.llm_api_key = self.maxkb_api_key
            self.multimodal_api_key = self.maxkb_api_key
        
        # MaxKB specific processing parameters
        self.max_concurrent_uploads = int(os.getenv('MAXKB_MAX_CONCURRENT_UPLOADS', str(self.max_concurrent_uploads)))
        self.max_concurrent_api_calls = int(os.getenv('MAXKB_MAX_CONCURRENT_API_CALLS', str(self.max_concurrent_api_calls)))
    
    def get_model_client_config(self) -> Dict[str, Any]:
        """Get MaxKB model client configuration"""
        return {
            'llm_model_id': self.llm_model_id,
            'vision_model_id': self.vision_model_id,
            'api_key': self.maxkb_api_key,
            'api_url': self.maxkb_api_url,
            'timeout': self.model_client_timeout,
            'max_retries': self.model_client_max_retries
        }
    
    def get_file_storage_config(self) -> Dict[str, Any]:
        """Get MaxKB file storage configuration"""
        return {
            'type': self.file_storage_type,
            'path': self.file_storage_path,
            'bucket': self.file_storage_bucket
        }
    
    def get_image_optimizer_config(self) -> Dict[str, Any]:
        """Get MaxKB image optimizer configuration"""
        return {
            'enabled': self.image_optimizer_enabled,
            'quality': self.image_optimizer_quality,
            'max_width': self.image_optimizer_max_width,
            'max_height': self.image_optimizer_max_height
        }
    
    def get_learn_info(self, learn_type: int) -> dict:
        """Get learn_info for MaxKB - map from model IDs"""
        # MaxKB doesn't use learn_type, return empty or mapped config
        return {
            'model_id': self.llm_model_id,
            'vision_model_id': self.vision_model_id
        }
    
    def get_model_config(self, model_type: int, use_llm: bool = False) -> dict:
        """Get model configuration for MaxKB"""
        # Map model_type to MaxKB model configuration
        if use_llm:
            return {
                'model': self.llm_model_id,
                'api_key': self.maxkb_api_key,
                'api_url': self.maxkb_api_url,
                'keyname': 'MAXKB_API_KEY',
                'key': self.maxkb_api_key
            }
        else:
            return {
                'model': self.vision_model_id,
                'api_key': self.maxkb_api_key,
                'api_url': self.maxkb_api_url,
                'keyname': 'MAXKB_API_KEY',
                'key': self.maxkb_api_key
            }
    
    async def call_litellm(self, model_type: int, messages: list, use_llm: bool = False, **kwargs) -> any:
        """Override litellm call to use MaxKB model client"""
        from .maxkb_model_client import maxkb_model_client
        from .logger import get_module_logger
        logger = get_module_logger('config_maxkb')
        import json
        
        try:
            # Determine which model to use
            if use_llm:
                model_id = self.llm_model_id
            else:
                model_id = self.vision_model_id
            
            logger.debug(f"MaxKB: Calling model {model_id} with {len(messages)} messages")
            
            # Check if this is a vision request (has images)
            has_images = False
            for msg in messages:
                if isinstance(msg.get('content'), list):
                    for content_item in msg['content']:
                        if isinstance(content_item, dict) and content_item.get('type') == 'image_url':
                            has_images = True
                            break
            
            # Call appropriate method based on content type
            if has_images:
                # Extract image and text for vision model
                image_path = None
                prompt = ""
                for msg in messages:
                    if isinstance(msg.get('content'), list):
                        for content_item in msg['content']:
                            if content_item.get('type') == 'text':
                                prompt = content_item.get('text', '')
                            elif content_item.get('type') == 'image_url':
                                image_url = content_item.get('image_url', {})
                                if isinstance(image_url, dict):
                                    url = image_url.get('url', '')
                                    if url.startswith('data:'):
                                        # Handle base64 image
                                        import base64
                                        import tempfile
                                        # Extract base64 data
                                        base64_data = url.split(',')[1] if ',' in url else url
                                        image_data = base64.b64decode(base64_data)
                                        # Save to temp file
                                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                                            tmp.write(image_data)
                                            image_path = tmp.name
                                    else:
                                        image_path = url
                
                if image_path:
                    response_text = await maxkb_model_client.vision_completion(
                        model_id=model_id,
                        image_path=image_path,
                        prompt=prompt,
                        **kwargs
                    )
                else:
                    # Fallback to text completion
                    response_text = await maxkb_model_client.chat_completion(
                        model_id=model_id,
                        messages=messages,
                        **kwargs
                    )
            else:
                # Regular text completion
                response_text = await maxkb_model_client.chat_completion(
                    model_id=model_id,
                    messages=messages,
                    **kwargs
                )
            
            # Create response object similar to litellm response
            class MockResponse:
                def __init__(self, content):
                    self.choices = [type('obj', (object,), {
                        'message': type('obj', (object,), {
                            'content': content
                        })()
                    })()]
                    # Add usage attribute for compatibility
                    self.usage = type('obj', (object,), {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    })()
            
            return MockResponse(response_text)
            
        except Exception as e:
            logger.error(f"MaxKB model call failed: {str(e)}")
            # Return a mock response with error message
            class MockResponse:
                def __init__(self, content):
                    self.choices = [type('obj', (object,), {
                        'message': type('obj', (object,), {
                            'content': content
                        })()
                    })()]
                    # Add usage attribute for compatibility
                    self.usage = type('obj', (object,), {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    })()
            
            # Return empty response on error to continue processing
            return MockResponse("")
    
    def _get_default_llm_model_id(self) -> str:
        """获取默认的LLM模型ID"""
        try:
            # 尝试从数据库获取第一个可用的LLM模型
            from django.db.models import QuerySet
            from models_provider.models import Model
            
            model = QuerySet(Model).filter(
                model_type__in=['LLM', 'CHAT']
            ).first()
            
            if model:
                return str(model.id)
        except Exception:
            pass
        
        # 返回默认值
        return 'default-llm'
    
    def _get_default_vision_model_id(self) -> str:
        """获取默认的视觉模型ID"""
        try:
            # 尝试从数据库获取第一个可用的视觉或多模态模型
            from django.db.models import QuerySet
            from models_provider.models import Model
            
            # 首先尝试获取专门的视觉模型
            model = QuerySet(Model).filter(
                model_type__in=['VISION', 'MULTIMODAL']
            ).first()
            
            # 如果没有，获取任意LLM模型（许多LLM支持视觉）
            if not model:
                model = QuerySet(Model).filter(
                    model_type__in=['LLM', 'CHAT']
                ).first()
            
            if model:
                return str(model.id)
        except Exception:
            pass
        
        # 返回默认值
        return 'default-vision'