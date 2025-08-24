FROM node:24-alpine AS web-build

# Configure npm to use npmmirror
RUN npm config set registry https://registry.npmmirror.com

COPY ui ui
RUN cd ui && ls -la && if [ -d "dist" ]; then exit 0; fi && \
    npm install --prefer-offline --no-audit && \
    npm install -D concurrently && \
    NODE_OPTIONS="--max-old-space-size=16384" npm run build && \
    NODE_OPTIONS="--max-old-space-size=16384" npm run build-chat && \
    find . -maxdepth 1 ! -name '.' ! -name 'dist' ! -name 'public' -exec rm -rf {} +

FROM ghcr.io/1panel-dev/maxkb-base:python3.11-pg17.6 AS stage-build

# Configure apt to use Aliyun mirror (for Debian 12 bookworm)
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
        sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
        sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    fi

ARG DEPENDENCIES="                    \
        python3-pip                    \
        gettext"

RUN apt-get update && \
    apt-get install -y --no-install-recommends $DEPENDENCIES && \
    apt-get clean all  && \
    rm -rf /var/lib/apt/lists/*

COPY --chmod=700 . /opt/maxkb-app

WORKDIR /opt/maxkb-app

# Configure pip to use Aliyun mirror
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set install.trusted-host mirrors.aliyun.com

RUN rm -rf /opt/maxkb-app/ui && \
    python3 -m venv /opt/py3 && \
    pip install uv --break-system-packages && \
    . /opt/py3/bin/activate && \
    uv pip install -r pyproject.toml --index-url https://mirrors.aliyun.com/pypi/simple/ && \
    find /opt/maxkb-app  -depth \( -name ".git*" -o -name ".docker*" -o -name ".idea*" -o -name ".editorconfig*" -o -name ".prettierrc*" -o -name "README.md" -o -name "poetry.lock" -o -name "pyproject.toml"  \) -exec rm -rf {} + && \
    export MAXKB_CONFIG_TYPE=ENV && python3 /opt/maxkb-app/apps/manage.py compilemessages && \
    export PIP_TARGET=/opt/maxkb-app/sandbox/python-packages && \
    uv pip install --target=$PIP_TARGET --index-url https://mirrors.aliyun.com/pypi/simple/ requests pymysql psycopg2-binary && \
    rm -rf /opt/maxkb-app/installer
COPY --from=web-build --chmod=700 ui /opt/maxkb-app/ui

FROM ghcr.io/1panel-dev/maxkb-base:python3.11-pg17.6
ARG DOCKER_IMAGE_TAG=dev \
    BUILD_AT \
    GITHUB_COMMIT

ENV MAXKB_VERSION="${DOCKER_IMAGE_TAG} (build at ${BUILD_AT}, commit: ${GITHUB_COMMIT})" \
    MAXKB_DB_NAME=maxkb \
    MAXKB_DB_HOST=127.0.0.1 \
    MAXKB_DB_PORT=5432  \
    MAXKB_DB_USER=${POSTGRES_USER} \
    MAXKB_DB_PASSWORD=${POSTGRES_PASSWORD} \
    MAXKB_DB_MAX_OVERFLOW=80 \
    MAXKB_REDIS_HOST=127.0.0.1 \
    MAXKB_REDIS_PORT=6379 \
    MAXKB_REDIS_DB=0 \
    MAXKB_REDIS_PASSWORD=${REDIS_PASSWORD} \
    MAXKB_EMBEDDING_MODEL_PATH=/opt/maxkb-app/model/embedding \
    MAXKB_EMBEDDING_MODEL_NAME=/opt/maxkb-app/model/embedding/shibing624_text2vec-base-chinese \
    MAXKB_LOCAL_MODEL_HOST=127.0.0.1 \
    MAXKB_LOCAL_MODEL_PORT=11636 \
    MAXKB_LOCAL_MODEL_PROTOCOL=http \
    PATH=/opt/py3/bin:$PATH \
    PIP_TARGET=/opt/maxkb/python-packages

# Install poppler-utils for PDF processing (required by MinerU)
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/maxkb-app
COPY --from=stage-build /opt/maxkb-app /opt/maxkb-app
COPY --from=stage-build /opt/py3 /opt/py3

# Install LibreOffice from local tar.gz for MinerU PPT conversion
COPY resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz* /tmp/resources/
RUN cd /tmp && \
    cat resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz* > resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz && \
    tar -xzf resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz && \
    dpkg -i LibreOffice_25.2.3.2_Linux_x86-64_deb/DEBS/*.deb || apt-get update && apt-get install -f -y && \
    rm -rf LibreOffice_25.2.3.2_Linux_x86-64_deb && \
    rm resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz && \
    rm resources/LibreOffice_25.2.3_Linux_x86-64_deb.tar.gz* && \
    rm -f /usr/bin/soffice && \
    ln -s /opt/libreoffice25.2/program/soffice /usr/bin/soffice && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/* && \
    chmod 755 /tmp

EXPOSE 8080
VOLUME /opt/maxkb
ENTRYPOINT ["bash", "-c"]
CMD [ "/usr/bin/start-all.sh" ]
