"""
图片优化器模块

提供图片处理、优化和批量处理功能
"""

import os
import asyncio
from typing import List, Dict, Any, Callable
from PIL import Image
import io
from .logger import get_module_logger
logger = get_module_logger('image_optimizer')


class ImageOptimizer:
    """图片优化器"""
    
    def __init__(self, max_concurrent_uploads: int = 5,
                 max_concurrent_api_calls: int = 3,
                 max_image_size_mb: float = 5.0,
                 compression_quality: int = 85,
                 upload_max_retries: int = 3,
                 upload_retry_delay: float = 1.0):
        """
        初始化图片优化器
        
        Args:
            max_concurrent_uploads: 最大并发上传数
            max_concurrent_api_calls: 最大并发API调用数
            max_image_size_mb: 最大图片大小(MB)
            compression_quality: 压缩质量
            upload_max_retries: 上传最大重试次数
            upload_retry_delay: 上传重试延迟
        """
        self.max_concurrent_uploads = max_concurrent_uploads
        self.max_concurrent_api_calls = max_concurrent_api_calls
        self.max_image_size_mb = max_image_size_mb
        self.compression_quality = compression_quality
        self.upload_max_retries = upload_max_retries
        self.upload_retry_delay = upload_retry_delay
        self.logger = logger
    
    async def cleanup(self):
        """清理资源"""
        pass
    
    async def batch_classify_images(self, 
                                   images: List[str],
                                   classify_func: Callable,
                                   learn_type: Any,
                                   temp_dir: str,
                                   src_name: str) -> Dict[str, Dict]:
        """
        批量分类图片
        
        Args:
            images: 图片文件名列表
            classify_func: 分类函数
            learn_type: 学习类型
            temp_dir: 临时目录
            src_name: 源文件名
            
        Returns:
            图片分类结果字典
        """
        results = {}
        
        # 顺序处理图片，避免并发压力
        for image_filename in images:
            image_path = os.path.join(temp_dir, image_filename)
            try:
                result = await classify_func(
                    learn_type,
                    image_path,
                    temp_dir,
                    src_name
                )
                results[image_filename] = result
            except Exception as e:
                self.logger.error(f"Failed to classify image {image_filename}: {str(e)}")
                results[image_filename] = {
                    'error': str(e),
                    'is_meaningful': False
                }
        
        return results
    
    async def batch_upload_images(self,
                                 images: List[str],
                                 upload_func: Callable,
                                 temp_dir: str) -> Dict[str, str]:
        """
        批量上传图片
        
        Args:
            images: 图片文件名列表
            upload_func: 上传函数
            temp_dir: 临时目录
            
        Returns:
            图片上传结果字典 (filename -> url)
        """
        results = {}
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        async def upload_with_semaphore(image_filename):
            async with semaphore:
                image_path = os.path.join(temp_dir, image_filename)
                for retry in range(self.upload_max_retries):
                    try:
                        url = await upload_func(image_path)
                        return image_filename, url
                    except Exception as e:
                        if retry < self.upload_max_retries - 1:
                            await asyncio.sleep(self.upload_retry_delay * (retry + 1))
                        else:
                            self.logger.error(f"Failed to upload {image_filename} after {self.upload_max_retries} retries: {str(e)}")
                            return image_filename, None
        
        # 并发上传
        tasks = [upload_with_semaphore(img) for img in images]
        upload_results = await asyncio.gather(*tasks)
        
        for filename, url in upload_results:
            if url:
                results[filename] = url
        
        return results
    
    def compress_image(self, image_path: str, max_size_mb: float = None) -> bytes:
        """
        压缩图片
        
        Args:
            image_path: 图片路径
            max_size_mb: 最大大小(MB)
            
        Returns:
            压缩后的图片字节
        """
        if max_size_mb is None:
            max_size_mb = self.max_image_size_mb
        
        max_size_bytes = max_size_mb * 1024 * 1024
        
        with Image.open(image_path) as img:
            # 转换为RGB（如果需要）
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # 逐步压缩直到满足大小要求
            quality = self.compression_quality
            while quality > 10:
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
                
                if buffer.tell() <= max_size_bytes:
                    return buffer.getvalue()
                
                quality -= 10
            
            # 如果还是太大，缩小尺寸
            width, height = img.size
            while width > 100 and height > 100:
                width = width // 2
                height = height // 2
                img = img.resize((width, height), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=30, optimize=True)
                
                if buffer.tell() <= max_size_bytes:
                    return buffer.getvalue()
            
            # 返回最小的版本
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=10, optimize=True)
            return buffer.getvalue()