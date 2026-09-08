# WorkPilot v2 - 开发模式脚本（Windows PowerShell）
#
# 基础设施（postgres / ollama）跑在 Docker，
# 后端和前端在本机直接运行，代码改动即时生效，无需重新构建。
#
# 用法：
#   .\dev.ps1 start          启动所有开发服务
#   .\dev.ps1 stop           停止所有开发服务
#   .\dev.ps1 restart        重启后端
#   .\dev.ps1 restart be     重启后端
#   .\dev.ps1 restart fe     重启前端
#   .\dev.ps1 restart all    重启后端和前端
#   .\dev.ps1 status         查看服务状态
#   .\dev.ps1 logs [svc]     查看 Docker 容器日志（postgres / ollama）
#   .\dev.ps1 pull-models    首次使用时拉取 Ollama 模型
#   .\dev.ps1 psql           进入 PostgreSQL 交互终端
#
# 端口：
#   postgres  :5432   (Docker，暴露到本机)
#   ollama    :11434  (Docker，暴露到本机)
#   backend   :8000   (本机直接运行，FastAPI 热重载)
#   frontend  :5173   (本机直接运行，Vite dev server)

$Action  = if ($args.Count -ge 1) { $args[0] } else { "start" }
$Service = if ($args.Count -ge 2) { $args[1] } else { "postgres" }

$ErrorActionPreference = "Stop"

# ---------- 路径 ------------------------------------------------------

$Root        = $PSScriptRoot
$Backend     = Join-Path $Root "backend"
$Frontend    = Join-Path $Root "frontend"
$EnvFile     = Join-Path $Backend ".env"
$BackendPid  = Join-Path $Root ".backend.pid"
$FrontendPid = Join-Path $Root ".frontend.pid"

# Docker Compose 命令（使用 dev 覆盖文件暴露端口）
$DC = "docker compose -f docker-compose.yml -f docker-compose.dev.yml"

# ---------- 工具函数 --------------------------------------------------

function Write-Step  { param($m) Write-Host "  >> $m" -ForegroundColor Cyan   }
function Write-OK    { param($m) Write-Host "  OK $m" -ForegroundColor Green  }
function Write-Warn  { param($m) Write-Host "  !! $m" -ForegroundColor Yellow }
function Write-Err   { param($m) Write-Host "  XX $m" -ForegroundColor Red    }
function Write-Title { param($m) Write-Host "`n$m"    -ForegroundColor White  }
function Write-Rule  {           Write-Host "  $('-' * 50)" -ForegroundColor DarkGray }

# ---------- 前置检查 --------------------------------------------------

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Err "找不到 docker 命令，请先安装 Docker Desktop"; exit 1
    }
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Docker 未运行，请先启动 Docker Desktop"; exit 1
    }
}

function Assert-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Err "找不到 node，请先安装 Node.js 18+"; exit 1
    }
}

function Assert-Uv {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Err "找不到 uv，请先安装：https://docs.astral.sh/uv/"; exit 1
    }
}

function Assert-Env {
    if (-not (Test-Path $EnvFile)) {
        $example = Join-Path $Backend ".env.example"
        if (Test-Path $example) {
            Copy-Item $example $EnvFile
            Write-Warn "已创建 backend/.env，请修改 JWT_SECRET_KEY 和 POSTGRES_PASSWORD 后重试"
        } else {
            Write-Err "找不到 backend/.env，请先创建并配置"
        }
        exit 1
    }
}

# ---------- 读取 .env，把 Docker 内部地址替换为 localhost ─────────

function Get-DevEnv {
    $env_vars = @{}
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $env_vars[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }

    # 把 Docker 服务名替换为 127.0.0.1，禁用 SSL
    if ($env_vars['DATABASE_URL']) {
        $url = $env_vars['DATABASE_URL'] -replace '@postgres:', '@127.0.0.1:'
        if ($url -notmatch '\?') { $url += '?ssl=disable' }
        $env_vars['DATABASE_URL'] = $url
    }
    $env_vars['OLLAMA_BASE_URL'] = 'http://127.0.0.1:11434'

    # 开发时上传目录用本机路径
    $uploadsDir = Join-Path $Backend "uploads"
    if (-not (Test-Path $uploadsDir)) { New-Item -ItemType Directory -Path $uploadsDir | Out-Null }
    $env_vars['UPLOAD_DIR'] = $uploadsDir

    return $env_vars
}

# ---------- 进程管理（通用） -----------------------------------------

function Start-NativeProcess {
    param($PidFilePath, $WorkDir, $Command, $WindowTitle)
    if (Test-Path $PidFilePath) {
        $old = (Get-Content $PidFilePath -Raw).Trim()
        if (Get-Process -Id $old -ErrorAction SilentlyContinue) {
            Write-Warn "$WindowTitle 已在运行中（PID $old），跳过"
            return
        }
        Remove-Item -Path $PidFilePath -Force
    }
    $proc = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", "Set-Location '$WorkDir'; $Command" `
        -PassThru
    "$($proc.Id)" | Out-File $PidFilePath -Encoding ascii -NoNewline
    Write-OK "$WindowTitle 已启动（PID $($proc.Id)）"
}

function Stop-NativeProcess {
    param($PidFilePath, $Label)
    if (-not (Test-Path $PidFilePath)) {
        Write-Warn "$Label 没有 PID 文件，跳过"
        return
    }
    $pid_ = (Get-Content $PidFilePath -Raw).Trim()
    $proc = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
    if ($proc) {
        Get-CimInstance Win32_Process |
            Where-Object { $_.ParentProcessId -eq [int]$pid_ } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        Write-OK "$Label 已停止（PID $pid_）"
    } else {
        Write-Warn "$Label 进程（PID $pid_）已不存在"
    }
    Remove-Item -Path $PidFilePath -Force
}

function Get-ProcessStatus {
    param($PidFilePath, $Label)
    if (-not (Test-Path $PidFilePath)) { return "$Label：未运行" }
    $pid_ = (Get-Content $PidFilePath -Raw).Trim()
    if (Get-Process -Id $pid_ -ErrorAction SilentlyContinue) { return "$Label：运行中（PID $pid_）" }
    return "$Label：已退出（PID 文件残留）"
}

# ---------- Docker Compose 封装 ---------------------------------------

function Invoke-DC {
    Push-Location $Root
    Invoke-Expression "docker compose -f docker-compose.yml -f docker-compose.dev.yml $args"
    $exit = $LASTEXITCODE
    Pop-Location
    return $exit
}

# ---------- 主逻辑 ----------------------------------------------------

switch ($Action.ToLower()) {

    "start" {
        Write-Title "WorkPilot - 启动开发环境"
        Write-Rule
        Assert-Docker
        Assert-Node
        Assert-Uv
        Assert-Env

        # 1. 启动基础设施（postgres + ollama），暴露端口到本机
        Write-Step "启动 postgres / ollama（端口暴露到本机）..."
        Invoke-DC up -d postgres ollama | Out-Null

        # 2. 等待 postgres 健康
        Write-Step "等待 postgres 就绪..."
        $waited = 0
        while ($waited -lt 60) {
            $out = (docker compose ps postgres --format json 2>$null | Out-String).Trim()
            if ($out -match '"healthy"') { break }
            Start-Sleep 2
            $waited += 2
            Write-Host "    ${waited}s ..." -ForegroundColor DarkGray
        }
        if ($waited -ge 60) { Write-Warn "postgres 健康检查超时，继续（可能还在启动中）" }
        else { Write-OK "postgres 就绪" }

        # 3. 把 .env 里的 Docker 地址替换为 localhost，以环境变量形式注入
        $devEnv = Get-DevEnv
        $envLine = ($devEnv.GetEnumerator() | ForEach-Object {
            "`$env:$($_.Key) = '$($_.Value)'"
        }) -join '; '

        # 4. 安装后端依赖（首次）
        if (-not (Test-Path (Join-Path $Backend ".venv"))) {
            Write-Step "安装后端依赖（uv sync）..."
            Push-Location $Backend; uv sync; Pop-Location
        }

        # 5. 启动后端（新窗口，热重载）
        Write-Step "在新窗口启动后端（热重载）..."
        $backendCmd = "$envLine; Write-Host 'WorkPilot Backend  http://localhost:8000/docs' -ForegroundColor Cyan; uv run fastapi dev main.py"
        Start-NativeProcess $BackendPid $Backend $backendCmd "Backend"

        # 等几秒让后端起来
        Start-Sleep -Seconds 4

        # 6. 安装前端依赖（首次）
        if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
            Write-Step "安装前端依赖（npm install）..."
            Push-Location $Frontend; npm install --silent; Pop-Location
        }

        # 7. 启动前端（新窗口，Vite hot reload）
        Write-Step "在新窗口启动前端（Vite dev server）..."
        $frontendCmd = "Write-Host 'WorkPilot Frontend  http://localhost:5173' -ForegroundColor Cyan; npm run dev"
        Start-NativeProcess $FrontendPid $Frontend $frontendCmd "Frontend"

        Write-Rule
        Write-OK "开发环境已就绪！"
        Write-Host "  前端      -> http://localhost:5173"      -ForegroundColor White
        Write-Host "  Swagger   -> http://localhost:8000/docs" -ForegroundColor White
        Write-Host ""
        Write-Host "  后端改代码  -> 自动热重载，无需任何操作" -ForegroundColor DarkGray
        Write-Host "  前端改代码  -> 自动热重载，无需任何操作" -ForegroundColor DarkGray
        Write-Host "  停止服务    -> .\dev.ps1 stop"           -ForegroundColor DarkGray
        Write-Rule
    }

    "stop" {
        Write-Title "WorkPilot - 停止开发环境"
        Write-Rule
        Stop-NativeProcess $BackendPid  "Backend"
        Stop-NativeProcess $FrontendPid "Frontend"
        Write-Step "停止 Docker 容器..."
        Invoke-DC stop postgres ollama | Out-Null
        Write-OK "已停止（数据卷保留）"
        Write-Host "  清除全部数据：docker compose down -v" -ForegroundColor DarkGray
        Write-Rule
    }

    "restart" {
        $target = if ($Service -ne "postgres") { $Service } else { "be" }

        if ($target -in @("be", "backend")) {
            Write-Title "WorkPilot - 重启后端"
            Assert-Uv
            Assert-Env
            Stop-NativeProcess $BackendPid "Backend"
            Start-Sleep -Seconds 1
            $devEnv = Get-DevEnv
            $envLine = ($devEnv.GetEnumerator() | ForEach-Object {
                "`$env:$($_.Key) = '$($_.Value)'"
            }) -join '; '
            $backendCmd = "$envLine; Write-Host 'WorkPilot Backend  http://localhost:8000/docs' -ForegroundColor Cyan; uv run fastapi dev main.py"
            Start-NativeProcess $BackendPid $Backend $backendCmd "Backend"
            Write-OK "后端已重启  -> http://localhost:8000/docs"
        }
        elseif ($target -in @("fe", "frontend")) {
            Write-Title "WorkPilot - 重启前端"
            Assert-Node
            Stop-NativeProcess $FrontendPid "Frontend"
            Start-Sleep -Seconds 1
            $frontendCmd = "Write-Host 'WorkPilot Frontend  http://localhost:5173' -ForegroundColor Cyan; npm run dev"
            Start-NativeProcess $FrontendPid $Frontend $frontendCmd "Frontend"
            Write-OK "前端已重启  -> http://localhost:5173"
        }
        elseif ($target -eq "all") {
            Write-Title "WorkPilot - 重启后端和前端"
            Assert-Uv
            Assert-Node
            Assert-Env
            # 后端
            Stop-NativeProcess $BackendPid "Backend"
            Start-Sleep -Seconds 1
            $devEnv = Get-DevEnv
            $envLine = ($devEnv.GetEnumerator() | ForEach-Object {
                "`$env:$($_.Key) = '$($_.Value)'"
            }) -join '; '
            $backendCmd = "$envLine; Write-Host 'WorkPilot Backend  http://localhost:8000/docs' -ForegroundColor Cyan; uv run fastapi dev main.py"
            Start-NativeProcess $BackendPid $Backend $backendCmd "Backend"
            # 前端
            Stop-NativeProcess $FrontendPid "Frontend"
            Start-Sleep -Seconds 1
            $frontendCmd = "Write-Host 'WorkPilot Frontend  http://localhost:5173' -ForegroundColor Cyan; npm run dev"
            Start-NativeProcess $FrontendPid $Frontend $frontendCmd "Frontend"
            Write-OK "后端和前端已重启"
        }
        else {
            Write-Err "未知服务: $target（可选: be/fe/all）"
            exit 1
        }
    }

    "status" {
        Write-Title "WorkPilot - 服务状态"
        Write-Rule
        Assert-Docker
        Write-Host "`nDocker 容器：" -ForegroundColor White
        Invoke-DC ps --format "table {{.Service}}`t{{.Status}}`t{{.Ports}}"
        Write-Host "`n本机进程：" -ForegroundColor White
        Write-Host "  $(Get-ProcessStatus $BackendPid  'Backend')"  -ForegroundColor Cyan
        Write-Host "  $(Get-ProcessStatus $FrontendPid 'Frontend')" -ForegroundColor Cyan
        Write-Rule
    }

    "logs" {
        Assert-Docker
        Write-Host "追踪 $Service 日志  （Ctrl+C 退出）" -ForegroundColor Cyan
        Invoke-DC logs -f --tail=100 $Service
    }

    "pull-models" {
        Write-Title "WorkPilot - 拉取 Ollama 模型（首次部署时执行）"
        Write-Rule
        Assert-Docker
        Invoke-DC up -d ollama | Out-Null
        Start-Sleep 3
        Write-Step "拉取 nomic-embed-text（Embedding 模型）..."
        Invoke-DC exec ollama ollama pull nomic-embed-text
        Write-Step "拉取 qwen2.5:7b（推理模型）..."
        Invoke-DC exec ollama ollama pull "qwen2.5:7b"
        Write-OK "模型已就绪"
        Write-Rule
    }

    "psql" {
        Assert-Docker
        Write-Step "进入 PostgreSQL（\q 退出）..."
        Invoke-DC exec postgres psql -U workpilot -d workpilot
    }

    default {
        Write-Host "用法：.\dev.ps1 [start|stop|restart|status|logs|pull-models|psql]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  restart 可选参数：" -ForegroundColor Yellow
        Write-Host "    .\dev.ps1 restart        重启后端（默认）" -ForegroundColor Gray
        Write-Host "    .\dev.ps1 restart be     重启后端" -ForegroundColor Gray
        Write-Host "    .\dev.ps1 restart fe     重启前端" -ForegroundColor Gray
        Write-Host "    .\dev.ps1 restart all    重启后端和前端" -ForegroundColor Gray
        exit 1
    }
}
