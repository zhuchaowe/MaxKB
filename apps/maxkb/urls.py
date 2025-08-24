"""
URL configuration for maxkb project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os
from pathlib import Path

from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, re_path, include
from django.views import static
from rest_framework import status

from chat.urls import urlpatterns as chat_urlpatterns
from common.init.init_doc import init_doc
from common.result import Result
from maxkb import settings
from maxkb.conf import PROJECT_DIR
from maxkb.const import CONFIG

admin_api_prefix = CONFIG.get_admin_path()[1:] + '/api/'
admin_ui_prefix = CONFIG.get_admin_path()
chat_api_prefix = CONFIG.get_chat_path()[1:] + '/api/'
chat_ui_prefix = CONFIG.get_chat_path()
urlpatterns = [
    path(admin_api_prefix, include("users.urls")),
    path(admin_api_prefix, include("tools.urls")),
    path(admin_api_prefix, include("models_provider.urls")),
    path(admin_api_prefix, include("folders.urls")),
    path(admin_api_prefix, include("knowledge.urls")),
    path(admin_api_prefix, include("system_manage.urls")),
    path(admin_api_prefix, include("application.urls")),
    path(admin_api_prefix, include("oss.urls")),
    path(chat_api_prefix, include("oss.urls")),
    path(chat_api_prefix, include("chat.urls")),
    path(f'{admin_ui_prefix[1:]}/', include('oss.retrieval_urls')),
    path(f'{chat_ui_prefix[1:]}/', include('oss.retrieval_urls')),
]
init_doc(urlpatterns, chat_urlpatterns)


def pro():
    urlpatterns.append(
        re_path(r'^doc/(?P<path>.*)$', static.serve,
                {'document_root': os.path.join(settings.STATIC_ROOT, "drf_spectacular_sidecar")}, name='doc'),
    )
    # 暴露ui静态资源
    urlpatterns.append(
        re_path(rf"^{CONFIG.get_admin_path()[1:]}/(?P<path>.*)$", static.serve,
                {'document_root': os.path.join(settings.STATIC_ROOT, "admin")},
                name='admin'),
    )
    # 暴露ui静态资源
    urlpatterns.append(
        re_path(rf'^{CONFIG.get_chat_path()[1:]}/(?P<path>.*)$', static.serve,
                {'document_root': os.path.join(settings.STATIC_ROOT, "chat")},
                name='chat'),
    )


if not settings.DEBUG:
    pro()

# 添加storage路由 - 使用函数视图避免类导入问题
def serve_storage_file(request, file_path):
    """
    直接提供storage目录下的文件访问
    """
    import os
    import mimetypes
    from django.http import HttpResponse, Http404
    from django.utils.encoding import escape_uri_path
    
    # 基础存储路径 - 支持本地开发和Docker环境
    base_path = os.getenv('MAXKB_STORAGE_PATH', '/opt/maxkb/storage')
    # 如果是本地开发环境，使用相对路径
    if not os.path.exists(base_path):
        base_path = './tmp/maxkb/storage'
    full_path = os.path.join(base_path, file_path)
    
    # 安全检查
    try:
        real_base = os.path.realpath(base_path)
        real_path = os.path.realpath(full_path)
        if not real_path.startswith(real_base):
            raise Http404("File not found")
    except (OSError, ValueError):
        raise Http404("File not found")
    
    # 检查文件是否存在
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("File not found")
    
    # 读取文件
    try:
        with open(full_path, 'rb') as f:
            file_content = f.read()
    except IOError:
        raise Http404("File not found")
    
    # 获取MIME类型
    content_type, _ = mimetypes.guess_type(full_path)
    if not content_type:
        content_type = 'application/octet-stream'
    
    # 构建响应
    response = HttpResponse(file_content, content_type=content_type)
    
    # 设置响应头
    file_name = os.path.basename(full_path)
    if content_type.startswith('image/'):
        response['Content-Disposition'] = f'inline; filename="{escape_uri_path(file_name)}"'
        response['Cache-Control'] = 'public, max-age=2592000'  # 30天缓存
    else:
        response['Content-Disposition'] = f'attachment; filename="{escape_uri_path(file_name)}"'
        response['Cache-Control'] = 'public, max-age=86400'  # 1天缓存
    
    return response

# 添加storage路由
urlpatterns.insert(0, re_path(r'^storage/(?P<file_path>.*)$', serve_storage_file, name='storage_file'))


def get_index_html(index_path):
    file = open(index_path, "r", encoding='utf-8')
    content = file.read()
    file.close()
    return content


def get_all_files(directory):
    base_path = Path(directory)
    file_paths = [
        '/' + str(file.relative_to(base_path)).replace('\\', '/')
        for file in base_path.rglob('*')
        if file.is_file()
    ]
    return sorted(file_paths, key=len, reverse=True)


static_dict = {
    chat_ui_prefix: get_all_files(os.path.join(PROJECT_DIR, 'apps', "static", 'chat')),
    admin_ui_prefix: get_all_files(os.path.join(PROJECT_DIR, 'apps', "static", 'admin'))
}


def page_not_found(request, exception):
    """
    页面不存在处理
    """
    if request.path.startswith(admin_ui_prefix + '/api/'):
        return Result(response_status=status.HTTP_404_NOT_FOUND, code=404, message="HTTP_404_NOT_FOUND")
    if request.path.startswith(chat_ui_prefix + '/api/'):
        return Result(response_status=status.HTTP_404_NOT_FOUND, code=404, message="HTTP_404_NOT_FOUND")
    if request.path.startswith(chat_ui_prefix):
        in_ = [url for url in static_dict.get(chat_ui_prefix) if request.path.endswith(url)]
        if len(in_) > 0:
            a = chat_ui_prefix + in_[0]
            return HttpResponseRedirect(a)
        index_path = os.path.join(PROJECT_DIR, 'apps', "static", 'chat', 'index.html')
        content = get_index_html(index_path)
        content = content.replace("prefix: '/chat'", f"prefix: '{CONFIG.get_chat_path()}'")
        if not os.path.exists(index_path):
            return HttpResponse("页面不存在", status=404)
        return HttpResponse(content, status=200)
    elif request.path.startswith(admin_ui_prefix):
        in_ = [url for url in static_dict.get(admin_ui_prefix) if request.path.endswith(url)]
        if len(in_) > 0:
            a = admin_ui_prefix + in_[0]
            return HttpResponseRedirect(a)
        index_path = os.path.join(PROJECT_DIR, 'apps', "static", 'admin', 'index.html')
        if not os.path.exists(index_path):
            return HttpResponse("页面不存在", status=404)
        content = get_index_html(index_path)
        content = content.replace("prefix: '/admin'", f"prefix: '{CONFIG.get_admin_path()}'").replace(
            "chatPrefix: '/chat'", f"chatPrefix: '{CONFIG.get_chat_path()}'")
        return HttpResponse(content, status=200)
    else:
        return HttpResponseRedirect(admin_ui_prefix + '/')


handler404 = page_not_found
