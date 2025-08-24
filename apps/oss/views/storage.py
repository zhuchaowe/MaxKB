# coding=utf-8
"""
Storage file service for MinerU parsed images
"""
import os
import mimetypes
from pathlib import Path

from django.http import HttpResponse, Http404
from django.utils.encoding import escape_uri_path
from django.views import View


class StorageFileView(View):
    """
    静态文件服务视图，用于提供MinerU解析后的图片访问
    使用Django基础View类，完全不涉及认证系统
    """
    
    def get(self, request, file_path: str):
        """
        获取存储的文件
        
        Args:
            request: HTTP请求
            file_path: 文件相对路径（如：mineru/images/xxx.jpg）
        
        Returns:
            文件内容或404错误
        """
        # 基础存储路径（从环境变量读取，默认为/opt/maxkb/storage）
        base_path = os.getenv('MAXKB_STORAGE_PATH', '/opt/maxkb/storage')
        
        # 构建完整文件路径
        full_path = os.path.join(base_path, file_path)
        
        # 安全检查：确保请求的路径在base_path内
        try:
            # 规范化路径，解析符号链接等
            real_base = os.path.realpath(base_path)
            real_path = os.path.realpath(full_path)
            
            # 确保文件路径在基础路径内（防止路径遍历攻击）
            if not real_path.startswith(real_base):
                raise Http404("File not found")
        except (OSError, ValueError):
            raise Http404("File not found")
        
        # 检查文件是否存在
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            raise Http404("File not found")
        
        # 读取文件内容
        try:
            with open(full_path, 'rb') as f:
                file_content = f.read()
        except IOError:
            raise Http404("File not found")
        
        # 获取文件MIME类型
        content_type, _ = mimetypes.guess_type(full_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # 构建响应
        response = HttpResponse(file_content, content_type=content_type)
        
        # 设置文件名（用于下载）
        file_name = os.path.basename(full_path)
        # 对于图片类型，使用inline显示；其他类型使用attachment下载
        if content_type.startswith('image/'):
            disposition = 'inline'
        else:
            disposition = 'attachment'
        
        # 使用escape_uri_path处理文件名中的特殊字符
        response['Content-Disposition'] = f'{disposition}; filename="{escape_uri_path(file_name)}"'
        
        # 设置缓存控制（图片可以缓存较长时间）
        if content_type.startswith('image/'):
            # 图片缓存30天
            response['Cache-Control'] = 'public, max-age=2592000'
        else:
            # 其他文件缓存1天
            response['Cache-Control'] = 'public, max-age=86400'
        
        return response