# WorkPilot v2 - 停止脚本（停止全部 Docker 容器，保留数据卷）
# 用法：.\stop.ps1
# 彻底清除数据和镜像：docker compose down -v --rmi all
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  WorkPilot v2  -  停止中..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

docker compose down
if ($LASTEXITCODE -eq 0) {
    Write-Host "  所有容器已停止，数据卷已保留。" -ForegroundColor Green
    Write-Host "  彻底清除数据：docker compose down -v" -ForegroundColor Gray
} else {
    Write-Host "  警告：docker compose down 返回非 0，请手动检查。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
