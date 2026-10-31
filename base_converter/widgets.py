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
        self._cursor = cursor
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
        # 重建所有图形项，避免 _shape_ids 无限累积旧 item id。
        self._shape_ids = []
        self._text_id = None
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
        if self._focused and self._enabled:
            # 键盘焦点环：仅在可获得焦点且启用时绘制。
            self.create_polygon(
                *_rounded_points(1.5, 1.5, w - 1.5, h - 1.5, max(2, self._radius - 1)),
                smooth=True,
                splinesteps=24,
                fill="",
                outline=theme.ACCENT_BRIGHT,
                width=2,
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
        self._redraw()

    def _on_blur(self, _event=None) -> None:
        self._focused = False
        self._redraw()

    # ------------------------------------------------------------------ 接口
    def set_text(self, text: str) -> None:
        self._text = text
        if self._text_id:
            self.itemconfigure(self._text_id, text=text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(takefocus=1 if self._enabled else 0)
        self.configure(cursor=self._cursor if self._enabled else "arrow")
        self._refresh_fill()
        # 禁用时移除焦点环；重新启用且仍持有焦点时恢复焦点环。
        if self._focused:
            self._redraw()

    def set_colors(self, fill: str, hover_fill: str, text_color: str) -> None:
        self._fill = fill
        self._hover_fill = hover_fill
        self._text_color = text_color
        self._refresh_fill()


class BasePickerButton(RoundedButton):
    """显示当前进制的按钮，点击后弹出一个 2–36 进制的选择面板。"""

    # 所有存活的实例，用于在某个弹窗持有 grab 时把点击转发给另一个选择器。
    _instances: list["BasePickerButton"] = []

    def __init__(
        self,
        parent: tk.Misc,
        *,
        base: int,
        options: list[tuple[int, str]],
        on_select,
        title: str,
        height: int = 38,
    ) -> None:
        self._base = base
        self._base_choices = list(options)
        self._on_select = on_select
        self._title = title
        self._popup: tk.Toplevel | None = None
        self._name_by_base = {value: name for value, name in self._base_choices}
        super().__init__(
            parent,
            text=self._button_text(),
            command=self._toggle_popup,
            fill=theme.SURFACE_2,
            hover_fill=theme.SURFACE_3,
            text_color=theme.TEXT,
            height=height,
            radius=9,
            font=theme.font(10),
            border=theme.BORDER_SOFT,
        )
        if self not in BasePickerButton._instances:
            BasePickerButton._instances.append(self)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _button_text(self) -> str:
        return f"{self._base} · {self._name_by_base.get(self._base, '')}   ▾"

    # -------------------------------------------------------------- 实例登记
    def _on_destroy(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self:
            return
        try:
            BasePickerButton._instances.remove(self)
        except ValueError:
            pass
        self._popup = None

    @classmethod
    def _live_instances(cls) -> list["BasePickerButton"]:
        alive: list[BasePickerButton] = []
        for picker in list(cls._instances):
            try:
                if picker.winfo_exists():
                    alive.append(picker)
            except tk.TclError:
                pass
        return alive

    def _contains_screen_point(self, x_root: int, y_root: int) -> bool:
        """判断屏幕坐标是否落在本按钮的可见区域内。"""
        try:
            if not self.winfo_ismapped():
                return False
            x = self.winfo_rootx()
            y = self.winfo_rooty()
            width = self.winfo_width()
            height = self.winfo_height()
        except tk.TclError:
            return False
        return x <= x_root < x + width and y <= y_root < y + height

    def get_base(self) -> int:
        return self._base

    def set_base(self, base: int) -> None:
        if base == self._base:
            return
        self._base = base
        self.set_text(self._button_text())
        if self._popup is not None:
            self._close_popup()

    def _toggle_popup(self) -> None:
        if self._popup is not None:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self) -> None:
        self._close_popup()
        self.update_idletasks()

        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        self._popup = popup

        outer = tk.Frame(popup, bg=theme.BORDER)
        outer.pack(fill="both", expand=True)
        panel = tk.Frame(outer, bg=theme.SURFACE, padx=12, pady=10)
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        header = tk.Frame(panel, bg=theme.SURFACE)
        header.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text=self._title,
            font=theme.font(10, "bold"),
            fg=theme.TEXT,
            bg=theme.SURFACE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="2–36 进制",
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(8, 6))
        tk.Button(
            header,
            text="✕",
            command=self._close_popup,
            font=theme.font(9, "bold"),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            activebackground=theme.SURFACE_2,
            activeforeground=theme.RED,
            relief="flat",
            bd=0,
            padx=4,
            pady=0,
            cursor="hand2",
            highlightthickness=0,
        ).grid(row=0, column=2, sticky="e")

        body = tk.Frame(panel, bg=theme.SURFACE)
        body.grid(row=1, column=0, columnspan=5, sticky="nsew")
        for col in range(5):
            body.grid_columnconfigure(col, weight=1, uniform="base-option")
        for index, (value, name) in enumerate(self._base_choices):
            row, col = divmod(index, 5)
            selected = value == self._base
            common = value in (2, 8, 10, 16)
            if name.startswith(f"{value} "):
                option_text = name
            else:
                option_text = f"{value:>2}  {name}"
            button = tk.Button(
                body,
                text=option_text,
                command=lambda chosen=value: self._choose(chosen),
                font=theme.font(9, "bold" if selected else "normal"),
                fg=theme.ACCENT_BRIGHT if selected else (theme.ACCENT if common else theme.TEXT),
                bg=theme.ACCENT_SOFT if selected else theme.SURFACE_2,
                activebackground=theme.ACCENT_DARK,
                activeforeground=theme.ACCENT_BRIGHT,
                relief="flat",
                bd=0,
                padx=7,
                pady=6,
                anchor="w",
                cursor="hand2",
                highlightthickness=0,
            )
            button.grid(row=row, column=col, sticky="ew", padx=2, pady=2)

        tk.Label(
            panel,
            text="点击任意进制切换 · Esc 关闭",
            font=theme.font(8),
            fg=theme.MUTED,
            bg=theme.SURFACE,
            anchor="w",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(7, 0))

        popup.update_idletasks()
        width = max(popup.winfo_reqwidth(), 540)
        height = popup.winfo_reqheight()
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 6
        if x + width > screen_w - 8:
            x = max(8, screen_w - width - 8)
        if y + height > screen_h - 8:
            y = max(8, self.winfo_rooty() - height - 6)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        popup.focus_set()
        popup.grab_set()

        popup.bind("<Escape>", self._on_popup_escape)
        popup.bind("<Button-1>", self._on_popup_click)
        popup.bind("<FocusOut>", self._on_popup_focus_out)
        popup.bind("<Return>", self._on_popup_confirm)
        popup.bind("<KP_Enter>", self._on_popup_confirm)
        popup.bind("<F5>", self._on_popup_confirm)

    def _on_popup_click(self, event):
        popup = self._popup
        if popup is None:
            return None
        widget = getattr(event, "widget", None)
        x_root = getattr(event, "x_root", None)
        y_root = getattr(event, "y_root", None)
        if widget is popup and x_root is not None and y_root is not None:
            # 弹窗持有 grab 时，点击另一个选择器按钮会被吞掉；
            # 这里直接把点击转交给那个按钮，实现一次点击完成切换。
            for other in BasePickerButton._live_instances():
                if other is self:
                    continue
                if other._contains_screen_point(x_root, y_root):
                    self._close_popup()
                    other._open_popup()
                    return "break"
        if widget is popup:
            width = popup.winfo_width()
            height = popup.winfo_height()
            x = getattr(event, "x", None)
            y = getattr(event, "y", None)
            if x is not None and y is not None and not (0 <= x < width and 0 <= y < height):
                self._close_popup()
        return None

    def _on_popup_escape(self, _event=None):
        self._close_popup(focus_back=True)
        return "break"

    def _on_popup_confirm(self, _event=None):
        """Return / KP_Enter / F5：关闭弹窗后触发一次选择回调。"""
        if self._popup is None:
            return "break"
        self._close_popup(focus_back=True)
        if self._on_select is not None:
            self._on_select()
        return "break"

    def _on_popup_focus_out(self, event) -> None:
        popup = self._popup
        if popup is None or event.widget is not popup:
            return
        popup.after(30, self._close_if_focus_left)

    def _close_if_focus_left(self) -> None:
        popup = self._popup
        if popup is None:
            return
        focus = popup.focus_get()
        if focus is None or not str(focus).startswith(str(popup)):
            self._close_popup()

    def _choose(self, base: int) -> None:
        self._close_popup()
        self.set_base(base)
        self.focus_set()
        self._on_select()

    def _close_popup(self, focus_back: bool = False) -> None:
        popup = self._popup
        if popup is None:
            return
        self._popup = None
        try:
            popup.grab_release()
        except tk.TclError:
            pass
        try:
            popup.destroy()
        except tk.TclError:
            pass
        if focus_back:
            try:
                self.focus_set()
            except tk.TclError:
                pass


class ScrollableFrame(tk.Frame):
    """带垂直滚动条的容器。

    使用 .inner 作为子控件的父容器，.clear() 可清空内容。
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg: str = theme.BG,
        autohide_scrollbar: bool = False,
    ) -> None:
        super().__init__(parent, bg=bg)
        self._autohide_scrollbar = bool(autohide_scrollbar)
        self._scrollbar_shown = True
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
        self._update_scrollbar_visibility()

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self) -> None:
        """自动隐藏模式下：内容适配时隐藏滚动条，否则显示。"""
        if not self._autohide_scrollbar:
            if not self._scrollbar_shown:
                self.scrollbar.grid()
                self._scrollbar_shown = True
            return
        bbox = self.canvas.bbox("all")
        content_height = (bbox[3] - bbox[1]) if bbox else 0
        try:
            canvas_height = self.canvas.winfo_height()
        except tk.TclError:
            canvas_height = 0
        should_show = content_height > canvas_height + 1
        if should_show == self._scrollbar_shown:
            return
        if should_show:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()
        self._scrollbar_shown = should_show

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)
        # Tk 在子控件销毁后不会主动刷新 Frame 的请求尺寸（残留旧高度），
        # 通过重新设置宽度强制触发一次尺寸重算，滚动条自动隐藏才能生效。
        self._resync_inner_size()

    def _resync_inner_size(self) -> None:
        try:
            self.inner.configure(width=max(1, self.canvas.winfo_width()))
        except tk.TclError:
            pass
        self._update_scrollbar_visibility()

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
        """跨平台滚轮处理：Windows/macOS 用 delta，Linux 用 Button-4/5 的 num。"""
        num = getattr(event, "num", None)
        if num in (4, 5):
            steps = -1 if num == 4 else 1
        else:
            delta = getattr(event, "delta", 0)
            try:
                delta_value = float(delta)
            except (TypeError, ValueError):
                delta_value = 0.0
            if delta_value == 0:
                return
            # 非 120 整数倍的 delta 也至少滚动一步，避免 int(delta/120) == 0 时无响应。
            magnitude = max(1, int(abs(delta_value) / 120))
            steps = -magnitude if delta_value > 0 else magnitude
        self.canvas.yview_scroll(steps * 2, "units")


def divider(parent: tk.Misc, *, color: str = theme.BORDER_SOFT, pady: int = 0) -> tk.Frame:
    line = tk.Frame(parent, bg=color, height=1)
    line.pack(fill="x", pady=pady)
    return line
