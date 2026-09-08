#!/usr/bin/env bash
# WorkPilot v2 — 开发环境管理脚本（Linux / macOS）
#
# 用法：
#   ./dev.sh start          启动全部开发服务
#   ./dev.sh stop           停止全部开发服务
#   ./dev.sh restart        重启后端容器（改依赖/配置后用）
#   ./dev.sh status         查看各服务状态
#   ./dev.sh logs [service] 查看日志（默认 backend，可传 postgres/ollama）
#   ./dev.sh pull-models    拉取 Ollama 模型（首次部署执行一次）
#   ./dev.sh psql           进入 PostgreSQL 交互终端
#
# 开发架构：
#   postgres  :5432   ─┐
#   ollama   :11434   ─┤  Docker (docker-compose.override.yml)
#   backend  :8000    ─┘  FastAPI 热重载
#   frontend :5173        Vite dev server（宿主机后台运行）
#
#   浏览器访问 → http://localhost:5173
#   Swagger UI → http://localhost:8000/docs

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────────────

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; WHITE='\033[1;37m'; GRAY='\033[0;90m'; NC='\033[0m'

step()  { echo -e "  ${CYAN}»${NC} $1"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }
err()   { echo -e "  ${RED}✗${NC} $1"; }
title() { echo -e "\n${WHITE}$1${NC}"; }

# ── 路径 ─────────────────────────────────────────────────────────

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
PID_FILE="$ROOT/.frontend.pid"
LOG_FILE="$ROOT/.frontend.log"
ENV_FILE="$ROOT/backend/.env"

ACTION="${1:-start}"
SERVICE="${2:-backend}"

# ── 前置检查 ─────────────────────────────────────────────────────

assert_docker() {
    if ! command -v docker &>/dev/null; then
        err "未找到 docker 命令，请先安装 Docker"
        exit 1
    fi
    if ! docker info &>/dev/null; then
        err "Docker 未运行，请先启动 Docker"
        exit 1
    fi
}

assert_node() {
    if ! command -v node &>/dev/null; then
        err "未找到 node 命令，请先安装 Node.js 18+"
        exit 1
    fi
}

assert_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        warn "backend/.env 不存在，从 .env.example 复制..."
        cp "$ROOT/backend/.env.example" "$ENV_FILE"
        warn "请编辑 backend/.env，修改 JWT_SECRET_KEY 和 POSTGRES_PASSWORD 后重新运行"
        exit 1
    fi
}

# ── 前端进程管理 ──────────────────────────────────────────────────

start_frontend() {
    # 检查是否已在运行
    if [[ -f "$PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$PID_FILE")
        if kill -0 "$old_pid" 2>/dev/null; then
            warn "前端已在运行（PID $old_pid）"
            return
        fi
        rm -f "$PID_FILE"
    fi

    # 检查 node_modules
    if [[ ! -d "$FRONTEND/node_modules" ]]; then
        step "安装前端依赖（npm install）..."
        (cd "$FRONTEND" && npm install --silent)
    fi

    step "启动 Vite dev server（后台）→ 日志：$LOG_FILE"
    (cd "$FRONTEND" && npm run dev > "$LOG_FILE" 2>&1) &
    echo $! > "$PID_FILE"
    ok "前端已启动（PID $(cat "$PID_FILE")）→ http://localhost:5173"
    echo -e "  ${GRAY}前端日志：tail -f $LOG_FILE${NC}"
}

stop_frontend() {
    if [[ ! -f "$PID_FILE" ]]; then
        warn "未找到前端 PID 文件，跳过"
        return
    fi
    local saved_pid
    saved_pid=$(cat "$PID_FILE")
    if kill -0 "$saved_pid" 2>/dev/null; then
        # 停止整个进程组（包括 node 子进程）
        kill -- -"$(ps -o pgid= -p "$saved_pid" | tr -d ' ')" 2>/dev/null \
            || kill "$saved_pid" 2>/dev/null
        ok "前端已停止（PID $saved_pid）"
    else
        warn "前端进程（PID $saved_pid）已不存在"
    fi
    rm -f "$PID_FILE"
}

frontend_status() {
    if [[ ! -f "$PID_FILE" ]]; then echo "未运行"; return; fi
    local saved_pid
    saved_pid=$(cat "$PID_FILE")
    if kill -0 "$saved_pid" 2>/dev/null; then
        echo "运行中 (PID $saved_pid)"
    else
        echo "进程已退出（PID 文件残留）"
    fi
}

# ── Docker Compose 辅助 ───────────────────────────────────────────

dc() {
    # 在项目根目录执行 docker compose（自动加载 override.yml）
    (cd "$ROOT" && docker compose "$@")
}

# ════════════════════════════════════════════════════════════════
# 动作
# ════════════════════════════════════════════════════════════════

case "$ACTION" in

    # ── start ────────────────────────────────────────────────

    start)
        title "▶  WorkPilot 开发环境启动"
        assert_docker
        assert_node
        assert_env

        step "启动后端服务（postgres / ollama / backend）..."
        dc up -d postgres ollama backend

        step "等待 backend 健康检查..."
        waited=0
        while [[ $waited -lt 60 ]]; do
            health=$(docker inspect \
                --format "{{.State.Health.Status}}" \
                "$(dc ps -q backend 2>/dev/null)" 2>/dev/null || echo "unknown")
            [[ "$health" == "healthy" ]] && break
            sleep 3; waited=$((waited+3))
            printf "    (%ds)\r" "$waited"
        done
        echo ""

        if [[ $waited -ge 60 ]]; then
            warn "backend 健康检查超时，请运行 ./dev.sh logs 查看详情"
        else
            ok "后端就绪 → http://localhost:8000/docs"
        fi

        start_frontend

        title "═══════════════════════════════════════"
        ok "开发环境已启动！"
        echo -e "  前端  → ${WHITE}http://localhost:5173${NC}"
        echo -e "  API   → ${WHITE}http://localhost:8000/docs${NC}"
        echo -e "  停止  → ${GRAY}./dev.sh stop${NC}"
        title "═══════════════════════════════════════"
        ;;

    # ── stop ─────────────────────────────────────────────────

    stop)
        title "■  WorkPilot 开发环境停止"
        stop_frontend
        step "停止后端 Docker 服务..."
        dc stop backend postgres ollama
        ok "后端服务已停止（数据卷保留）"
        echo -e "  ${GRAY}如需彻底清除数据，运行：docker compose down -v${NC}"
        ;;

    # ── restart ──────────────────────────────────────────────

    restart)
        title "↺  重启后端容器"
        assert_docker
        step "重启 backend..."
        dc restart backend
        ok "backend 已重启"
        echo -e "  ${GRAY}日志：./dev.sh logs${NC}"
        ;;

    # ── status ───────────────────────────────────────────────

    status)
        title "○  服务状态"
        assert_docker
        echo -e "\nDocker 服务："
        dc ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
        echo -e "\n前端进程："
        echo -e "  Vite dev server — $(frontend_status)"
        ;;

    # ── logs ─────────────────────────────────────────────────

    logs)
        assert_docker
        if [[ "$SERVICE" == "frontend" ]]; then
            if [[ -f "$LOG_FILE" ]]; then
                tail -f "$LOG_FILE"
            else
                err "前端日志文件不存在（$LOG_FILE）"
                exit 1
            fi
        else
            title "📋  日志 — $SERVICE"
            echo -e "  ${GRAY}(Ctrl+C 退出)${NC}"
            dc logs -f --tail=100 "$SERVICE"
        fi
        ;;

    # ── pull-models ──────────────────────────────────────────

    pull-models)
        title "⬇  拉取 Ollama 模型（首次部署）"
        assert_docker

        dc up -d ollama
        sleep 3

        step "拉取 nomic-embed-text（Embedding 模型）..."
        dc exec ollama ollama pull nomic-embed-text

        step "拉取 qwen2.5:7b（对话模型）..."
        dc exec ollama ollama pull qwen2.5:7b

        ok "模型拉取完成"
        ;;

    # ── psql ─────────────────────────────────────────────────

    psql)
        assert_docker
        step "进入 PostgreSQL 交互终端（\q 退出）..."
        dc exec postgres psql -U workpilot -d workpilot
        ;;

    # ── 未知 ─────────────────────────────────────────────────

    *)
        echo "用法：./dev.sh [start|stop|restart|status|logs|pull-models|psql]"
        exit 1
        ;;
esac
