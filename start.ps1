# WorkPilot v2 - 稳定启动脚本（全 Docker，代码有变动时重新构建）
# 用法：.\start.ps1
# 停止：.\stop.ps1
#
# 与 dev.ps1 的区别：
#   start.ps1  全服务跑在 Docker 内（nginx + 构建好的前端产物），稳定部署用
#   dev.ps1    后端/数据库跑 Docker，前端用 npm run dev 热更新，开发调试用
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  WorkPilot v2  -  启动（Docker 完整部署）" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 backend/.env
$envFile = Join-Path $PSScriptRoot "backend\.env"
if (-not (Test-Path $envFile)) {
    $example = Join-Path $PSScriptRoot "backend\.env.example"
    if (Test-Path $example) {
        Copy-Item $example $envFile
        Write-Host "  已从 .env.example 创建 backend/.env，请先修改 JWT_SECRET_KEY 和 POSTGRES_PASSWORD 后重试。" -ForegroundColor Yellow
    } else {
        Write-Host "  错误：找不到 backend/.env，请先创建并配置。" -ForegroundColor Red
    }
    exit 1
}

# 2. 构建并启动所有容器（--build 确保代码变动后重新构建镜像）
Write-Host "[1/3] 构建镜像并启动所有容器（首次或代码变动后需要较长时间）..." -ForegroundColor Yellow
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  错误：docker compose up 失败，请确认 Docker Desktop 已运行。" -ForegroundColor Red
    exit 1
}
Write-Host "      容器已启动" -ForegroundColor Green

# 3. 等待 backend 健康检查通过
Write-Host "[2/3] 等待 backend 就绪（最长 120 秒）..." -ForegroundColor Yellow
$elapsed = 0
$ready = $false
while ($elapsed -lt 120) {
    try {
        $cid = (docker compose ps -q backend 2>$null | Out-String).Trim()
        if ($cid) {
            $health = (docker inspect --format "{{.State.Health.Status}}" $cid 2>$null | Out-String).Trim()
            if ($health -eq "healthy") { $ready = $true; break }
        }
    } catch {}
    Start-Sleep -Seconds 3
    $elapsed += 3
    Write-Host "    ${elapsed}s ..." -ForegroundColor DarkGray
}
if (-not $ready) {
    Write-Host "  警告：backend 健康检查超时，运行 'docker compose logs -f backend' 查看详情。" -ForegroundColor Yellow
} else {
    Write-Host "  backend 已就绪（${elapsed}s）" -ForegroundColor Green
}

# 4. 等待 nginx（最终对外入口）
Write-Host "[3/3] 等待 nginx 响应..." -ForegroundColor Yellow
$nginx_ready = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost/" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        $nginx_ready = $true; break
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
if ($nginx_ready) {
    Write-Host "  启动完成！" -ForegroundColor Green
} else {
    Write-Host "  容器已启动（nginx 可能还在初始化中）" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  访问地址：http://localhost" -ForegroundColor White
Write-Host "  API 文档：http://localhost/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "  查看日志：docker compose logs -f backend" -ForegroundColor Gray
Write-Host "  停止服务：.\stop.ps1" -ForegroundColor Gray
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
