"""图形界面：把进制转换的计算过程变成可读、可演示的步骤卡片。"""

from __future__ import annotations

import re
import time
import tkinter as tk
from tkinter import ttk

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
from .widgets import RoundedButton, ScrollableFrame, _rounded_points, divider


class BaseConverterApp(tk.Tk):
    """进制转换演示器主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        # 统一不同缩放比例下的视觉大小：高 DPI 屏幕上最多放大到 1.5 倍，
        # 避免 1240×840 的窗口里文字过大、内容被挤出屏幕。
        try:
            natural_scaling = float(self.tk.call("tk", "scaling"))
            self.tk.call("tk", "scaling", min(max(natural_scaling, 1.333), 1.5))
        except (tk.TclError, ValueError):
            pass
        theme.resolve_fonts(self)

        self.title("进制转换演示器 · Base Conversion Explorer")
        self.configure(bg=theme.BG)
        self.minsize(1180, 840)
        self._center_window(1240, 880)
        self._set_window_icon()

        # 数据状态
        self._base_labels = [self._base_label(base) for base in range(MIN_BASE, MAX_BASE + 1)]
        self._base_by_label = {label: base for label, base in zip(self._base_labels, range(MIN_BASE, MAX_BASE + 1))}
        self.number_var = tk.StringVar(value="255")
        self.source_var = tk.StringVar(value=self._base_label(10))
        self.target_var = tk.StringVar(value=self._base_label(2))
        self.error_var = tk.StringVar(value="")
        self.expression_var = tk.StringVar(value="等待输入")
        self.result_var = tk.StringVar(value="—")
        self.meta_var = tk.StringVar(value="选择源进制与目标进制，再输入整数")
        self.status_var = tk.StringVar(value="就绪 · 输入数字后按 Enter 快速转换")
        self.step_count_var = tk.StringVar(value="0 步")

        self.result: ConversionResult | None = None
        self._preview_job: str | None = None
        self._toast_job: str | None = None
        self._last_elapsed_ms: float = 0.0

        self._configure_styles()
        self._build_ui()
        self._bind_shortcuts()

        # 首次打开时直接展示 255 → 二进制 的示例，方便课堂演示。
        self.after(180, self.convert)

    # ------------------------------------------------------------------ 基础
    def _center_window(self, width: int, height: int) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 24)
        self.geometry(f"{width}x{height}+{x}+{y}")

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

    def _base_label(self, base: int) -> str:
        return f"{base} · {base_name(base)}"

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=theme.SURFACE_2,
            background=theme.SURFACE_2,
            foreground=theme.TEXT,
            arrowcolor=theme.ACCENT,
            bordercolor=theme.BORDER,
            lightcolor=theme.SURFACE_2,
            darkcolor=theme.SURFACE_2,
            padding=(8, 7),
            arrowsize=13,
            font=theme.font(10),
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", theme.SURFACE_2), ("disabled", theme.SURFACE_2)],
            foreground=[("readonly", theme.TEXT), ("disabled", theme.MUTED)],
            selectbackground=[("readonly", theme.SURFACE_2)],
            selectforeground=[("readonly", theme.TEXT)],
            bordercolor=[("focus", theme.ACCENT)],
        )
        # 下拉列表（Listbox）的配色不能通过 ttk.Style 设置，需要用 option database。
        self.option_add("*TCombobox*Listbox.background", theme.SURFACE_2)
        self.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT_SOFT)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.ACCENT_BRIGHT)
        self.option_add("*TCombobox*Listbox.font", "Microsoft YaHei UI 10")

    def _bind_shortcuts(self) -> None:
        self.bind("<Return>", self.convert)
        self.bind("<F5>", self.convert)
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    # ------------------------------------------------------------------ 布局
    def _build_ui(self) -> None:
        self._build_header()
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 8))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=356)
        body.grid_columnconfigure(1, weight=1)

        input_panel = self._build_input_panel(body)
        input_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
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

        tk.Label(
            inner,
            text="待转换数字",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(fill="x", pady=(18, 7))

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
        self.entry.pack(fill="x", ipady=11)
        self.entry.bind("<KeyRelease>", self._schedule_preview)
        self.entry.bind("<Control-a>", self._select_all)

        self.error_label = tk.Label(
            inner,
            textvariable=self.error_var,
            font=theme.font(8),
            fg=theme.RED,
            bg=theme.SURFACE,
            anchor="nw",
            justify="left",
            height=2,
            wraplength=300,
        )
        self.error_label.pack(fill="x", pady=(5, 0))

        divider(inner, pady=(2, 14))

        selector = tk.Frame(inner, bg=theme.SURFACE)
        selector.pack(fill="x", pady=(0, 14))
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

        self.source_combo = ttk.Combobox(
            selector,
            textvariable=self.source_var,
            values=self._base_labels,
            state="readonly",
            style="Dark.TCombobox",
            font=theme.font(10),
            width=10,
        )
        self.source_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(6, 0))
        self.source_combo.bind("<<ComboboxSelected>>", self._on_base_changed)

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

        self.target_combo = ttk.Combobox(
            selector,
            textvariable=self.target_var,
            values=self._base_labels,
            state="readonly",
            style="Dark.TCombobox",
            font=theme.font(10),
            width=10,
        )
        self.target_combo.grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=(6, 0))
        self.target_combo.bind("<<ComboboxSelected>>", self._on_base_changed)

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
        self.convert_button.pack(fill="x", pady=(2, 16))

        divider(inner, pady=(0, 14))

        tk.Label(
            inner,
            text="快速示例",
            font=theme.font(9, "bold"),
            fg=theme.TEXT_DIM,
            bg=theme.SURFACE,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

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
                pady=(0, 7),
            )

        divider(inner, pady=(5, 12))

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
            pady=9,
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
        ).pack(anchor="w", pady=(5, 0))

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
            text="纯 Python 标准库 · Tkinter",
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
        if self.steps.contains_pointer(event.x_root, event.y_root):
            self.steps.on_mousewheel(event)
            return "break"
        return None

    def _on_base_changed(self, _event=None) -> None:
        self.convert()

    def _schedule_preview(self, event=None) -> None:
        if event is not None and event.keysym in {
            "Left", "Right", "Up", "Down", "Home", "End", "Tab", "Shift_L", "Shift_R",
            "Control_L", "Control_R", "Alt_L", "Alt_R", "Escape",
        }:
            return
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self._preview_job = self.after(380, self._preview)

    def _preview(self) -> None:
        self._preview_job = None
        try:
            source_base, target_base = self._selected_bases()
            result = build_conversion(self.number_var.get(), source_base, target_base)
        except ConversionError:
            return
        self._apply_result(result, silent=True)

    def _selected_bases(self) -> tuple[int, int]:
        source = self._base_by_label.get(self.source_var.get(), 10)
        target = self._base_by_label.get(self.target_var.get(), 2)
        return source, target

    def _set_bases(self, source_base: int, target_base: int) -> None:
        self.source_var.set(self._base_label(source_base))
        self.target_var.set(self._base_label(target_base))

    def _swap_bases(self) -> None:
        source, target = self._selected_bases()
        # 如果当前有有效结果，就把结果带回输入框，交换后正好完成一次“往返验证”。
        if self.result is not None:
            self.number_var.set(self.result.result_text)
        self._set_bases(target, source)
        self.convert()

    def _apply_example(self, text: str, source_base: int, target_base: int) -> None:
        self.number_var.set(text)
        self._set_bases(source_base, target_base)
        self.entry.icursor("end")
        self.entry.focus_set()
        self.convert()

    # ------------------------------------------------------------------ 转换
    def convert(self, _event=None) -> None:
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
            self._preview_job = None
        source_base, target_base = self._selected_bases()
        started = time.perf_counter()
        try:
            result = build_conversion(self.number_var.get(), source_base, target_base)
        except ConversionError as exc:
            self._show_error(exc.message)
            return
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._apply_result(result, elapsed_ms=elapsed_ms)

    def _apply_result(self, result: ConversionResult, elapsed_ms: float = 0.0, silent: bool = False) -> None:
        self.result = result
        self._last_elapsed_ms = elapsed_ms
        self.error_var.set("")
        self.entry.configure(highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT)
        self.expression_var.set(result.expression())
        self.result_var.set(result.result_text)
        self.result_label.configure(fg=theme.TEXT)
        self._fit_result_font(result.result_text)

        digit_count = len(result.target_digits.lstrip("-"))
        meta_parts = [f"十进制值 {result.decimal_text}", f"结果 {digit_count} 位", f"{len(result.steps)} 个步骤"]
        if result.is_negative:
            meta_parts.append("负数按绝对值演算，符号单独保留")
        self.meta_var.set("  ·  ".join(meta_parts))

        self.copy_button.set_enabled(True)
        self.step_count_var.set(f"共 {len(result.steps)} 步 · 详细演算")
        self._render_steps(result)
        self.steps.scroll_to_top()
        self.status_dot_canvas.itemconfigure(self.status_dot, fill=theme.GREEN)
        if not silent:
            self.status_var.set(f"转换完成  ·  {elapsed_ms:.2f} ms")
        else:
            self.status_var.set("已实时更新  ·  按 Enter 可锁定结果")

    def _fit_result_font(self, text: str) -> None:
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

    def _on_result_resize(self, event) -> None:
        wrap = max(280, event.width - 22)
        self.result_label.configure(wraplength=wrap)
        self.expression_label.configure(wraplength=wrap)
        self.meta_label.configure(wraplength=wrap)

    def _show_error(self, message: str) -> None:
        self.result = None
        self.error_var.set(message)
        self.entry.configure(highlightbackground=theme.RED, highlightcolor=theme.RED)
        self.expression_var.set("等待有效输入")
        self.result_var.set("—")
        self.result_label.configure(fg=theme.MUTED, font=theme.mono(31, "bold"))
        self.meta_var.set("修正左侧输入后重新转换")
        self.copy_button.set_enabled(False)
        self.step_count_var.set("0 步")
        self.steps.clear()
        self._render_message_card("暂时无法生成步骤", message, theme.RED, "!")
        self.status_dot_canvas.itemconfigure(self.status_dot, fill=theme.RED)
        self.status_var.set("输入有误  ·  请检查数字与源进制是否匹配")

    def _copy_result(self) -> None:
        if self.result is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self.result.result_text)
        self.copy_button.set_text("已复制 ✓")
        self.status_var.set(f"已复制结果：{self.result.result_text}")
        if self._toast_job is not None:
            try:
                self.after_cancel(self._toast_job)
            except tk.TclError:
                pass
        self._toast_job = self.after(1800, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._toast_job = None
        self.copy_button.set_text("复制结果")

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
            wraplength=640,
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
            longest = max(
                (len(line) for row in chunked_rows for cell in row for line in cell.split("\n")),
                default=0,
            )
            compact = longest > 12
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
