# MaxKB 开发环境

提供两种开发环境配置方案，根据需求选择使用。

## ⚠️ 重要说明

1. **首次启动较慢**：MaxKB 启动时需要初始化数据库、加载模型等，可能需要 3-5 分钟
2. **镜像要求**：需要先构建本地镜像 `maxkb-local:latest`
   ```bash
   # 在项目根目录构建镜像
   docker build -f installer/Dockerfile -t maxkb-local:latest .
   ```

## 方案一：最简单模式（推荐）

使用官方镜像，通过挂载源码实现开发调试。

### 快速启动

```bash
cd dev

# 方式一：使用启动脚本（推荐，会等待服务完全启动）
./start-dev.sh

# 方式二：手动启动
docker-compose -f docker-compose-simple.yml up -d
# 查看日志
docker-compose -f docker-compose-simple.yml logs -f
```

访问：
- 应用地址：http://localhost:8081
- 默认账号：admin / Admin@1234

### 特点
- ✅ 一个容器包含所有服务（PostgreSQL、Redis、Django、Celery）
- ✅ Python代码修改自动重载
- ✅ 最简单的配置
- ❌ 前端需要手动构建才能看到效果

## 方案二：完整开发模式

分离前后端开发环境，支持前端热重载。

### 启动方式

```bash
cd dev

# 启动所有服务
docker-compose up -d

# 仅启动后端
docker-compose up -d maxkb-dev

# 仅启动前端开发服务器
docker-compose up -d frontend-dev
```

访问：
- Django后端：http://localhost:8080
- 前端开发服务器（管理界面）：http://localhost:5173
- 前端开发服务器（聊天界面）：http://localhost:5174

### 特点
- ✅ 前后端都支持热重载
- ✅ 前端使用Vite开发服务器，体验更好
- ✅ 可以独立开发前端或后端
- ❌ 配置相对复杂

## 开发流程

### 后端开发

1. 修改 `apps/` 目录下的Python代码
2. Django开发服务器会自动检测变化并重载
3. 查看容器日志观察变化：
   ```bash
   docker logs -f maxkb-dev
   ```

### 前端开发

#### 方案一（简单模式）
1. 修改 `ui/` 目录下的代码
2. 在容器内手动构建：
   ```bash
   docker exec -it maxkb-dev bash
   cd /opt/maxkb-app
   python main.py collect_static
   ```

#### 方案二（完整模式）
1. 修改 `ui/` 目录下的代码
2. Vite开发服务器自动热重载
3. 访问 http://localhost:5173 查看效果

### 数据库操作

```bash
# 执行数据库迁移
docker exec -it maxkb-dev python /opt/maxkb-app/main.py upgrade_db

# 进入Django Shell
docker exec -it maxkb-dev python /opt/maxkb-app/apps/manage.py shell

# 创建超级用户
docker exec -it maxkb-dev python /opt/maxkb-app/apps/manage.py createsuperuser
```

## 常见问题

### 1. 端口冲突
修改 docker-compose.yml 中的端口映射，例如：
```yaml
ports:
  - "8081:8080"  # 改为8081
```

### 2. 权限问题
如果遇到文件权限问题：
```bash
sudo chown -R $USER:$USER ../apps ../ui
```

### 3. 前端连接后端失败
确保环境变量 `VITE_APP_BASE_URL` 设置正确：
```bash
VITE_APP_BASE_URL=http://localhost:8080
```

### 4. 查看所有环境变量
```bash
docker exec maxkb-dev env | grep MAXKB
```

## 生产镜像构建

如果需要构建自己的镜像：

```bash
# 在项目根目录
docker build -f installer/Dockerfile -t my-maxkb:dev .

# 修改 docker-compose.yml 使用自定义镜像
# image: my-maxkb:dev
```

## 清理环境

```bash
# 停止并删除容器
docker-compose down

# 清理所有数据（慎用）
docker-compose down -v
rm -rf ~/.maxkb-dev
```