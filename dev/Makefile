# MaxKB 开发环境快捷命令

# 快速重启Python进程（最常用）
restart:
	@echo "🔄 重启MaxKB Python进程..."
	@docker exec maxkb-dev pkill -f "python.*main.py" 2>/dev/null || true
	@sleep 2
	@echo "✅ 重启完成"

# 查看实时日志
logs:
	docker logs -f maxkb-dev

# 查看最新20行日志
log:
	docker logs maxkb-dev --tail 20

# 进入容器shell
shell:
	docker exec -it maxkb-dev bash

# 查看Python进程
ps:
	@docker exec maxkb-dev ps aux | grep python | grep -v grep || echo "没有找到Python进程"

# 完全重启容器
full-restart:
	docker compose -f docker-compose-simple.yml restart

# 停止容器
stop:
	docker compose -f docker-compose-simple.yml stop

# 启动容器
start:
	docker compose -f docker-compose-simple.yml start

# 重新构建并启动
rebuild:
	docker compose -f docker-compose-simple.yml down
	docker compose -f docker-compose-simple.yml up -d --build

# 查看容器状态
status:
	@docker ps --filter name=maxkb-dev --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 清理日志
clean-logs:
	@docker exec maxkb-dev bash -c "find /opt/maxkb-app -name '*.log' -type f -exec truncate -s 0 {} \;" 2>/dev/null || true
	@echo "日志已清理"

# 帮助信息
help:
	@echo "MaxKB 开发环境快捷命令："
	@echo "  make restart      - 快速重启Python进程（最快）"
	@echo "  make logs        - 查看实时日志"
	@echo "  make log         - 查看最新20行日志"
	@echo "  make shell       - 进入容器Shell"
	@echo "  make ps          - 查看Python进程"
	@echo "  make full-restart - 完全重启容器"
	@echo "  make stop        - 停止容器"
	@echo "  make start       - 启动容器"
	@echo "  make rebuild     - 重新构建并启动"
	@echo "  make status      - 查看容器状态"
	@echo "  make clean-logs  - 清理日志文件"

.DEFAULT_GOAL := help