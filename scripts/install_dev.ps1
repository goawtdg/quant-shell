# 开发环境安装（纯壳 + desk + 可选 reference）
# 用法: powershell -File scripts/install_dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing quant-shell [desk,dev]..."
pip install -e ".[desk,dev]"

$Ref = Join-Path $Root "packages\quant-shell-reference"
if (Test-Path $Ref) {
    Write-Host "Installing quant-shell-reference..."
    pip install -e $Ref
} else {
    Write-Host "WARN: packages/quant-shell-reference missing"
}

Write-Host "Done. Check: python -m quant_shell.cli plugins"
Write-Host "Desk API: python -m quant_shell.desk"
