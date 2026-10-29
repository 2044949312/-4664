"""核心转换逻辑的单元测试。

运行方式（在项目根目录）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

# 允许直接运行 tests/test_converter.py，也允许从项目根目录运行 unittest。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_converter.converter import (  # noqa: E402
    ConversionError,
    build_conversion,
    int_to_base,
    parse_number,
)


class ParseNumberTests(unittest.TestCase):
    def test_common_bases(self):
        self.assertEqual(parse_number("255", 10)[0], 255)
        self.assertEqual(parse_number("FF", 16)[0], 255)
        self.assertEqual(parse_number("11111111", 2)[0], 255)
        self.assertEqual(parse_number("777", 8)[0], 511)

    def test_lowercase_and_spaces(self):
        self.assertEqual(parse_number("  ff  ", 16)[0], 255)
        self.assertEqual(parse_number("1010 1010", 2)[0], 170)
        self.assertEqual(parse_number("FF_FF", 16)[0], 65535)

    def test_negative_and_positive_sign(self):
        self.assertEqual(parse_number("-1010", 2)[0], -10)
        self.assertEqual(parse_number("+1010", 2)[0], 10)
        self.assertEqual(parse_number("-0", 10)[0], 0)

    def test_prefixes_are_accepted(self):
        self.assertEqual(parse_number("0b1010", 2)[0], 10)
        self.assertEqual(parse_number("0o17", 8)[0], 15)
        self.assertEqual(parse_number("0x1F", 16)[0], 31)

    def test_leading_zeros_are_removed(self):
        value, normalized, digits = parse_number("000FF", 16)
        self.assertEqual(value, 255)
        self.assertEqual(normalized, "FF")
        self.assertEqual(digits, "FF")

    def test_base_36(self):
        self.assertEqual(parse_number("HELLO", 36)[0], 29234652)

    def test_invalid_digit_message(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("2", 2)
        self.assertIn("不是 2 进制", ctx.exception.message)
        self.assertIn("0–1", ctx.exception.message)

    def test_empty_input(self):
        for text in ("", "   ", "+", "-", "0x"):
            with self.subTest(text=text):
                with self.assertRaises(ConversionError):
                    parse_number(text, 16)

    def test_invalid_base(self):
        for base in (1, 37, 0, -2):
            with self.subTest(base=base):
                with self.assertRaises(ConversionError):
                    parse_number("10", base)

    def test_too_long(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("1" * 97, 2)
        self.assertIn("过长", ctx.exception.message)


class IntToBaseTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(int_to_base(255, 2), "11111111")
        self.assertEqual(int_to_base(255, 16), "FF")
        self.assertEqual(int_to_base(255, 8), "377")
        self.assertEqual(int_to_base(0, 2), "0")
        self.assertEqual(int_to_base(35, 36), "Z")
        self.assertEqual(int_to_base(-255, 16), "-FF")

    def test_large_value(self):
        value = 2**100 + 12345
        self.assertEqual(int_to_base(value, 2), bin(value)[2:].upper())
        self.assertEqual(int_to_base(value, 16), format(value, "X"))


class BuildConversionTests(unittest.TestCase):
    def test_decimal_to_binary(self):
        result = build_conversion("255", 10, 2)
        self.assertEqual(result.result_text, "11111111")
        self.assertEqual(result.value, 255)
        self.assertEqual(len(result.steps), 1)
        step = result.steps[0]
        self.assertEqual(step.kind, "divide")
        self.assertEqual(len(step.rows), 8)
        self.assertEqual(step.rows[0][1], "255")
        self.assertEqual(step.rows[-1][3], "0")  # 最后一轮的商为 0
        self.assertIn("11111111", step.footer)

    def test_hex_to_decimal_expands_by_weight(self):
        result = build_conversion("FF", 16, 10)
        self.assertEqual(result.result_text, "255")
        self.assertEqual(len(result.steps), 1)
        step = result.steps[0]
        self.assertEqual(step.kind, "expand")
        self.assertEqual(step.rows, (("1", "F", "15", "16^1", "16", "240"), ("0", "F", "15", "16^0", "1", "15")))
        self.assertIn("240 + 15 = 255", step.footer)

    def test_hex_to_binary_uses_two_methods(self):
        result = build_conversion("FF", 16, 2)
        self.assertEqual(result.result_text, "11111111")
        self.assertEqual([step.kind for step in result.steps], ["info", "expand", "divide"])
        self.assertIn("先转十进制", result.steps[0].title)

    def test_same_base(self):
        result = build_conversion("00ff", 16, 16)
        self.assertEqual(result.result_text, "FF")
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].kind, "info")
        self.assertIn("无需换算", result.steps[0].kicker)

    def test_negative_round_trip(self):
        result = build_conversion("-255", 10, 16)
        self.assertEqual(result.result_text, "-FF")
        self.assertEqual(result.value, -255)
        self.assertEqual(result.steps[0].rows[0][1], "255")  # 绝对值参与竖式

    def test_zero(self):
        result = build_conversion("0", 10, 16)
        self.assertEqual(result.result_text, "0")
        self.assertEqual(result.steps[0].rows[0][-1], "0")

    def test_expression(self):
        result = build_conversion("FF", 16, 2)
        self.assertIn("(FF)₁₆", result.expression())
        self.assertIn("(11111111)₂", result.expression())

    def test_random_round_trip(self):
        rng = random.Random(20261029)
        for _ in range(100):
            base = rng.randint(2, 36)
            value = rng.randint(0, 10**12)
            text = int_to_base(value, base)
            result = build_conversion(text, base, 10)
            self.assertEqual(result.value, value, msg=f"{text} (base {base})")
            back = build_conversion(str(value), 10, base)
            self.assertEqual(back.result_text, text)

    def test_base_36_case_insensitive(self):
        result = build_conversion("hello", 36, 10)
        self.assertEqual(result.value, 29234652)
        self.assertEqual(build_conversion("HELLO", 36, 36).result_text, "HELLO")


if __name__ == "__main__":
    unittest.main()
