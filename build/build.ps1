# 进制转换演示器 · 一键打包脚本
# 用法（项目根目录）：
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
# 可选：先安装 PyInstaller
#   powershell -ExecutionPolicy Bypass -File build\build.ps1 -InstallPyInstaller

param(
    [switch]$InstallPyInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
# Windows 上 python 可能只是应用商店占位程序，优先使用 py 启动器。
$Python = "python"
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
}
Push-Location $ProjectRoot
try {
    if ($InstallPyInstaller) {
        & $Python -m pip install --upgrade pyinstaller
    }

    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        (Join-Path $PSScriptRoot "BaseConverterDir.spec") `
        --distpath (Join-Path $ProjectRoot "build\dist") `
        --workpath (Join-Path $ProjectRoot "build\work")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败（退出码 $LASTEXITCODE）"
    }

    $distDir = Join-Path $ProjectRoot "build\dist\BaseConverterDir"
    $distExe = Join-Path $distDir "BaseConverterDir.exe"
    $distInternal = Join-Path $distDir "_internal"
    if (-not (Test-Path $distExe)) { throw "未找到打包产物：$distExe" }

    Copy-Item $distExe (Join-Path $ProjectRoot "进制转换演示器.exe") -Force
    $targetInternal = Join-Path $ProjectRoot "_internal"
    if (Test-Path $targetInternal) { Remove-Item $targetInternal -Recurse -Force }
    Copy-Item $distInternal $targetInternal -Recurse -Force
    Write-Host "打包完成：进制转换演示器.exe + _internal 已更新。" -ForegroundColor Green
}
finally {
    Pop-Location
}
