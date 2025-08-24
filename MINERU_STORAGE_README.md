# MinerU 图片存储配置说明

## 访问URL格式

MinerU解析后的图片访问URL格式为：
```
http://localhost:8080/storage/mineru/images/xxx.jpg
```

简洁直接，直接使用 `/storage/` 路径访问

## 存储路径配置

### 本地开发环境
- 存储路径：`./tmp/maxkb/storage/`
- 图片位置：`./tmp/maxkb/storage/mineru/images/`

### Docker环境
- 容器内路径：`/opt/maxkb/storage/`
- 本地映射路径：`~/.maxkb/storage/`
- 图片位置：`~/.maxkb/storage/mineru/images/`

## 环境变量配置

在 `.env` 文件或 docker-compose.yml 中添加：
```bash
MAXKB_STORAGE_PATH=/opt/maxkb/storage
```

## Docker Volume配置

在 `docker-compose.yml` 中已配置：
```yaml
volumes:
  - ~/.maxkb/storage:/opt/maxkb/storage:rw
```

## 测试访问

1. 运行测试脚本创建测试图片：
```bash
python test_image_access.py
```

2. 访问测试URL：
```
http://localhost:8080/storage/mineru/images/ac3681aaa7a346b49ef9c7ceb7b94058.jpg
```

## 故障排查

1. **404错误**：检查文件是否存在于存储目录
2. **权限错误**：确保存储目录有写入权限
3. **路径错误**：确认URL路径以 `/storage/` 开头

## 相关文件

- 存储视图：`apps/oss/views/storage.py`
- URL配置：`apps/oss/urls.py`
- MinerU适配器：`apps/common/handle/impl/mineru/maxkb_adapter/adapter.py`
- 配置文件：`apps/common/handle/impl/mineru/maxkb_adapter/config_maxkb.py`