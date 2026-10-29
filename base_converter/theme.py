"""界面的颜色、字体与尺寸常量。

集中管理视觉参数，方便统一调整主题。
"""

from __future__ import annotations

import tkinter.font as tkfont

# 深色主题色板
BG = "#07111F"
BG_SOFT = "#0A1727"
SURFACE = "#0E1D30"
SURFACE_2 = "#12243A"
SURFACE_3 = "#172D47"
BORDER = "#213B58"
BORDER_SOFT = "#192F49"

TEXT = "#F2F7FD"
TEXT_DIM = "#B7C9DC"
MUTED = "#7F98B3"
MUTED_2 = "#5E7897"

ACCENT = "#39C6F4"
ACCENT_BRIGHT = "#7BE3FF"
ACCENT_DARK = "#083247"
ACCENT_SOFT = "#0D3B54"
GREEN = "#34D399"
GREEN_DARK = "#063D31"
PURPLE = "#A78BFA"
PURPLE_DARK = "#261E4D"
AMBER = "#FBBF24"
RED = "#FB7185"
RED_DARK = "#461523"

UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"

STEP_COLORS = {
    "info": (PURPLE, PURPLE_DARK),
    "expand": (ACCENT, ACCENT_DARK),
    "divide": (GREEN, GREEN_DARK),
}


def font(size: int, weight: str = "normal", family: str | None = None) -> tuple:
    """返回 Tk 字体元组。"""
    return (family or UI_FONT, size, weight)


def mono(size: int, weight: str = "normal") -> tuple:
    return (MONO_FONT, size, weight)


def resolve_fonts(root) -> None:
    """如果系统缺少首选字体，自动退回可用字体。"""
    global UI_FONT, MONO_FONT
    families = set(tkfont.families(root))
    if UI_FONT not in families:
        for candidate in ("Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI"):
            if candidate in families:
                UI_FONT = candidate
                break
        else:
            UI_FONT = "TkDefaultFont"
    if MONO_FONT not in families:
        for candidate in ("Cascadia Mono", "Consolas", "Courier New", "Courier"):
            if candidate in families:
                MONO_FONT = candidate
                break
        else:
            MONO_FONT = "TkFixedFont"
