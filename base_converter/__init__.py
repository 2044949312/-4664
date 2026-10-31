"""进制转换演示器。

包的顶层只做惰性导出：导入 ``base_converter.converter`` 时不会连带导入
tkinter 或图形界面代码，方便在没有图形环境的机器上单独测试核心逻辑。

用法保持不变：
    from base_converter import BaseConverterApp
首次访问 ``BaseConverterApp`` 时才会真正导入 ``base_converter.app``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅用于类型检查，运行时不导入 tkinter。
    from .app import BaseConverterApp

__all__ = ["BaseConverterApp"]


def __getattr__(name: str):
    """PEP 562 模块级 __getattr__：按需加载图形界面类。"""
    if name == "BaseConverterApp":
        from .app import BaseConverterApp

        globals()[name] = BaseConverterApp
        return BaseConverterApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
