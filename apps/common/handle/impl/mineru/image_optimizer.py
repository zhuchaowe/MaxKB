import os
import asyncio
import hashlib
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from PIL import Image
import io
import base64
from .logger import get_module_logger
logger = get_module_logger('image_optimizer')
from asyncio import Semaphore
import aiofiles

@dataclass
class ImageInfo:
    """图片信息数据类"""
    filepath: str
    filename: str
    xref: Optional[int] = None
    size: Optional[int] = None
    hash: Optional[str] = None
    compressed: bool = False
    loaded: bool = False
    data: Optional[bytes] = None
    base64_data: Optional[str] = None

class ImageOptimizer:
    """图片优化处理器"""
    
    def __init__(self, 
                 max_concurrent_uploads: int = 5,
                 max_concurrent_api_calls: int = 3,
                 max_image_size_mb: float = 5.0,
                 compression_quality: int = 85,
                 batch_size: int = 10,
                 upload_max_retries: int = 3,
                 upload_retry_delay: float = 1.0):
        """
        初始化图片优化器
        
        Args:
            max_concurrent_uploads: 最大并发上传数
            max_concurrent_api_calls: 最大并发API调用数
            max_image_size_mb: 图片最大尺寸(MB)
            compression_quality: 压缩质量(1-100)
            batch_size: 批处理大小
            upload_max_retries: 上传失败最大重试次数
            upload_retry_delay: 重试基础延迟时间(秒)
        """
        self.max_concurrent_uploads = max_concurrent_uploads
        self.max_concurrent_api_calls = max_concurrent_api_calls
        self.max_image_size_bytes = max_image_size_mb * 1024 * 1024
        self.compression_quality = compression_quality
        self.batch_size = batch_size
        self.upload_max_retries = upload_max_retries
        self.upload_retry_delay = upload_retry_delay
        
        # 并发控制信号量
        self.upload_semaphore = Semaphore(max_concurrent_uploads)
        self.api_semaphore = Semaphore(max_concurrent_api_calls)
        
        # 缓存
        self.hash_cache: Dict[str, str] = {}  # hash -> uploaded_url
        self.image_cache: Dict[str, ImageInfo] = {}  # filepath -> ImageInfo
        
    async def calculate_image_hash(self, filepath: str) -> str:
        """异步计算图片文件哈希值"""
        hash_md5 = hashlib.md5()
        async with aiofiles.open(filepath, 'rb') as f:
            while chunk := await f.read(8192):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    async def load_image_info(self, filepath: str, filename: str, xref: Optional[int] = None) -> ImageInfo:
        """延迟加载图片信息，不立即读取内容"""
        if filepath in self.image_cache:
            return self.image_cache[filepath]
            
        try:
            stat = os.stat(filepath)
            info = ImageInfo(
                filepath=filepath,
                filename=filename,
                xref=xref,
                size=stat.st_size,
                loaded=False
            )
            self.image_cache[filepath] = info
            return info
        except Exception as e:
            logger.error(f"Failed to load image info {filepath}: {e}")
            raise
    
    async def load_image_data(self, image_info: ImageInfo) -> bytes:
        """按需加载图片数据"""
        if image_info.loaded and image_info.data:
            return image_info.data
            
        async with aiofiles.open(image_info.filepath, 'rb') as f:
            image_info.data = await f.read()
            image_info.loaded = True
            
        # 计算哈希
        if not image_info.hash:
            image_info.hash = hashlib.md5(image_info.data).hexdigest()
            
        return image_info.data
    
    async def compress_image(self, image_data: bytes, max_size: Optional[int] = None) -> bytes:
        """压缩图片"""
        if max_size is None:
            max_size = self.max_image_size_bytes
            
        # 如果图片已经小于限制，直接返回
        if len(image_data) <= max_size:
            return image_data
            
        try:
            # 使用PIL压缩图片
            img = Image.open(io.BytesIO(image_data))
            
            # 转换RGBA为RGB（如果需要）
            if img.mode == 'RGBA':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img = rgb_img
            
            # 计算缩放比例
            current_size = len(image_data)
            scale_factor = (max_size / current_size) ** 0.5
            
            if scale_factor < 1:
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 压缩保存
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=self.compression_quality, optimize=True)
            compressed_data = output.getvalue()
            
            logger.info(f"Compressed image from {len(image_data)} to {len(compressed_data)} bytes")
            return compressed_data
            
        except Exception as e:
            logger.error(f"Failed to compress image: {e}")
            return image_data
    
    async def process_image_for_upload(self, image_info: ImageInfo) -> Tuple[bytes, str]:
        """处理图片准备上传，返回(图片数据, 哈希值)"""
        # 检查是否已经上传过相同内容
        if image_info.hash and image_info.hash in self.hash_cache:
            return None, image_info.hash
            
        # 加载图片数据
        image_data = await self.load_image_data(image_info)
        
        # 压缩图片
        if image_info.size > self.max_image_size_bytes:
            image_data = await self.compress_image(image_data)
            image_info.compressed = True
            image_info.data = image_data
            # 重新计算压缩后的哈希
            image_info.hash = hashlib.md5(image_data).hexdigest()
        
        return image_data, image_info.hash
    
    async def batch_upload_images(self, 
                                  images: List[ImageInfo], 
                                  upload_func,
                                  upload_options) -> Dict[str, str]:
        """批量并发上传图片"""
        results = {}
        upload_tasks = []
        
        for image_info in images:
            # 创建上传任务，使用配置的重试参数
            task = self._upload_single_image(
                image_info, 
                upload_func, 
                upload_options,
                max_retries=self.upload_max_retries,
                retry_delay=self.upload_retry_delay
            )
            upload_tasks.append(task)
        
        # 并发执行所有上传任务
        upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        
        # 处理结果
        for image_info, result in zip(images, upload_results):
            if isinstance(result, Exception):
                logger.error(f"Failed to upload {image_info.filename}: {result}")
                # 即使失败也要记录结果，使用空字符串
                if image_info.xref is not None:
                    results[image_info.xref] = ''
                else:
                    results[image_info.filename] = ''
                continue
                
            url, upload_key = result
            if url:
                # 保存到缓存
                if image_info.hash:
                    self.hash_cache[image_info.hash] = url
                    
                if image_info.xref is not None:
                    results[image_info.xref] = url
                else:
                    results[image_info.filename] = url
            else:
                # URL为空的情况
                logger.warning(f"Upload returned empty URL for {image_info.filename}")
                if image_info.xref is not None:
                    results[image_info.xref] = ''
                else:
                    results[image_info.filename] = ''
                    
        return results
    
    async def _upload_single_image(self, 
                                   image_info: ImageInfo, 
                                   upload_func,
                                   upload_options,
                                   max_retries: int = 3,
                                   retry_delay: float = 1.0) -> Tuple[Optional[str], Optional[str]]:
        if os.getenv('MINERU_TEST_FILE'):
            return image_info.filepath, None
        # return image_info.filepath, None
        """上传单个图片（带并发控制和重试机制）"""
        async with self.upload_semaphore:
            # 处理图片
            image_data, hash_value = await self.process_image_for_upload(image_info)
            
            # 如果已经上传过，直接返回URL
            if image_data is None and hash_value in self.hash_cache:
                url = self.hash_cache[hash_value]
                logger.info(f"Image {image_info.filename} already uploaded, reusing URL")
                return url, None
            
            # 重试机制
            for attempt in range(max_retries):
                try:
                    # 调用上传函数
                    logger.info(f"Uploading image {image_info.filename} (attempt {attempt + 1}/{max_retries})")
                    result = await upload_func(
                        image_info.filepath if not image_info.compressed else None,
                        image_info.filename,
                        upload_options,
                        binary_data=image_data if image_info.compressed else None
                    )
                    
                    # 检查上传结果
                    if result and result[0]:  # URL不为空
                        logger.info(f"Successfully uploaded {image_info.filename}")
                        return result
                    else:
                        logger.warning(f"Upload returned empty result for {image_info.filename}")
                        
                except Exception as e:
                    logger.error(f"Upload attempt {attempt + 1} failed for {image_info.filename}: {e}")
                    
                    # 如果不是最后一次尝试，等待后重试
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
                        continue
                    else:
                        # 最后一次尝试失败，记录详细错误
                        logger.error(f"All upload attempts failed for {image_info.filename}: {e}")
                        raise
            
            # 所有重试都失败
            return None, None
    
    async def prepare_images_for_api(self, images: List[ImageInfo]) -> List[Dict[str, Any]]:
        """准备图片数据用于API调用"""
        prepared = []
        
        for image_info in images:
            # 延迟加载图片数据
            image_data = await self.load_image_data(image_info)
            
            # 如果需要，压缩图片
            if image_info.size > self.max_image_size_bytes:
                image_data = await self.compress_image(image_data)
                
            # 转换为base64
            if not image_info.base64_data:
                image_info.base64_data = base64.b64encode(image_data).decode('utf-8')
                
            prepared.append({
                'filename': image_info.filename,
                'xref': image_info.xref,
                'base64': image_info.base64_data,
                'image_info': image_info
            })
            
        return prepared
    
    async def batch_classify_images(self, 
                                    images: List[ImageInfo],
                                    classify_func,
                                    vision_model,
                                    temp_dir: str,
                                    src_name: str) -> Dict[int, Dict]:
        """批量分类图片 - 修改为顺序执行以避免对多模态服务造成压力"""
        results = {}
        
        # 分批处理
        for i in range(0, len(images), self.batch_size):
            batch = images[i:i + self.batch_size]
            
            # 准备批量数据
            prepared_images = await self.prepare_images_for_api(batch)
            
            # 顺序执行分类，而不是并发
            for img_data in prepared_images:
                try:
                    # 顺序处理每个图片
                    result = await self._classify_single_image(
                        img_data,
                        classify_func,
                        vision_model,
                        temp_dir,
                        src_name
                    )
                    
                    if img_data['xref'] is not None:
                        results[img_data['xref']] = result
                        
                except Exception as e:
                    logger.error(f"Failed to classify image {img_data['filename']}: {e}")
                    continue
                    
        return results
    
    async def _classify_single_image(self,
                                     img_data: Dict[str, Any],
                                     classify_func,
                                     vision_model,
                                     temp_dir: str,
                                     src_name: str) -> Dict:
        """分类单个图片（带并发控制）"""
        async with self.api_semaphore:
            try:
                # 调用分类函数
                return await classify_func(
                    vision_model,
                    img_data['image_info'].filepath,
                    temp_dir,
                    src_name,
                    hint=f"xref={img_data['xref']}"
                )
            except Exception as e:
                logger.error(f"Failed to classify image: {e}")
                raise
    
    def clear_cache(self):
        """清理缓存"""
        self.image_cache.clear()
        # 不清理hash_cache，因为它可以跨文档复用
        
    async def cleanup(self):
        """清理资源"""
        # 清理内存中的图片数据
        for image_info in self.image_cache.values():
            image_info.data = None
            image_info.base64_data = None