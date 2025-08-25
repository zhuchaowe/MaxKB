#!/bin/bash

# Docker 容器启动脚本
# 使用 installer/docker-compose.yml 启动 MaxKB 容器

set -e

echo "=========================================="
echo "MaxKB Docker 容器启动脚本"
echo "=========================================="

# 设置构建参数
BUILD_AT=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
GITHUB_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo ""
echo "启动参数："
echo "  - 配置文件: installer/docker-compose.yml"
echo "  - 启动时间: ${BUILD_AT}"
echo "  - Git提交: ${GITHUB_COMMIT}"
echo ""

# 创建 resources 目录（如果不存在）
if [ ! -d "resources" ]; then
    echo "创建 resources 目录..."
    mkdir -p resources
fi

# 下载 LibreOffice 资源文件
echo "检查并下载 LibreOffice 资源文件..."
DOWNLOAD_BASE_URL="http://192.168.101.129:5244/d/nas"
FILES=(
    "LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_00?sign=aNvKFaEE9QRwTBLP53KgM8Y-22AlXBkb9WsE3CW42-M=:0"
    "LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_01?sign=20ZZkcY70olgh18Qdh5VVPWI2xQpzRdBTIkA1DsRw50=:0"
    "LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_02?sign=sbEuEP_xKcZS1YnmHkTtuvi-o5KQweWCVmHM3FwHRII=:0"
)

for i in "${!FILES[@]}"; do
    FILE_URL="${DOWNLOAD_BASE_URL}/${FILES[$i]}"
    FILE_NAME="LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_0${i}"
    FILE_PATH="resources/${FILE_NAME}"
    
    if [ ! -f "${FILE_PATH}" ]; then
        echo "下载 ${FILE_NAME}..."
        curl -L -o "${FILE_PATH}" "${FILE_URL}"
        if [ $? -ne 0 ]; then
            echo "错误: 下载 ${FILE_NAME} 失败"
            exit 1
        fi
        echo "✓ ${FILE_NAME} 下载完成"
    else
        echo "✓ ${FILE_NAME} 已存在，跳过下载"
    fi
done

# 验证所有文件是否存在
echo "验证 LibreOffice 资源文件..."
if [ ! -f "resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_00" ] || \
   [ ! -f "resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_01" ] || \
   [ ! -f "resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_02" ]; then
    echo "错误: LibreOffice 资源文件不完整"
    echo "请检查 resources/ 目录下是否有以下文件:"
    echo "  - LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_00"
    echo "  - LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_01"
    echo "  - LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz_02"
    exit 1
fi
echo "✓ 所有 LibreOffice 资源文件就绪"

# 停止并删除旧容器（如果存在）
echo ""
echo "检查现有容器..."
if docker ps -a | grep -q maxkb-dev; then
    echo "发现旧容器，正在停止..."
    cd installer
    docker-compose down
    cd ..
    echo "✓ 旧容器已停止并删除"
fi

# 启动容器（docker-compose 会自动构建镜像如果不存在）
echo ""
echo "启动 MaxKB 容器..."
echo "如果镜像不存在，将自动构建（首次运行可能需要几分钟）..."
cd installer
docker-compose up -d --build

# 检查启动结果
if [ $? -eq 0 ]; then
    cd ..
    echo ""
    echo "=========================================="
    echo "✓ MaxKB 容器启动成功！"
    echo "=========================================="
    echo ""
    echo "容器信息："
    docker ps | grep maxkb-dev
    echo ""
    echo "服务访问地址："
    echo "  http://localhost:2008"
    echo ""
    echo "查看日志："
    echo "  cd installer && docker-compose logs -f"
    echo ""
    echo "停止容器："
    echo "  cd installer && docker-compose down"
    echo ""
    echo "重启容器："
    echo "  cd installer && docker-compose restart"
    echo ""
else
    cd ..
    echo ""
    echo "=========================================="
    echo "✗ 容器启动失败"
    echo "=========================================="
    echo "请检查错误信息并重试"
    exit 1
fi

echo "启动脚本执行完成！"