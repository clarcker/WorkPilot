# ── WorkPilot v2 Backend ──────────────────────────────────────────
# 构建：docker build -t workpilot-backend ./backend
# 运行：由 docker-compose.yml 管理
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# 系统依赖（curl 用于健康检查；build-essential 用于部分 C 扩展编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 包管理器）
RUN pip install --no-cache-dir uv

# 先拷贝依赖声明，利用 Docker layer 缓存
# uv.lock 用 * 通配（存在就拷贝，不存在也不报错）
COPY pyproject.toml uv.lock* ./

# 安装生产依赖（不含 dev extras）
# --no-dev：跳过 dev 依赖
# 若 uv.lock 存在则使用锁文件（--frozen），否则重新解析
RUN uv sync --no-dev 2>/dev/null || true && uv sync --no-dev

# 拷贝全部源码
COPY . .

# 赋予启动脚本执行权限
RUN chmod +x entrypoint.sh

# 仅在容器内部暴露端口（不对宿主机暴露，由 nginx 代理）
EXPOSE 8000

# 健康检查（供 docker-compose depends_on 使用）
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=60s \
    --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
