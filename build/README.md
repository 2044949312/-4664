# 进制转换演示器 · 打包说明

本目录存放可复现的 PyInstaller 打包配置，发布版本为 Windows 64 位 onedir（免安装）。

## 环境要求

- Windows 10/11 x64
- Python 3.10+（建议 3.12，与发布版本一致）
- 打包依赖（仅构建需要，程序运行零第三方依赖）：

```powershell
python -m pip install --upgrade pyinstaller
```

## 一键打包

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

脚本会：

1. 使用 `build/BaseConverterDir.spec` 打包；
2. 输出到 `build/dist/BaseConverterDir/`；
3. 把 `BaseConverterDir.exe` 复制为项目根目录的 `进制转换演示器.exe`，并同步替换 `_internal/`。

## 版本信息与清单

- `version_info.txt`：exe 文件属性中的版本号（当前 1.1.0）；
- `app.manifest`：声明 PerMonitorV2 DPI 感知、Windows 10/11 兼容性与 asInvoker 权限；
- `BaseConverterDir.spec`：PyInstaller 配置，使用相对路径，仓库内可直接复现。

## 发布注意

- `进制转换演示器.exe` 必须与 `_internal/` 文件夹同级、一起复制；只复制 exe 会提示找不到 `python312.dll`。
- 未做代码签名，首次运行可能触发 Windows SmartScreen，提示“已保护你的电脑”，选择“更多信息 → 仍要运行”即可。
- 若需要单文件版本，可在 spec 中把 `EXE`/`COLLECT` 改为 onefile 模式，但启动会变慢且会解压到临时目录。
