"""图形界面：把进制转换的计算过程变成可读、可演示的步骤卡片。"""

from __future__ import annotations

import re
import sys
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from pathlib import Path
from tkinter import messagebox, ttk

from . import theme
from .converter import (
    MAX_BASE,
    MAX_INPUT_DIGITS,
    MIN_BASE,
    ConversionError,
    ConversionResult,
    Step,
    base_name,
    build_conversion,
    build_quick_examples,
)
from .widgets import BasePickerButton, RoundedButton, ScrollableFrame, _rounded_points, divider

APP_VERSION = "1.1.0"

# 超过该行数后，步骤表格改用单个只读 Text 控件渲染：
# 这样即使 96 位输入产生数百行，也不会因为创建上千个 Label 而冻结界面。
MAX_GRID_ROWS = 40

# 预览成功后再次按 Enter 时忽略重复触发；这些键也不应该触发实时预览。
_PREVIEW_IGNORED_KEYS = {
    "Left", "Right", "Up", "Down", "Home", "End", "Tab", "Shift_L", "Shift_R",
    "Control_L", "Control_R", "Alt_L", "Alt_R", "Escape", "Return", "KP_Enter", "F5",
}


class BaseConverterApp(tk.Tk):
    """进制转换演示器主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        # 统一不同缩放比例下的视觉大小：低缩放保持原样，高 DPI 最多放大到 2.0 倍；
        # 窗口尺寸也会根据屏幕可用区域和缩放比例自适应，避免小屏/4K 屏体验失控。
        self._ui_scale = self._configure_scaling()
        theme.resolve_fonts(self)

        self.title(f"进制转换演示器 v{APP_VERSION} · Base Conversion Explorer")
        self.configure(bg=theme.BG)
        self._setup_window()
        self._set_window_icon()

        # 数据状态
        self._base_options = [
            (base, base_name(base)) for base in range(MIN_BASE, MAX_BASE + 1)
        ]
        self.number_var = tk.StringVar(value="255")
        self.hint_var = tk.StringVar(value="")
        self.error_var = tk.StringVar(value="")
        self.expression_var = tk.StringVar(value="等待输入")
        self.result_var = tk.StringVar(value="—")
        self.meta_var = tk.StringVar(value="选择源进制与目标进制，再输入整数")
        self.status_var = tk.StringVar(value="就绪 · 输入数字后按 Enter 快速转换")
        self.step_count_var = tk.StringVar(value="0 步")

        self.result: ConversionResult | None = None
        self._preview_job: str | None = None
        self._toast_job: str | None = None
        self._last_state_key: tuple[str, int, int] | None = None
        self._busy = False

        self._build_ui()
        self._bind_shortcuts()
        self.number_var.trace_add("write", self._on_number_changed)
        self._on_number_changed()

        # 首次打开时直接展示 255 → 二进制 的示例，方便课堂演示。
        self.after(180, self.convert)

    # ------------------------------------------------------------------ 窗口
    def _configure_scaling(self) -> float:
        try:
            natural_scaling = float(self.tk.call("tk", "scaling"))
        except (tk.TclError, ValueError):
            natural_scaling = 1.333
        scale = min(max(natural_scaling, 1.333), 2.0)
        try:
            self.tk.call("tk", "scaling", scale)
        except tk.TclError:
            pass
        return scale

    @staticmethod
    def _work_area() -> tuple[int, int, int, int]:
        """返回主屏幕可用桌面区域 (x, y, width, height)，单位为物理像素。"""
        if sys.platform == "win32":
            try:
                import ctypes

                class _Rect(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                rect = _Rect()
                ok = ctypes.windll.user32.SystemParametersInfoW(
                    0x0030, 0, ctypes.byref(rect), 0  # SPI_GETWORKAREA
                )
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if ok and width > 320 and height > 240:
                    return rect.left, rect.top, width, height
            except Exception:
                pass
        return 0, 0, 0, 0

    def _setup_window(self) -> None:
        work_x, work_y, work_w, work_h = self._work_area()
        if work_w <= 0 or work_h <= 0:
            work_x, work_y = 0, 0
            work_w = self.winfo_screenwidth()
            work_h = self.winfo_screenheight()

        # 高 DPI（>150%）时适当放大基准窗口，避免 4K 屏幕上界面过小。
        factor = min(1.35, max(1.0, self._ui_scale / 1.5))
        base_w = int(round(1240 * factor))
        base_h = int(round(880 * factor))
        width = min(base_w, max(720, work_w - 40))
        height = min(base_h, max(560, work_h - 80))
        width = min(width, work_w - 20)
        height = min(height, work_h - 20)
        x = work_x + max(0, (work_w - width) // 2)
        y = work_y + max(0, (work_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1000, width), min(640, height))

    # ------------------------------------------------------------------ 基础
    def report_callback_exception(self, exc, val, tb) -> None:  # type: ignore[override]
        """未捕获的界面回调异常：写日志并提示用户，避免窗口无提示消失。"""
        try:
            detail = "".join(traceback.format_exception(exc, val, tb))
        except Exception:
            detail = f"{exc.__name__}: {val}"
        log_path = None
        try:
            log_path = Path(tempfile.gettempdir()) / "进制转换演示器.log"
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n{detail}\n")
        except OSError:
            log_path = None
        hint = f"\n\n详细信息已写入:\n{log_path}" if log_path else ""
        try:
            messagebox.showerror(
                "程序内部错误",
                f"界面发生未处理的异常：\n{val}{hint}",
                parent=self,
            )
        except tk.TclError:
            pass

    @staticmethod
    def _shorten(text: str, limit: int = 48) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _set_window_icon(self) -> None:
        """用 PhotoImage 画一个简单的双向箭头图标，避免依赖外部图片。"""
        image = tk.PhotoImage(width=32, height=32)
        image.put(theme.BG_SOFT, to=(0, 0, 32, 32))
        image.put(theme.SURFACE, to=(2, 2, 30, 30))
        image.put(theme.ACCENT, to=(6, 10, 26, 12))
        image.put(theme.ACCENT_BRIGHT, to=(6, 20, 26, 22))
        # 上箭头：右端向下收尖；下箭头：左端向上收尖
        image.put(theme.ACCENT, to=(26, 8, 29, 14))
        image.put(theme.ACCENT_BRIGHT, to=(3, 18, 6, 24))
        self.iconphoto(True, image)
        self._icon_image = image  # 防止被垃圾回收

    def _bind_shortcuts(self) -> None:
        self.bind("<Return>", self.convert)
        self.bind("<F5>", self.convert)
        self.bind("<Escape>", self._on_escape)
        # Windows 使用 <MouseWheel>，Linux/X11 的滚轮则是 Button-4/5。
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._on_mousewheel)
        self.bind("<Control-Shift-C>", lambda _event: self._copy_expression())

    # ------------------------------------------------------------------ 布局
    def _build_ui(self) -> None:
        self._build_header()
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 8))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=356)
        body.grid_columnconfigure(1, weight=1)

        # 左侧输入区放进可滚动容器：小屏（如 1366×768 投影）下也能看到全部设置。
        self.input_scroll = ScrollableFrame(body, bg=theme.BG, autohide_scrollbar=True)
        self.input_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        input_panel = self._build_input_panel(self.input_scroll.inner)
        input_panel.pack(fill="x", padx=(0, 6))
        right = self._build_right_panel(body)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_footer()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=theme.BG)
        header.pack(fill="x", padx=28, pady=(20, 14))

        logo = tk.Canvas(header, width=46, height=46, bg=theme.BG, highlightthickness=0)
        logo.pack(side="left", padx=(0, 14))
        logo.create_polygon(
            *_rounded_points(1, 1, 45, 45, 13),
            smooth=True,
            splinesteps=24,
            fill=theme.SURFACE_2,
            outline=theme.BORDER,
            width=1,
        )
        logo.create_line(13, 18, 33, 18, fill=theme.ACCENT, width=2, arrow="last")
        logo.create_line(33, 28, 13, 28, fill=theme.ACCENT_BRIGHT, width=2, arrow="last")

        text_box = tk.Frame(header, bg=theme.BG)
        text_box.pack(side="left")
        tk.Label(
            text_box,
            text="进制转换演示器",
            font=theme.font(21, "bold"),
            fg=theme.TEXT,
            bg=theme.BG,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text_box,
            text="BASE CONVERSION EXPLORER   ·   按权展开 × 除基取余",
            font=theme.font(8, "bold"),
            fg=theme.MUTED,
            bg=theme.BG,
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        badge = tk.Frame(
            header,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            padx=13,
            pady=8,
        )
        badge.pack(side="right", pady=6)
        dot = tk.Canvas(badge, width=8, height=8, bg=theme.SURFACE, highlightthickness=0)
        dot.pack(side="left", padx=(0, 8))
        dot.create_oval(1, 1, 7, 7, fill=theme.GREEN, outline="")
        tk.Label(
            badge,
            text="计算机科学基础  ·  导论大作业",
            font=theme.font(8, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
        ).pack(side="left")

    def _build_input_panel(self, parent: tk.Misc) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        inner = tk.Frame(card, bg=theme.SURFACE, padx=20, pady=18)
        inner.pack(fill="both", expand=True)

        title_row = tk.Frame(inner, bg=theme.SURFACE)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text="输入设置",
            font=theme.font(12, "bold"),
            fg=theme.TEXT,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            title_row,
            text="整数",
            font=theme.font(8, "bold"),
            fg=theme.ACCENT,
            bg=theme.ACCENT_SOFT,
            padx=8,
            pady=2,
        ).pack(side="right")

        field_row = tk.Frame(inner, bg=theme.SURFACE)
        field_row.pack(fill="x", pady=(12, 7))
        tk.Label(
            field_row,
            text="待转换数字",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(side="left")
        self.clear_button = RoundedButton(
            field_row,
            "清空",
            self._clear_input,
            fill=theme.SURFACE_2,
            hover_fill=theme.SURFACE_3,
            text_color=theme.TEXT_DIM,
            height=24,
            width=52,
            radius=7,
            font=theme.font(8),
            border=theme.BORDER_SOFT,
            background=theme.SURFACE,
        )
        self.clear_button.pack(side="right")

        self.entry = tk.Entry(
            inner,
            textvariable=self.number_var,
            font=theme.mono(21, "bold"),
            bg=theme.BG_SOFT,
            fg=theme.TEXT,
            insertbackground=theme.ACCENT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT,
            selectbackground=theme.ACCENT_DARK,
            selectforeground=theme.TEXT,
        )
        self.entry.pack(fill="x", ipady=10)
        self.entry.bind("<KeyRelease>", self._schedule_preview)
        self.entry.bind("<Control-a>", self._select_all)

        self.hint_label = tk.Label(
            inner,
            textvariable=self.hint_var,
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.hint_label.pack(fill="x", pady=(4, 0))

        self.error_label = tk.Label(
            inner,
            textvariable=self.error_var,
            font=theme.font(8),
            fg=theme.RED,
            bg=theme.SURFACE,
            anchor="nw",
            justify="left",
            height=1,
            wraplength=300,
        )
        self.error_label.pack(fill="x", pady=(4, 0))

        divider(inner, pady=(2, 10))

        selector = tk.Frame(inner, bg=theme.SURFACE)
        selector.pack(fill="x", pady=(0, 10))
        selector.grid_columnconfigure(0, weight=1)
        selector.grid_columnconfigure(2, weight=1)

        tk.Label(
            selector,
            text="源进制",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Label(
            selector,
            text="目标进制",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.source_picker = BasePickerButton(
            selector,
            base=10,
            options=self._base_options,
            on_select=self._on_base_changed,
            title="选择源进制",
            height=38,
        )
        self.source_picker.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(6, 0))

        swap_btn = RoundedButton(
            selector,
            "⇄",
            self._swap_bases,
            fill=theme.SURFACE_2,
            hover_fill=theme.SURFACE_3,
            text_color=theme.ACCENT,
            height=36,
            width=38,
            radius=9,
            font=theme.font(13, "bold"),
            border=theme.BORDER_SOFT,
            background=theme.SURFACE,
        )
        swap_btn.grid(row=1, column=1, pady=(6, 0))

        self.target_picker = BasePickerButton(
            selector,
            base=2,
            options=self._base_options,
            on_select=self._on_base_changed,
            title="选择目标进制",
            height=38,
        )
        self.target_picker.grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=(6, 0))

        self.convert_button = RoundedButton(
            inner,
            "开始转换    ↵",
            self.convert,
            fill=theme.ACCENT,
            hover_fill=theme.ACCENT_BRIGHT,
            text_color="#052333",
            height=46,
            radius=12,
            font=theme.font(11, "bold"),
            background=theme.SURFACE,
        )
        self.convert_button.pack(fill="x", pady=(2, 10))

        divider(inner, pady=(0, 10))

        tk.Label(
            inner,
            text="快速示例",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        examples = tk.Frame(inner, bg=theme.SURFACE)
        examples.pack(fill="x")
        examples.grid_columnconfigure(0, weight=1)
        examples.grid_columnconfigure(1, weight=1)
        for index, (label, text, src, tgt) in enumerate(build_quick_examples()):
            button = RoundedButton(
                examples,
                label,
                lambda t=text, s=src, g=tgt: self._apply_example(t, s, g),
                fill=theme.SURFACE_2,
                hover_fill=theme.SURFACE_3,
                text_color=theme.TEXT_DIM,
                height=34,
                radius=8,
                font=theme.font(8),
                border=theme.BORDER_SOFT,
                background=theme.SURFACE,
            )
            row, col = divmod(index, 2)
            button.grid(
                row=row,
                column=col,
                sticky="ew",
                padx=(0, 5) if col == 0 else (5, 0),
                pady=(0, 5),
            )

        divider(inner, pady=(4, 10))

        tk.Label(
            inner,
            text="进制速查",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        hint_box = tk.Frame(
            inner,
            bg=theme.BG_SOFT,
            highlightbackground=theme.BORDER_SOFT,
            highlightthickness=1,
            padx=11,
            pady=7,
        )
        hint_box.pack(fill="x")
        tk.Label(
            hint_box,
            text="0b1010  二进制     0o17  八进制\n0x1F  十六进制     A–Z  表示 10–35",
            font=theme.mono(8),
            fg=theme.TEXT_DIM,
            bg=theme.BG_SOFT,
            anchor="w",
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            hint_box,
            text=f"{MIN_BASE}–{MAX_BASE} 进制  ·  最多 {MAX_INPUT_DIGITS} 位  ·  仅演示整数",
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.BG_SOFT,
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        return card

    def _build_right_panel(self, parent: tk.Misc) -> tk.Frame:
        right = tk.Frame(parent, bg=theme.BG)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._build_result_card(right).grid(row=0, column=0, sticky="ew")
        self._build_steps_header(right).grid(row=1, column=0, sticky="ew", pady=(16, 9))
        self.steps = ScrollableFrame(right, bg=theme.BG)
        self.steps.grid(row=2, column=0, sticky="nsew")
        return right

    def _build_result_card(self, parent: tk.Misc) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        bar = tk.Frame(card, bg=theme.ACCENT, width=4)
        bar.pack(side="left", fill="y")

        content = tk.Frame(card, bg=theme.SURFACE, padx=20, pady=14)
        content.pack(side="left", fill="both", expand=True)

        top = tk.Frame(content, bg=theme.SURFACE)
        top.pack(fill="x")
        tk.Label(
            top,
            text="转换结果",
            font=theme.font(9, "bold"),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(side="left")
        self.copy_expr_button = RoundedButton(
            top,
            "复制表达式",
            self._copy_expression,
            fill=theme.SURFACE_2,
            hover_fill=theme.SURFACE_3,
            text_color=theme.TEXT_DIM,
            height=28,
            width=96,
            radius=8,
            font=theme.font(8),
            border=theme.BORDER_SOFT,
            background=theme.SURFACE,
            disabled=True,
        )
        self.copy_expr_button.pack(side="right", padx=(0, 6))
        self.copy_button = RoundedButton(
            top,
            "复制结果",
            self._copy_result,
            fill=theme.SURFACE_2,
            hover_fill=theme.SURFACE_3,
            text_color=theme.TEXT_DIM,
            height=28,
            width=84,
            radius=8,
            font=theme.font(8),
            border=theme.BORDER_SOFT,
            background=theme.SURFACE,
            disabled=True,
        )
        self.copy_button.pack(side="right")

        self.expression_label = tk.Label(
            content,
            textvariable=self.expression_var,
            font=theme.mono(10),
            fg=theme.ACCENT,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
        )
        self.expression_label.pack(fill="x", pady=(7, 2))

        self.result_label = tk.Label(
            content,
            textvariable=self.result_var,
            font=theme.mono(31, "bold"),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
        )
        self.result_label.pack(fill="x")

        self.meta_label = tk.Label(
            content,
            textvariable=self.meta_var,
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
        )
        self.meta_label.pack(fill="x", pady=(3, 0))

        content.bind("<Configure>", self._on_result_resize)
        return card

    def _build_steps_header(self, parent: tk.Misc) -> tk.Frame:
        header = tk.Frame(parent, bg=theme.BG)
        header.grid_columnconfigure(0, weight=1)

        title_box = tk.Frame(header, bg=theme.BG)
        title_box.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_box,
            text="转换过程",
            font=theme.font(13, "bold"),
            fg=theme.TEXT,
            bg=theme.BG,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            title_box,
            textvariable=self.step_count_var,
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.BG,
            anchor="w",
        ).pack(side="left", padx=(10, 0), pady=(3, 0))

        legend = tk.Frame(header, bg=theme.BG)
        legend.grid(row=0, column=1, sticky="e")
        for color, label in (
            (theme.ACCENT, "按权展开"),
            (theme.GREEN, "除基取余"),
            (theme.PURPLE, "说明"),
        ):
            dot = tk.Canvas(legend, width=8, height=8, bg=theme.BG, highlightthickness=0)
            dot.pack(side="left", padx=(10, 4))
            dot.create_oval(1, 1, 7, 7, fill=color, outline="")
            tk.Label(
                legend,
                text=label,
                font=theme.font(8),
                fg=theme.MUTED,
                bg=theme.BG,
            ).pack(side="left")
        return header

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=theme.BG)
        footer.pack(fill="x", padx=28, pady=(0, 13))
        dot = tk.Canvas(footer, width=8, height=8, bg=theme.BG, highlightthickness=0)
        dot.pack(side="left", padx=(1, 7))
        self.status_dot_canvas = dot
        self.status_dot = dot.create_oval(1, 1, 7, 7, fill=theme.GREEN, outline="")
        tk.Label(
            footer,
            textvariable=self.status_var,
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.BG,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            footer,
            text=f"纯 Python 标准库 · Tkinter · v{APP_VERSION}",
            font=theme.font(8),
            fg=theme.MUTED_2,
            bg=theme.BG,
            anchor="e",
        ).pack(side="right")

    # ------------------------------------------------------------------ 事件
    def _select_all(self, _event=None):
        self.entry.selection_range(0, "end")
        return "break"

    def _on_mousewheel(self, event):
        for area in (self.input_scroll, self.steps):
            if area.contains_pointer(event.x_root, event.y_root):
                area.on_mousewheel(event)
                return "break"
        return None

    def _on_escape(self, _event=None):
        """Esc：清空输入（输入框获得焦点时）。"""
        if self.focus_get() is self.entry and self.number_var.get():
            self._clear_input()
            return "break"
        return None

    def _on_number_changed(self, *_args) -> None:
        if self.number_var.get().strip():
            self.hint_var.set("支持 A–Z 数码、空格/下划线、0b/0o/0x 前缀；仅演示整数")
        else:
            self.hint_var.set("输入整数，例如 255、FF、1010、-1010")

    def _on_base_changed(self, _event=None) -> None:
        self.entry.focus_set()
        self.convert()

    def _cancel_preview(self) -> None:
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
            self._preview_job = None

    def _schedule_preview(self, event=None) -> None:
        # Enter/F5 已经会立即转换，KeyRelease 不应再排一次预览，否则会重复渲染。
        if event is not None and event.keysym in _PREVIEW_IGNORED_KEYS:
            return
        self._cancel_preview()
        self._preview_job = self.after(380, self._preview)

    def _preview(self) -> None:
        self._preview_job = None
        source_base, target_base = self._selected_bases()
        text = self.number_var.get()
        key = (text, source_base, target_base)
        if key == self._last_state_key:
            return
        try:
            result = build_conversion(text, source_base, target_base)
        except ConversionError as exc:
            # 预览失败必须让用户看到“当前输入无效”，不能继续展示旧结果。
            self._show_error(exc.message, key)
            return
        self._apply_result(result, silent=True)

    def _selected_bases(self) -> tuple[int, int]:
        return self.source_picker.get_base(), self.target_picker.get_base()

    def _set_bases(self, source_base: int, target_base: int) -> None:
        self.source_picker.set_base(source_base)
        self.target_picker.set_base(target_base)

    def _swap_bases(self) -> None:
        source, target = self._selected_bases()
        # 先按当前输入重新转换：不能用上一次的 self.result 覆盖用户刚输入的数字。
        try:
            current = build_conversion(self.number_var.get(), source, target)
        except ConversionError:
            current = None
        if current is not None:
            self.number_var.set(current.result_text)
        self._set_bases(target, source)
        self.convert()

    def _apply_example(self, text: str, source_base: int, target_base: int) -> None:
        self.number_var.set(text)
        self._set_bases(source_base, target_base)
        self.entry.icursor("end")
        self.entry.focus_set()
        self.convert()

    # ------------------------------------------------------------------ 转换
    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        try:
            self.configure(cursor="watch" if busy else "")
            if busy:
                self.update_idletasks()
        except tk.TclError:
            pass

    def convert(self, _event=None) -> None:
        self._cancel_preview()
        source_base, target_base = self._selected_bases()
        text = self.number_var.get()
        started = time.perf_counter()
        try:
            result = build_conversion(text, source_base, target_base)
        except ConversionError as exc:
            self._show_error(exc.message, (text, source_base, target_base))
            self.entry.focus_set()
            return
        calc_ms = (time.perf_counter() - started) * 1000
        self._set_busy(True)
        try:
            self._apply_result(result, calc_ms=calc_ms)
        finally:
            self._set_busy(False)
        # 转换后把焦点还给输入框：继续输入/按 Enter 都能直接生效。
        self.entry.focus_set()

    def _apply_result(
        self,
        result: ConversionResult,
        *,
        calc_ms: float | None = None,
        silent: bool = False,
    ) -> None:
        self._last_state_key = (result.raw, result.source_base, result.target_base)
        self.result = result
        self._reset_copy_buttons()
        self.error_var.set("")
        self.error_label.configure(height=1)
        self.entry.configure(highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT)

        # 超长结果只显示前 120 位：避免结果卡占满整个窗口；完整值仍可复制。
        full_result = result.result_text
        shown_result = (
            full_result if len(full_result) <= 120 else full_result[:117] + "…"
        )
        full_expression = result.expression()
        shown_expression = (
            full_expression
            if len(full_expression) <= 200
            else full_expression[:199] + "…"
        )
        decimal_text = result.decimal_text
        shown_decimal = (
            decimal_text if len(decimal_text) <= 60 else decimal_text[:57] + "…"
        )
        result_size = self._fit_result_font(shown_result)
        expr_limit = self._label_char_limit(self.expression_label, theme.mono(10))
        result_limit = self._label_char_limit(
            self.result_label, theme.mono(result_size, "bold")
        )
        self.expression_var.set(self._hard_wrap_tokens(shown_expression, expr_limit))
        self.result_var.set(self._hard_wrap_tokens(shown_result, result_limit))
        self.result_label.configure(fg=theme.TEXT)

        digit_count = len(full_result.lstrip("-"))
        meta_parts = [f"十进制值 {shown_decimal}", f"结果 {digit_count} 位", f"{len(result.steps)} 个步骤"]
        if result.is_negative:
            meta_parts.append("负数按绝对值演算，符号单独保留")
        if len(full_result) > 120:
            meta_parts.append("超长结果仅显示前 120 位，复制可得完整值")
        self.meta_var.set(self._hard_wrap_tokens("  ·  ".join(meta_parts), result_limit))

        self.copy_button.set_enabled(True)
        self.copy_expr_button.set_enabled(True)
        self.step_count_var.set(f"共 {len(result.steps)} 步 · 详细演算")
        render_started = time.perf_counter()
        self._render_steps(result)
        render_ms = (time.perf_counter() - render_started) * 1000
        self.steps.scroll_to_top()
        self.status_dot_canvas.itemconfigure(self.status_dot, fill=theme.GREEN)
        if silent:
            self.status_var.set(f"已实时更新  ·  {len(result.steps)} 个步骤  ·  按 Enter 重新转换")
        elif calc_ms is None:
            self.status_var.set("转换完成")
        else:
            # 同时展示计算与渲染耗时，避免“0.05 ms”误导用户。
            self.status_var.set(
                f"转换完成  ·  计算 {calc_ms:.2f} ms  ·  渲染 {render_ms:.0f} ms"
            )

    def _fit_result_font(self, text: str) -> int:
        length = len(text)
        if length <= 24:
            size = 31
        elif length <= 40:
            size = 25
        elif length <= 64:
            size = 19
        elif length <= 100:
            size = 15
        else:
            size = 12
        self.result_label.configure(font=theme.mono(size, "bold"))
        return size

    @staticmethod
    def _label_char_limit(widget: tk.Misc, font: tuple, fallback_px: int = 900) -> int:
        """估算某个 Label 每行能放多少个等宽字符，用于对超长数字主动换行。"""
        try:
            width = widget.winfo_width()
        except tk.TclError:
            width = 0
        if width <= 50:
            width = fallback_px
        try:
            char_width = max(1, tkfont.Font(font=font).measure("0"))
        except tk.TclError:
            char_width = 10
        return max(12, int((width - 24) / char_width))

    @staticmethod
    def _hard_wrap_tokens(text: str, limit: int) -> str:
        """在超长数字/字母串中插入换行，避免等宽 Label 把内容撑出卡片。

        只拆分纯字母数字 token，中文、空格、括号等原样保留。
        """
        if limit < 8:
            limit = 8

        def wrap_token(token: str) -> str:
            if len(token) <= limit:
                return token
            return "\n".join(
                token[i : i + limit] for i in range(0, len(token), limit)
            )

        return "".join(
            wrap_token(part) if part.isalnum() else part
            for part in re.split(r"([0-9A-Za-z]+)", text)
        )

    def _on_result_resize(self, event) -> None:
        wrap = max(280, event.width - 22)
        self.result_label.configure(wraplength=wrap)
        self.expression_label.configure(wraplength=wrap)
        self.meta_label.configure(wraplength=wrap)

    def _show_error(self, message: str, key: tuple[str, int, int] | None = None) -> None:
        if key is not None:
            self._last_state_key = key
        self.result = None
        self._reset_copy_buttons()
        self.error_var.set(message)
        self.error_label.configure(height=4)
        self.entry.configure(highlightbackground=theme.RED, highlightcolor=theme.RED)
        self.expression_var.set("等待有效输入")
        self.result_var.set("—")
        self.result_label.configure(fg=theme.MUTED, font=theme.mono(31, "bold"))
        self.meta_var.set("修正左侧输入后重新转换")
        self.copy_button.set_enabled(False)
        self.copy_expr_button.set_enabled(False)
        self.step_count_var.set("0 步")
        self.steps.clear()
        self._render_message_card("暂时无法生成步骤", message, theme.RED, "!")
        self.status_dot_canvas.itemconfigure(self.status_dot, fill=theme.RED)
        self.status_var.set("输入有误  ·  请检查数字与源进制是否匹配")

    def _copy_result(self) -> None:
        if self.result is None:
            return
        self._copy_text(self.result.result_text, self.copy_button, "结果")

    def _copy_expression(self) -> None:
        if self.result is None:
            return
        self._copy_text(self.result.expression(), self.copy_expr_button, "表达式")

    def _copy_text(self, text: str, button: RoundedButton, label: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        # 处理一次事件循环，让 Windows 剪贴板真正持有数据（避免立即关闭程序时丢失）。
        self.update_idletasks()
        button.set_text("已复制 ✓")
        self.status_var.set(f"已复制{label}：{self._shorten(text)}")
        if self._toast_job is not None:
            try:
                self.after_cancel(self._toast_job)
            except tk.TclError:
                pass
        self._toast_job = self.after(1800, self._reset_copy_buttons)
        # 复制后把焦点还给输入框，避免下一次按 Enter 又触发复制。
        self.entry.focus_set()

    def _reset_copy_buttons(self) -> None:
        if self._toast_job is not None:
            try:
                self.after_cancel(self._toast_job)
            except tk.TclError:
                pass
            self._toast_job = None
        if hasattr(self, "copy_button"):
            self.copy_button.set_text("复制结果")
        if hasattr(self, "copy_expr_button"):
            self.copy_expr_button.set_text("复制表达式")

    # ------------------------------------------------------------------ 清空
    def _clear_input(self) -> None:
        self._cancel_preview()
        self.number_var.set("")
        self.result = None
        self._last_state_key = None
        self.error_var.set("")
        self.error_label.configure(height=1)
        self.entry.configure(highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT)
        self.expression_var.set("等待输入")
        self.result_var.set("—")
        self.result_label.configure(fg=theme.MUTED, font=theme.mono(31, "bold"))
        self.meta_var.set("输入数字后会自动预览，按 Enter 生成完整步骤")
        self.copy_button.set_enabled(False)
        self.copy_expr_button.set_enabled(False)
        self.step_count_var.set("0 步")
        self.steps.clear()
        self._render_message_card(
            "已清空输入",
            "请输入一个整数，然后按 Enter 或点击「开始转换」。",
            theme.PURPLE,
            "i",
        )
        self.status_dot_canvas.itemconfigure(self.status_dot, fill=theme.GREEN)
        self.status_var.set("已清空  ·  等待输入")
        self.entry.focus_set()

    # ------------------------------------------------------------------ 步骤渲染
    def _render_steps(self, result: ConversionResult) -> None:
        self.steps.clear()
        for index, step in enumerate(result.steps, start=1):
            self._render_step_card(index, step)

    @staticmethod
    def _wrap_long_number(value: str, width: int = 12) -> str:
        """把超长纯数字/字母串按固定宽度断行，防止表格撑破卡片。"""
        if len(value) <= width:
            return value

        def wrap_token(token: str) -> str:
            if len(token) <= width:
                return token
            sign = token[0] if token[:1] in ("+", "-") else ""
            body = token[1:] if sign else token
            if not body or not body.isascii() or not body.isalnum():
                return token
            lines = [body[i : i + width] for i in range(0, len(body), width)]
            if sign:
                lines[0] = sign + lines[0]
            return "\n".join(lines)

        # 计算式里可能含有“123… ÷ 36”这样的混合文本，逐个长 token 处理。
        wrapped = "".join(
            wrap_token(part) if part.isalnum() else part
            for part in re.split(r"([0-9A-Za-z]+)", value)
        )
        # 若混合文本本身仍然超宽，再按字符硬换行，确保表格不会撑开。
        final_lines: list[str] = []
        for line in wrapped.split("\n"):
            if len(line) <= width:
                final_lines.append(line)
            else:
                final_lines.extend(line[i : i + width] for i in range(0, len(line), width))
        return "\n".join(final_lines)

    def _render_message_card(self, title: str, message: str, color: str, mark: str) -> None:
        card = tk.Frame(
            self.steps.inner,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 12))
        body = tk.Frame(card, bg=theme.SURFACE, padx=20, pady=18)
        body.pack(fill="both", expand=True)
        head = tk.Frame(body, bg=theme.SURFACE)
        head.pack(fill="x")
        badge = tk.Label(
            head,
            text=mark,
            font=theme.mono(15, "bold"),
            fg=color,
            bg=theme.SURFACE_2,
            width=3,
            height=1,
        )
        badge.pack(side="left", padx=(0, 12))
        tk.Label(
            head,
            text=title,
            font=theme.font(12, "bold"),
            fg=theme.TEXT,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            body,
            text=message,
            font=theme.font(9),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(fill="x", pady=(10, 0))

    def _render_step_card(self, index: int, step: Step) -> None:
        color, dark = theme.STEP_COLORS.get(step.kind, (theme.MUTED, theme.SURFACE_2))
        card = tk.Frame(
            self.steps.inner,
            bg=theme.SURFACE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 12))
        tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")

        body = tk.Frame(card, bg=theme.SURFACE, padx=16, pady=13)
        body.pack(side="left", fill="both", expand=True)

        head = tk.Frame(body, bg=theme.SURFACE)
        head.pack(fill="x")
        number = tk.Frame(head, bg=dark, width=40, height=40)
        number.pack(side="left", anchor="n")
        number.pack_propagate(False)
        tk.Label(
            number,
            text=f"{index:02d}",
            font=theme.mono(11, "bold"),
            fg=color,
            bg=dark,
        ).pack(expand=True)

        text_box = tk.Frame(head, bg=theme.SURFACE)
        text_box.pack(side="left", fill="x", expand=True, padx=(12, 0))
        tk.Label(
            text_box,
            text=step.kicker,
            font=theme.font(8, "bold"),
            fg=color,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(fill="x")
        title = tk.Label(
            text_box,
            text=step.title,
            font=theme.font(12, "bold"),
            fg=theme.TEXT,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
        )
        title.pack(fill="x", pady=(2, 0))
        desc = tk.Label(
            text_box,
            text=step.description,
            font=theme.font(9),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
            justify="left",
        )
        desc.pack(fill="x", pady=(4, 0))

        if step.headers and step.rows:
            try:
                available_width = self.steps.canvas.winfo_width()
            except tk.TclError:
                available_width = 0
            # 行数多，或窗口很窄放不下 6 列表格时，改用可滚动文本表格，避免横向被裁切。
            use_text_table = len(step.rows) > MAX_GRID_ROWS or (
                len(step.headers) >= 5 and 1 < available_width < 520
            )
            if use_text_table:
                # 行数很多时用单个 Text 控件渲染：保留全部数据，但不会卡住界面。
                self._render_text_table(body, step)
            else:
                self._render_grid_table(body, step)

        formula_label = None
        if step.formula:
            formula_box = tk.Frame(
                body,
                bg=theme.BG_SOFT,
                highlightbackground=theme.BORDER_SOFT,
                highlightthickness=1,
                padx=11,
                pady=8,
            )
            formula_box.pack(fill="x", pady=(10, 0))
            tk.Label(
                formula_box,
                text="推导",
                font=theme.font(8, "bold"),
                fg=color,
                bg=theme.BG_SOFT,
            ).pack(side="left", anchor="n", padx=(0, 10))
            formula_label = tk.Label(
                formula_box,
                text=step.formula,
                font=theme.mono(9),
                fg=theme.TEXT,
                bg=theme.BG_SOFT,
                anchor="w",
                justify="left",
            )
            formula_label.pack(side="left", fill="x", expand=True)

        footer_label = None
        if step.footer:
            footer_box = tk.Frame(body, bg=theme.SURFACE)
            footer_box.pack(fill="x", pady=(8, 0))
            tk.Label(
                footer_box,
                text="✓",
                font=theme.font(9, "bold"),
                fg=color,
                bg=theme.SURFACE,
            ).pack(side="left", anchor="n", padx=(1, 7))
            footer_label = tk.Label(
                footer_box,
                text=step.footer,
                font=theme.font(9),
                fg=theme.TEXT_DIM,
                bg=theme.SURFACE,
                anchor="w",
                justify="left",
            )
            footer_label.pack(side="left", fill="x", expand=True)

        def _on_body_configure(event, *, desc=desc, title=title,
                               formula=formula_label, footer=footer_label):
            wrap = max(250, event.width - 72)
            title.configure(wraplength=wrap)
            desc.configure(wraplength=wrap)
            if formula is not None:
                formula.configure(wraplength=max(220, wrap - 34))
            if footer is not None:
                footer.configure(wraplength=max(220, wrap - 90))

        body.bind("<Configure>", _on_body_configure)

    # ------------------------------------------------------------------ 表格
    def _render_grid_table(self, body: tk.Misc, step: Step) -> None:
        """普通表格：行数不多时使用原生 Label 网格，排版最清晰。"""
        table = tk.Frame(
            body,
            bg=theme.SURFACE_2,
            highlightbackground=theme.BORDER_SOFT,
            highlightthickness=1,
        )
        table.pack(fill="x", pady=(12, 0))
        for col in range(len(step.headers)):
            table.grid_columnconfigure(col, weight=1, uniform="step-column")

        # 数字特别长时，把长数字按固定宽度换行，避免表格撑出卡片。
        chunked_rows = [
            tuple(self._wrap_long_number(value) for value in row)
            for row in step.rows
        ]
        # 注意：要在换行前判断原始长度，否则 compact 永远为 False（旧实现的 bug）。
        raw_longest = max(
            (len(value) for row in step.rows for value in row),
            default=0,
        )
        compact = raw_longest > 12
        cell_font = theme.mono(8) if compact else theme.mono(9)

        header_bg = theme.SURFACE_3
        for col, header in enumerate(step.headers):
            tk.Label(
                table,
                text=header,
                font=theme.font(8, "bold"),
                fg=theme.TEXT_DIM,
                bg=header_bg,
                padx=5,
                pady=5,
            ).grid(row=0, column=col, sticky="nsew")

        for row_index, row in enumerate(chunked_rows, start=1):
            is_final_division_row = (
                step.kind == "divide" and row_index == len(chunked_rows)
            )
            row_bg = theme.GREEN_DARK if is_final_division_row else (
                theme.SURFACE_2 if row_index % 2 else theme.BG_SOFT
            )
            row_fg = theme.GREEN if is_final_division_row else theme.TEXT
            for col, value in enumerate(row):
                font = (
                    theme.mono(8, "bold") if is_final_division_row and compact
                    else theme.mono(9, "bold") if is_final_division_row
                    else cell_font
                )
                tk.Label(
                    table,
                    text=value,
                    font=font,
                    fg=row_fg,
                    bg=row_bg,
                    padx=5,
                    pady=4,
                ).grid(row=row_index, column=col, sticky="nsew")

    def _render_text_table(self, body: tk.Misc, step: Step) -> None:
        """紧凑文本表格：几十到几百行时只创建一个 Text，渲染快且可滚动看全量数据。"""
        box = tk.Frame(
            body,
            bg=theme.SURFACE_2,
            highlightbackground=theme.BORDER_SOFT,
            highlightthickness=1,
        )
        box.pack(fill="x", pady=(12, 0))
        tk.Label(
            box,
            text=f"共 {len(step.rows)} 行 · 为保证流畅，使用可滚动的紧凑表格",
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.SURFACE_2,
            anchor="w",
        ).pack(fill="x", padx=9, pady=(6, 0))

        wrap = tk.Frame(box, bg=theme.SURFACE_2)
        wrap.pack(fill="x", padx=1, pady=(4, 1))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        text = tk.Text(
            wrap,
            height=min(18, len(step.rows) + 2),
            wrap="none",
            font=theme.mono(9),
            bg=theme.SURFACE_2,
            fg=theme.TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=8,
            pady=6,
            cursor="arrow",
        )
        y_scroll = ttk.Scrollbar(
            wrap, orient="vertical", command=text.yview, style="Dark.Vertical.TScrollbar"
        )
        x_scroll = ttk.Scrollbar(wrap, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        def cell(value: str) -> str:
            return value.replace("\n", " ")

        widths: list[int] = []
        for col, header in enumerate(step.headers):
            max_len = len(header)
            for row in step.rows:
                if col < len(row):
                    max_len = max(max_len, min(len(cell(row[col])), 32))
            widths.append(min(max_len, 32))

        def fmt(value: str, width: int) -> str:
            raw = cell(value)
            if len(raw) >= width:
                return raw  # 超长数值不截断，靠横向滚动条查看
            return raw.center(width)

        text.insert("end", "  ".join(fmt(h, w) for h, w in zip(step.headers, widths)) + "\n")
        text.tag_add("head", "1.0", "1.end")
        text.insert("end", "─" * min(160, sum(widths) + 2 * (len(widths) - 1)) + "\n")

        for index, row in enumerate(step.rows):
            line = "  ".join(fmt(value, width) for value, width in zip(row, widths))
            start = text.index("end-1c")
            text.insert("end", line + "\n")
            if step.kind == "divide" and index == len(step.rows) - 1:
                text.tag_add(
                    "final", start, f"{start} lineend"
                )
        text.tag_configure("head", foreground=theme.TEXT_DIM, font=theme.mono(9, "bold"))
        text.tag_configure(
            "final",
            foreground=theme.GREEN,
            background=theme.GREEN_DARK,
            font=theme.mono(9, "bold"),
        )
        text.configure(state="disabled")

