"""
MaxKB 模型调用客户端

该模块提供了 MinerU 使用 MaxKB 模型系统的接口，
替代原有的 litellm 调用方式。
"""

import json
from typing import Dict, List, Optional, Any
from django.db.models import QuerySet
from asgiref.sync import sync_to_async

from .logger import get_module_logger
logger = get_module_logger('maxkb_model_client')
from models_provider.models import Model
from models_provider.tools import get_model


class MaxKBModelClient:
    """MaxKB 模型调用客户端"""
    
    def __init__(self):
        """初始化 MaxKB 模型客户端"""
        self.logger = logger
        
    def _get_llm_model_sync(self, model_id: str):
        """
        同步方式获取大语言模型实例
        
        Args:
            model_id: 模型ID（UUID）或模型名称
            
        Returns:
            模型实例
        """
        try:
            import uuid
            
            # 首先尝试作为UUID查找
            model = None
            try:
                # 验证是否是有效的UUID
                uuid.UUID(model_id)
                model = QuerySet(Model).filter(id=model_id).first()
            except (ValueError, AttributeError):
                # 不是UUID，尝试按名称查找
                self.logger.debug(f"'{model_id}' is not a UUID, trying to find by name")
                model = QuerySet(Model).filter(name=model_id).first()
                
                # 如果还没找到，尝试按provider和model_name组合查找
                if not model:
                    # 尝试匹配常见的模型名称模式
                    if 'gpt' in model_id.lower():
                        model = QuerySet(Model).filter(
                            provider__contains='openai'
                        ).first()
                    elif 'claude' in model_id.lower():
                        model = QuerySet(Model).filter(
                            provider__contains='anthropic'
                        ).first()
            
            if not model:
                # 如果还是找不到，获取第一个可用的LLM模型
                self.logger.warning(f"Model '{model_id}' not found, trying to get default LLM model")
                model = QuerySet(Model).filter(
                    model_type__in=['LLM', 'CHAT']
                ).first()
                
                if model:
                    self.logger.info(f"Using default LLM model: {model.name} (ID: {model.id}, model_name: {model.model_name})")
            
            if not model:
                raise ValueError(f"No LLM model available (requested: {model_id})")
            
            # 获取 LLM 模型实例
            llm_model = get_model(model)
            return llm_model
            
        except Exception as e:
            self.logger.error(f"Failed to get LLM model {model_id}: {str(e)}")
            # 返回None而不是抛出异常，让调用方处理
            return None
    
    async def get_llm_model(self, model_id: str):
        """
        异步方式获取大语言模型实例
        
        Args:
            model_id: 模型ID（UUID）或模型名称
            
        Returns:
            模型实例
        """
        return await sync_to_async(self._get_llm_model_sync)(model_id)
    
    def _get_vision_model_sync(self, model_id: str):
        """
        同步方式获取视觉模型实例
        
        Args:
            model_id: 模型ID（UUID）或模型名称
            
        Returns:
            模型实例
        """
        try:
            import uuid
            
            # 首先尝试作为UUID查找
            model = None
            try:
                # 验证是否是有效的UUID
                uuid.UUID(model_id)
                model = QuerySet(Model).filter(id=model_id).first()
            except (ValueError, AttributeError):
                # 不是UUID，尝试按名称查找
                self.logger.debug(f"'{model_id}' is not a UUID, trying to find by name")
                model = QuerySet(Model).filter(name=model_id).first()
                
                # 如果还没找到，尝试按provider和model_name组合查找
                if not model:
                    # 尝试匹配常见的视觉模型名称模式
                    if 'vision' in model_id.lower() or 'gpt-4' in model_id.lower():
                        model = QuerySet(Model).filter(
                            provider__contains='openai'
                        ).first()
                    elif 'claude' in model_id.lower():
                        model = QuerySet(Model).filter(
                            provider__contains='anthropic'
                        ).first()
            
            if not model:
                # 如果还是找不到，尝试获取第一个支持视觉的模型
                self.logger.warning(f"Model '{model_id}' not found, trying to get default vision model")
                # 首先尝试获取专门的视觉模型
                model = QuerySet(Model).filter(
                    model_type__in=['VISION', 'MULTIMODAL']
                ).first()
                
                # 如果没有专门的视觉模型，获取支持视觉的LLM模型
                if not model:
                    model = QuerySet(Model).filter(
                        model_type__in=['LLM', 'CHAT']
                    ).first()
                
                if model:
                    self.logger.info(f"Using default vision model: {model.name} (ID: {model.id}, model_name: {model.model_name})")
            
            if not model:
                raise ValueError(f"No vision model available (requested: {model_id})")
            
            # 获取视觉模型实例
            vision_model = get_model(model)
            return vision_model
            
        except Exception as e:
            self.logger.error(f"Failed to get vision model {model_id}: {str(e)}")
            # 返回None而不是抛出异常，让调用方处理
            return None
    
    async def get_vision_model(self, model_id: str):
        """
        异步方式获取视觉模型实例
        
        Args:
            model_id: 模型ID（UUID）或模型名称
            
        Returns:
            模型实例
        """
        return await sync_to_async(self._get_vision_model_sync)(model_id)
    
    async def chat_completion(self, model_id: str, messages: List[Dict], **kwargs) -> str:
        """
        调用大语言模型进行对话完成
        
        Args:
            model_id: 模型ID
            messages: 消息列表
            **kwargs: 其他参数
            
        Returns:
            模型响应文本
        """
        try:
            self.logger.info(f"Calling chat completion with model_id: {model_id}")
            # 获取模型实例
            llm_model = await self.get_llm_model(model_id)
            
            if not llm_model:
                self.logger.warning(f"No model available for {model_id}, returning error JSON")
                import json
                return json.dumps({
                    "type": "brief_description",
                    "title": "No Model",
                    "description": "LLM model not available"
                })
            
            # 调用模型 - 使用 sync_to_async 包装同步调用
            response = await sync_to_async(llm_model.invoke)(messages)
            
            # 提取响应内容
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                return str(response)
                
        except Exception as e:
            self.logger.error(f"Chat completion failed for model {model_id}: {str(e)}")
            # 返回错误JSON而不是空字符串
            import json
            return json.dumps({
                "type": "brief_description",
                "title": "Error",
                "description": f"Chat completion failed: {str(e)}"
            })
    
    async def vision_completion(self, model_id: str, image_path: str, prompt: str, **kwargs) -> str:
        """
        调用视觉模型进行图片理解
        
        Args:
            model_id: 模型ID
            image_path: 图片路径
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            模型响应文本
        """
        try:
            self.logger.info(f"Calling vision completion with model_id: {model_id}")
            # 获取视觉模型实例
            vision_model = await self.get_vision_model(model_id)
            
            if not vision_model:
                self.logger.warning(f"No vision model available for {model_id}, returning error JSON")
                # Return a valid JSON response instead of empty string
                import json
                return json.dumps({
                    "type": "brief_description",
                    "title": "No Model",
                    "description": "Vision model not available"
                })
            else:
                # Log actual model name if available
                actual_model_name = getattr(vision_model, 'model_name', 'unknown')
                self.logger.info(f"Vision model instance created with actual model_name: {actual_model_name}")
            
            # 读取图片并转换为base64
            import base64
            import os
            
            if not os.path.exists(image_path):
                self.logger.error(f"Image file not found: {image_path}")
                import json
                return json.dumps({
                    "type": "brief_description",
                    "title": "File Error",
                    "description": f"Image file not found: {image_path}"
                })
            
            try:
                with open(image_path, 'rb') as img_file:
                    image_data = img_file.read()
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
            except Exception as e:
                self.logger.error(f"Failed to read/encode image {image_path}: {str(e)}")
                import json
                return json.dumps({
                    "type": "brief_description",
                    "title": "Image Error",
                    "description": f"Failed to read/encode image: {str(e)}"
                })
            
            # 构造消息 - 使用base64编码的图片
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }
            ]
            
            # 调用模型 - 使用 sync_to_async 包装同步调用
            response = await sync_to_async(vision_model.invoke)(messages)
            
            # 提取响应内容
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                return str(response)
                
        except Exception as e:
            self.logger.error(f"Vision completion failed for model {model_id}: {str(e)}")
            # 返回错误JSON而不是空字符串
            import json
            return json.dumps({
                "type": "brief_description",
                "title": "Vision Error",
                "description": f"Vision completion failed: {str(e)}"
            })
    
    async def batch_chat_completion(self, model_id: str, batch_messages: List[List[Dict]], **kwargs) -> List[str]:
        """
        批量调用大语言模型
        
        Args:
            model_id: 模型ID
            batch_messages: 批量消息列表
            **kwargs: 其他参数
            
        Returns:
            批量响应文本列表
        """
        results = []
        for messages in batch_messages:
            try:
                result = await self.chat_completion(model_id, messages, **kwargs)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Batch chat completion error: {str(e)}")
                results.append("")  # 失败时添加空字符串
        
        return results
    
    def _validate_model_sync(self, model_id: str) -> bool:
        """
        同步方式验证模型是否可用
        
        Args:
            model_id: 模型ID
            
        Returns:
            模型是否可用
        """
        try:
            model = QuerySet(Model).filter(id=model_id).first()
            return model is not None
        except Exception:
            return False
    
    async def validate_model(self, model_id: str) -> bool:
        """
        异步方式验证模型是否可用
        
        Args:
            model_id: 模型ID
            
        Returns:
            模型是否可用
        """
        return await sync_to_async(self._validate_model_sync)(model_id)


# 全局客户端实例
maxkb_model_client = MaxKBModelClient()