#!/bin/bash
# WorkPilot v2 Backend 启动脚本
# 执行顺序：迁移 → 初始化数据 → 启动服务器
set -e

echo "=================================================="
echo " WorkPilot v2 Backend Starting..."
echo "=================================================="

# ── 1. 执行数据库迁移 ──────────────────────────────────
echo "[1/3] Running Alembic migrations..."
uv run alembic upgrade head
echo "      Migrations complete."

# ── 2. 初始化超级管理员（幂等：占位符密码时才执行）────
echo "[2/3] Seeding initial admin..."
uv run python scripts/seed_admin.py
echo "      Seed complete."

# ── 3. 启动 Gunicorn + Uvicorn workers ────────────────
# Workers 数量说明：
#   - 当前设为 2，适合单机部署
#   - APScheduler 使用 PostgreSQLJobStore，多 Worker 下不会重复执行定时任务
#   - 可通过环境变量 GUNICORN_WORKERS 覆盖
WORKERS=${GUNICORN_WORKERS:-2}

echo "[3/3] Starting Gunicorn (workers=${WORKERS})..."
# 注意：gunicorn 依赖 Unix fcntl，仅 Linux/Docker 使用；Windows 请用 uvicorn
exec uv run gunicorn main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS}" \
    --bind 0.0.0.0:8000 \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
