from django.urls import path

from . import views

app_name = 'oss'

urlpatterns = [
    path('oss/file', views.FileView.as_view()),
    # storage路由已移至主URL配置中
]
