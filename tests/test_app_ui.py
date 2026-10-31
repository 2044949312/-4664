"""界面交互的回归测试。

这些测试需要一个可用的图形显示环境；在无显示的 CI 环境会自动跳过。
覆盖问题：实时预览失效、Enter 重复转换、⇄ 使用过期结果、按钮焦点、
清空输入，以及超长输入的渲染性能。
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    TK_AVAILABLE = True
    TK_SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - 无显示环境
    TK_AVAILABLE = False
    TK_SKIP_REASON = f"没有可用的 Tk 图形环境：{exc}"


@unittest.skipUnless(TK_AVAILABLE, TK_SKIP_REASON)
class AppUiTests(unittest.TestCase):
    def setUp(self) -> None:
        from base_converter.app import BaseConverterApp

        self.app = BaseConverterApp()
        self.app.update()
        time.sleep(0.25)  # 等启动时 after(180, convert) 执行完
        self.app.update()
        self.app.minsize(1000, 640)

    def tearDown(self) -> None:
        self.app.destroy()

    def _set(self, text: str, source: int, target: int) -> None:
        self.app.number_var.set(text)
        self.app.source_picker.set_base(source)
        self.app.target_picker.set_base(target)

    def test_preview_invalid_input_shows_error_and_clears_result(self) -> None:
        self._set("1010", 2, 10)
        self.app.convert()
        self.app.update()
        self.assertEqual(self.app.result.result_text, "10")

        self.app.number_var.set("1012")
        self.app._preview()
        self.app.update()

        self.assertIn("不是 2 进制", self.app.error_var.get())
        self.assertIsNone(self.app.result)
        self.assertFalse(self.app.copy_button._enabled)

    def test_enter_converts_only_once(self) -> None:
        import base_converter.app as app_module
        from types import SimpleNamespace

        self._set("1010", 2, 10)
        self.app.convert()
        self.app.update()

        original = app_module.build_conversion
        calls: list[int] = []

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        app_module.build_conversion = counting
        try:
            self.app.number_var.set("1111")
            self.app.convert()
            self.app.update()
            self.assertEqual(len(calls), 1)

            # 模拟 Enter/F5 的 KeyRelease：不应再排一次 380ms 的预览。
            for keysym in ("Return", "KP_Enter", "F5"):
                self.app._schedule_preview(SimpleNamespace(keysym=keysym))
            time.sleep(0.55)
            self.app.update()
        finally:
            app_module.build_conversion = original

        self.assertEqual(len(calls), 1)
        self.assertNotIn("锁定", self.app.status_var.get())

    def test_swap_uses_current_input(self) -> None:
        self._set("255", 10, 2)
        self.app.convert()
        self.app.update()

        # 输入新数字后立刻点 ⇄（发生在预览防抖之前）。
        self.app.number_var.set("256")
        self.app._swap_bases()
        self.app.update()

        self.assertEqual(self.app.number_var.get(), "100000000")
        self.assertEqual(self.app.result.value, 256)
        self.assertEqual((self.app.source_picker.get_base(), self.app.target_picker.get_base()), (2, 10))

    def test_actions_return_focus_to_entry_and_copy_is_reachable(self) -> None:
        self._set("255", 10, 2)
        self.app.convert()
        self.app.update()
        self.assertEqual(str(self.app.focus_get()), str(self.app.entry))

        self.app._copy_result()
        self.app.update()
        self.assertEqual(str(self.app.focus_get()), str(self.app.entry))

        # 复制按钮在启用后应进入 Tab 顺序（takefocus=1）。
        self.assertEqual(str(self.app.copy_button.cget("takefocus")), "1")

    def test_clear_input_resets_state(self) -> None:
        self._set("255", 10, 2)
        self.app.convert()
        self.app.update()

        self.app._clear_input()
        self.app.update()

        self.assertEqual(self.app.number_var.get(), "")
        self.assertIsNone(self.app.result)
        self.assertFalse(self.app.copy_button._enabled)
        self.assertIn("已清空", self.app.status_var.get())

    def test_long_input_renders_quickly_and_truncates_display(self) -> None:
        self._set("Z" * 96, 36, 2)
        started = time.perf_counter()
        self.app.convert()
        self.app.update()
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5.0, f"96 位输入渲染耗时 {elapsed:.2f}s，疑似重新出现卡顿")
        self.assertIsNotNone(self.app.result)
        self.assertGreater(len(self.app.result.target_digits), 400)
        self.assertIn("…", self.app.result_var.get())
        self.assertLess(len(self.app.result_var.get()), 400)


if __name__ == "__main__":
    unittest.main()
