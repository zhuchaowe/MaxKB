"""
MaxKB 文件存储客户端

为 MinerU 提供文件和图片上传功能
"""

import os
import hashlib
from typing import Optional
from django.core.files.uploadedfile import SimpleUploadedFile

from .logger import get_module_logger
logger = get_module_logger('file_storage_client')
from knowledge.models import File, FileSourceType


class FileStorageClient:
    """MaxKB 文件存储客户端"""
    
    def __init__(self, knowledge_id: str = None):
        """
        初始化文件存储客户端
        
        Args:
            knowledge_id: 知识库ID
        """
        self.knowledge_id = knowledge_id
        self.logger = logger
    
    async def upload_image(self, image_path: str, image_name: str = None) -> str:
        """
        上传图片到 MaxKB 文件存储
        
        Args:
            image_path: 图片路径
            image_name: 图片名称（可选）
            
        Returns:
            图片访问URL
        """
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            # 读取图片文件
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # 生成文件名
            if not image_name:
                image_name = os.path.basename(image_path)
            
            # 计算文件哈希
            file_hash = hashlib.md5(image_data).hexdigest()
            
            # 创建文件对象
            file_obj = File(
                file_name=image_name,
                file_size=len(image_data),
                source_type=FileSourceType.KNOWLEDGE if self.knowledge_id else FileSourceType.COMMON,
                source_id=self.knowledge_id or 'mineru_images'
            )
            
            # 保存文件
            file_obj.save(image_data)
            
            # 返回文件URL
            file_url = f"/api/file/{file_obj.id}"
            
            self.logger.info(f"Image uploaded successfully: {image_name} -> {file_url}")
            return file_url
            
        except Exception as e:
            self.logger.error(f"Failed to upload image {image_path}: {str(e)}")
            raise
    
    async def upload_file(self, file_path: str, file_name: str = None) -> str:
        """
        上传文件到 MaxKB 文件存储
        
        Args:
            file_path: 文件路径
            file_name: 文件名称（可选）
            
        Returns:
            文件访问URL
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # 读取文件
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # 生成文件名
            if not file_name:
                file_name = os.path.basename(file_path)
            
            # 创建文件对象
            file_obj = File(
                file_name=file_name,
                file_size=len(file_data),
                source_type=FileSourceType.KNOWLEDGE if self.knowledge_id else FileSourceType.COMMON,
                source_id=self.knowledge_id or 'mineru_files'
            )
            
            # 保存文件
            file_obj.save(file_data)
            
            # 返回文件URL
            file_url = f"/api/file/{file_obj.id}"
            
            self.logger.info(f"File uploaded successfully: {file_name} -> {file_url}")
            return file_url
            
        except Exception as e:
            self.logger.error(f"Failed to upload file {file_path}: {str(e)}")
            raise
    
    def cleanup_temp_files(self, temp_dir: str):
        """
        清理临时文件
        
        Args:
            temp_dir: 临时目录路径
        """
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                self.logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup temp directory {temp_dir}: {str(e)}")