"""进制转换演示器入口。

运行：
    python main.py
"""

from __future__ import annotations

import sys
import traceback


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


def _show_startup_error(message: str) -> None:
    """启动失败时给出可见提示：优先 Tk 弹窗，其次 Windows 原生弹窗。"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", message)
        root.destroy()
        return
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "启动失败", 0x10)
            return
        except Exception:
            pass
    print(message)


def main() -> None:
    _enable_high_dpi()
    try:
        from base_converter.app import BaseConverterApp
    except ImportError as exc:
        detail = str(exc)
        if "tkinter" in detail.lower() or "_tkinter" in detail.lower():
            message = (
                "启动失败：没有找到 Tkinter。请安装带 Tk 支持的 Python。\n\n"
                f"详细信息：{detail}"
            )
        else:
            message = f"启动失败：依赖模块导入失败。\n\n详细信息：{detail}"
        _show_startup_error(message)
        return

    try:
        app = BaseConverterApp()
        app.mainloop()
    except Exception:
        _show_startup_error(
            "启动失败：程序初始化或运行时发生异常。\n\n" + traceback.format_exc()
        )


if __name__ == "__main__":
    main()
