"""可复用的 Tkinter 小部件：圆角按钮、滚动区域、卡片标题等。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme


def _parent_bg(widget: tk.Misc) -> str:
    try:
        return widget.cget("bg")
    except tk.TclError:
        return theme.BG


def _rounded_points(x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


class RoundedButton(tk.Canvas):
    """Canvas 绘制的圆角按钮，支持悬停和键盘触发。"""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        fill: str = theme.ACCENT,
        hover_fill: str = theme.ACCENT_BRIGHT,
        text_color: str = "#06202E",
        height: int = 44,
        width: int | None = None,
        radius: int = 11,
        font: tuple | None = None,
        border: str | None = None,
        background: str | None = None,
        disabled: bool = False,
        cursor: str = "hand2",
    ) -> None:
        self._base_bg = background or _parent_bg(parent)
        super().__init__(
            parent,
            height=height,
            width=width or 1,
            bg=self._base_bg,
            highlightthickness=0,
            bd=0,
            cursor=cursor,
            takefocus=1 if not disabled else 0,
        )
        self._text = text
        self._command = command
        self._fill = fill
        self._hover_fill = hover_fill
        self._text_color = text_color
        self._radius = radius
        self._font = font or theme.font(10, "bold")
        self._border = border
        self._enabled = not disabled
        self._hovered = False
        self._focused = False
        self._shape_ids: list[int] = []
        self._text_id: int | None = None

        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", self._on_key)
        self.bind("<space>", self._on_key)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._on_blur)

    # ------------------------------------------------------------------ 绘制
    def _redraw(self, _event=None) -> None:
        self.delete("all")
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        if self._border:
            self._shape_ids.append(
                self.create_polygon(
                    *_rounded_points(0.5, 0.5, w - 0.5, h - 0.5, self._radius),
                    smooth=True,
                    splinesteps=24,
                    fill=self._border,
                    outline="",
                )
            )
            inset = 1.4
            fill = self._current_fill()
            self._shape_ids.append(
                self.create_polygon(
                    *_rounded_points(
                        inset, inset, w - inset, h - inset, max(2, self._radius - 1)
                    ),
                    smooth=True,
                    splinesteps=24,
                    fill=fill,
                    outline="",
                )
            )
        else:
            self._shape_ids.append(
                self.create_polygon(
                    *_rounded_points(1, 1, w - 1, h - 1, self._radius),
                    smooth=True,
                    splinesteps=24,
                    fill=self._current_fill(),
                    outline="",
                )
            )
        self._text_id = self.create_text(
            w / 2,
            h / 2 + 1,
            text=self._text,
            fill=self._text_color if self._enabled else theme.MUTED,
            font=self._font,
        )

    def _current_fill(self) -> str:
        if not self._enabled:
            return theme.SURFACE_3
        return self._hover_fill if self._hovered else self._fill

    def _refresh_fill(self) -> None:
        for item in self._shape_ids:
            self.itemconfigure(item, fill=self._current_fill())
        if self._text_id:
            self.itemconfigure(
                self._text_id,
                fill=self._text_color if self._enabled else theme.MUTED,
            )

    # ------------------------------------------------------------------ 事件
    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self._refresh_fill()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._refresh_fill()

    def _on_click(self, _event=None) -> None:
        if self._enabled:
            self.focus_set()

    def _on_release(self, _event=None) -> None:
        if self._enabled and self._command:
            self._command()

    def _on_key(self, _event=None) -> None:
        if self._enabled and self._command:
            self._command()
        return "break"

    def _on_focus(self, _event=None) -> None:
        self._focused = True

    def _on_blur(self, _event=None) -> None:
        self._focused = False

    # ------------------------------------------------------------------ 接口
    def set_text(self, text: str) -> None:
        self._text = text
        if self._text_id:
            self.itemconfigure(self._text_id, text=text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._refresh_fill()

    def set_colors(self, fill: str, hover_fill: str, text_color: str) -> None:
        self._fill = fill
        self._hover_fill = hover_fill
        self._text_color = text_color
        self._refresh_fill()


class ScrollableFrame(tk.Frame):
    """带垂直滚动条的容器。

    使用 .inner 作为子控件的父容器，.clear() 可清空内容。
    """

    def __init__(self, parent: tk.Misc, *, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar",
            troughcolor=bg,
            background=theme.SURFACE_3,
            bordercolor=bg,
            arrowcolor=theme.MUTED,
            darkcolor=theme.SURFACE_3,
            lightcolor=theme.SURFACE_3,
            width=8,
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[("active", theme.BORDER), ("pressed", theme.ACCENT)],
        )

        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            bd=0,
            yscrollincrement=24,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="Dark.Vertical.TScrollbar",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def contains_pointer(self, x_root: int, y_root: int) -> bool:
        widget = self.canvas.winfo_containing(x_root, y_root)
        while widget is not None:
            if widget is self.canvas:
                return True
            widget = widget.master
        return False

    def on_mousewheel(self, event) -> None:
        if event.delta:
            steps = -1 * int(event.delta / 120)
            self.canvas.yview_scroll(steps * 2, "units")


def divider(parent: tk.Misc, *, color: str = theme.BORDER_SOFT, pady: int = 0) -> tk.Frame:
    line = tk.Frame(parent, bg=color, height=1)
    line.pack(fill="x", pady=pady)
    return line
