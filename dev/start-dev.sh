#!/bin/bash
# MaxKB 开发环境启动脚本

echo "启动 MaxKB 开发环境..."

# 停止并删除旧容器
docker-compose -f docker-compose-simple.yml down 2>/dev/null

# 启动容器
docker-compose -f docker-compose-simple.yml up -d

echo "等待服务启动..."
echo "这可能需要几分钟时间，因为应用需要初始化..."

# 等待服务启动
max_attempts=60
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker exec maxkb-dev curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/admin/ | grep -q "200\|302"; then
        echo ""
        echo "✅ MaxKB 开发环境启动成功！"
        echo ""
        echo "访问地址："
        echo "  - 应用地址: http://localhost:8081"
        echo "  - 默认账号: admin / Admin@1234"
        echo ""
        echo "查看日志："
        echo "  docker logs -f maxkb-dev"
        echo ""
        exit 0
    fi
    
    printf "."
    sleep 5
    attempt=$((attempt + 1))
done

echo ""
echo "❌ 服务启动超时，请检查日志："
echo "docker logs maxkb-dev"
exit 1