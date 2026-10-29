"""进制转换演示器入口。

运行：
    python main.py
"""

from __future__ import annotations

import sys


def _enable_high_dpi() -> None:
    """Windows 高缩放屏幕下让窗口和字体更清晰。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


def main() -> None:
    _enable_high_dpi()
    try:
        from base_converter.app import BaseConverterApp
    except ImportError as exc:
        print("启动失败：没有找到 Tkinter。请安装带 Tk 支持的 Python。")
        print(f"详细信息：{exc}")
        input("按 Enter 键退出...")
        return

    app = BaseConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
