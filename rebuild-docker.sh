#!/bin/bash

# Docker 镜像重新编译脚本
# 用于构建 MaxKB Docker 镜像（包含 MinerU 集成和本地 LibreOffice）

set -e

echo "=========================================="
echo "MaxKB Docker 镜像构建脚本"
echo "=========================================="

# 设置构建参数
DOCKER_IMAGE_TAG=${DOCKER_IMAGE_TAG:-"dev"}
BUILD_AT=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
GITHUB_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
IMAGE_NAME="maxkb-local"
IMAGE_TAG="latest"

echo ""
echo "构建参数："
echo "  - 镜像名称: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  - Docker标签: ${DOCKER_IMAGE_TAG}"
echo "  - 构建时间: ${BUILD_AT}"
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
echo "清理旧容器..."
if docker ps -a | grep -q maxkb-local; then
    echo "停止并删除旧的 maxkb-local 容器..."
    docker stop maxkb-local 2>/dev/null || true
    docker rm maxkb-local 2>/dev/null || true
fi

# 构建 Docker 镜像
echo ""
echo "开始构建 Docker 镜像..."
echo "这可能需要几分钟时间，请耐心等待..."
echo ""

DOCKER_BUILDKIT=1 docker build \
    --build-arg DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG}" \
    --build-arg BUILD_AT="${BUILD_AT}" \
    --build-arg GITHUB_COMMIT="${GITHUB_COMMIT}" \
    --progress=plain \
    --memory=16g \
    -t ${IMAGE_NAME}:${IMAGE_TAG} \
    -f installer/Dockerfile \
    .

# 检查构建结果
if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Docker 镜像构建成功！"
    echo "=========================================="
    echo ""
    echo "镜像信息："
    docker images | grep ${IMAGE_NAME}
    echo ""
    echo "您可以使用以下命令运行容器："
    echo ""
    echo "  docker run -d \\"
    echo "    --name maxkb-local \\"
    echo "    -p 8080:8080 \\"
    echo "    -v maxkb-data:/opt/maxkb \\"
    echo "    ${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo "或使用 docker-compose："
    echo "  cd dev && docker-compose up -d"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "✗ Docker 镜像构建失败"
    echo "=========================================="
    echo "请检查错误信息并重试"
    exit 1
fi

# 清理悬空镜像（可选）
echo "是否清理悬空镜像？(y/n)"
read -r CLEANUP
if [ "$CLEANUP" = "y" ] || [ "$CLEANUP" = "Y" ]; then
    echo "清理悬空镜像..."
    docker image prune -f
    echo "✓ 清理完成"
fi

echo ""
echo "构建脚本执行完成！"
