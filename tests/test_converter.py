"""核心转换逻辑的单元测试。

运行方式（在项目根目录）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import unicodedata
import unittest
from pathlib import Path

# 允许直接运行 tests/test_converter.py，也允许从项目根目录运行 unittest。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_converter.converter import (  # noqa: E402
    BASE_NAMES,
    DIGITS,
    MAX_BASE,
    MAX_INPUT_DIGITS,
    MIN_BASE,
    ConversionError,
    allowed_digits_hint,
    base_name,
    build_conversion,
    build_quick_examples,
    int_to_base,
    parse_number,
    validate_base,
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


class UnicodeNormalizationTests(unittest.TestCase):
    """P2-1：全角数字、字母、空格、正负号都要能当作 ASCII 处理。"""

    def test_fullwidth_digits(self):
        self.assertEqual(parse_number("２５５", 10)[0], 255)
        result = build_conversion("２５５", 10, 2)
        self.assertEqual(result.result_text, "11111111")
        self.assertEqual(result.normalized, "255")

    def test_fullwidth_prefix_and_letters(self):
        self.assertEqual(parse_number("０ｘ１Ｆ", 16)[0], 31)
        self.assertEqual(parse_number("０Ｘ１Ｆ", 16)[0], 31)
        self.assertEqual(parse_number("０ｂ１０１０", 2)[0], 10)
        self.assertEqual(parse_number("０ｏ１７", 8)[0], 15)
        self.assertEqual(build_conversion("０ｘ１Ｆ", 16, 10).result_text, "31")

    def test_fullwidth_spaces(self):
        self.assertEqual(parse_number("１０１０　１０１０", 2)[0], 170)
        self.assertEqual(parse_number("　２５５　", 10)[0], 255)

    def test_fullwidth_signs(self):
        self.assertEqual(parse_number("－１０１０", 2)[0], -10)
        self.assertEqual(parse_number("＋１０１０", 2)[0], 10)

    def test_nfkc_reference(self):
        self.assertEqual(unicodedata.normalize("NFKC", "２５５"), "255")
        self.assertEqual(unicodedata.normalize("NFKC", "　"), " ")


class PrefixMismatchTests(unittest.TestCase):
    """P0-4：前缀与源进制不匹配时要给出明确的中文错误。"""

    def test_hex_prefix_on_decimal(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("0x1F", 10)
        message = ctx.exception.message
        self.assertIn("检测到 0x 前缀", message)
        self.assertIn("十六进制", message)
        self.assertIn("当前源进制是 十进制", message)
        self.assertIn("请把源进制改为 16", message)
        self.assertIn("去掉前缀", message)

    def test_binary_prefix_on_octal(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("0b1010", 8)
        message = ctx.exception.message
        self.assertIn("检测到 0b 前缀", message)
        self.assertIn("二进制", message)
        self.assertIn("八进制", message)
        self.assertIn("请把源进制改为 2", message)

    def test_octal_prefix_on_binary(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("0o17", 2)
        message = ctx.exception.message
        self.assertIn("检测到 0o 前缀", message)
        self.assertIn("八进制", message)
        self.assertIn("二进制", message)
        self.assertIn("请把源进制改为 8", message)

    def test_case_insensitive_detection(self):
        for text in ("0X1F", "0x1F", "0X1f", "0x1f"):
            with self.subTest(text=text):
                with self.assertRaises(ConversionError) as ctx:
                    parse_number(text, 10)
                self.assertIn("0x", ctx.exception.message)

    def test_fullwidth_prefix_mismatch(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("０ｘ１Ｆ", 10)
        self.assertIn("0x", ctx.exception.message)
        self.assertIn("十六进制", ctx.exception.message)

    def test_prefix_after_negative_sign(self):
        self.assertEqual(parse_number("-0x1F", 16)[0], -31)
        with self.assertRaises(ConversionError) as ctx:
            parse_number("-0x1F", 10)
        self.assertIn("请把源进制改为 16", ctx.exception.message)
        with self.assertRaises(ConversionError) as ctx:
            parse_number("-0xGG", 16)
        self.assertIn("位置：第 4 位", ctx.exception.message)

    def test_matching_prefix_still_strips(self):
        self.assertEqual(parse_number("0B1010", 2)[0], 10)
        self.assertEqual(parse_number("0o17", 8)[0], 15)
        self.assertEqual(parse_number("0X1F", 16)[0], 31)

    def test_build_conversion_raises_on_mismatch(self):
        with self.assertRaises(ConversionError):
            build_conversion("0x1F", 10, 2)
        with self.assertRaises(ConversionError):
            build_conversion("0b1010", 16, 2)


class DecimalRejectionTests(unittest.TestCase):
    """P1-6：只演示整数，出现小数要明确报错。"""

    DECIMAL_MESSAGE = "当前版本只演示整数，不支持小数部分（例如 3.14）。"

    def test_ascii_dot(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("3.14", 10)
        self.assertEqual(ctx.exception.message, self.DECIMAL_MESSAGE)

    def test_chinese_marks(self):
        for text in ("3。14", "3·14"):
            with self.subTest(text=text):
                with self.assertRaises(ConversionError) as ctx:
                    parse_number(text, 10)
                self.assertEqual(ctx.exception.message, self.DECIMAL_MESSAGE)

    def test_fullwidth_dot_normalized(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("３．１４", 10)
        self.assertEqual(ctx.exception.message, self.DECIMAL_MESSAGE)

    def test_other_bases_also_reject_decimals(self):
        for text, base in (("F.F", 16), ("1.0", 2), ("7.7", 8)):
            with self.subTest(text=text, base=base):
                with self.assertRaises(ConversionError) as ctx:
                    parse_number(text, base)
                self.assertIn("只演示整数", ctx.exception.message)

    def test_build_conversion_also_rejects(self):
        with self.assertRaises(ConversionError):
            build_conversion("1.5", 10, 2)


class ErrorPositionTests(unittest.TestCase):
    """P1-7：错误位置按 NFKC 之后、清洗之前的原始文本位置（1 基）报告。"""

    def assert_position(self, text, base, position):
        with self.assertRaises(ConversionError) as ctx:
            parse_number(text, base)
        self.assertIn(f"位置：第 {position} 位", ctx.exception.message)

    def test_position_with_space(self):
        self.assert_position("1010 1012", 2, 9)

    def test_position_with_prefix(self):
        self.assert_position("0xGG", 16, 3)

    def test_position_with_sign(self):
        self.assert_position("-1012", 2, 5)

    def test_position_with_underscores(self):
        self.assert_position("FF_FF_G", 16, 7)

    def test_position_with_fullwidth_digits(self):
        self.assert_position("２５５Ｇ", 16, 4)

    def test_message_keeps_position_wording(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("1012", 2)
        self.assertIn("位置：第 4 位。", ctx.exception.message)


class NegativeStepTests(unittest.TestCase):
    """P1-4：讲解步骤要显式说明负数按绝对值计算、结果补回负号。"""

    def test_same_base_formula_uses_signed_text(self):
        result = build_conversion("-FF", 16, 16)
        self.assertEqual(result.result_text, "-FF")
        step = result.steps[0]
        self.assertEqual(
            step.formula, "(-FF)₁₆ = (-FF)₁₆"
        )
        self.assertIn("负号", step.description)
        self.assertIn("保留", step.description)

    def test_expansion_negative_uses_absolute_value(self):
        result = build_conversion("-FF", 16, 10)
        self.assertEqual(result.result_text, "-255")
        step = result.steps[0]
        self.assertEqual(step.kind, "expand")
        self.assertIn("绝对值", step.title)
        self.assertIn("绝对值", step.description)
        self.assertIn("负号", step.description)
        self.assertIn("绝对值", step.formula)
        self.assertNotIn("(-FF)₁₆", step.formula)  # 公式展示的是绝对值
        self.assertIn("255", step.formula)
        self.assertIn("-255", step.footer)
        self.assertEqual(step.rows[0][1], "F")  # 数码逐位展示，不带负号

    def test_division_negative_uses_absolute_value(self):
        result = build_conversion("-255", 10, 16)
        self.assertEqual(result.result_text, "-FF")
        step = result.steps[0]
        self.assertEqual(step.kind, "divide")
        self.assertIn("绝对值", step.title)
        self.assertIn("绝对值", step.description)
        self.assertIn("负号", step.description)
        self.assertIn("绝对值", step.formula)
        self.assertIn("-FF", step.formula)
        self.assertEqual(step.rows[0][1], "255")  # 竖式使用绝对值

    def test_route_mentions_sign_handling(self):
        result = build_conversion("-FF", 16, 2)
        route = result.steps[0]
        self.assertEqual(route.kind, "info")
        self.assertIn("负号", route.description)
        self.assertIn("绝对值", route.description)

    def test_negative_binary_to_hex_steps(self):
        result = build_conversion("-1010", 2, 16)
        self.assertEqual(result.result_text, "-A")
        expand, divide = result.steps[1], result.steps[2]
        self.assertIn("绝对值", expand.formula)
        self.assertIn("10", expand.formula)
        self.assertIn("-A", divide.formula)
        self.assertIn("负号", divide.description)

    def test_positive_steps_do_not_talk_about_negative(self):
        result = build_conversion("FF", 16, 2)
        for step in result.steps:
            self.assertNotIn("负号", step.description)
            self.assertNotIn("补回", step.description)

    def test_negative_same_base_expression_keeps_sign(self):
        result = build_conversion("-FF", 16, 16)
        self.assertIn("(-FF)₁₆", result.expression())


class BaseNameTests(unittest.TestCase):
    """P2-13：2–36 进制都要有完整的中文名称。"""

    EXPECTED = {
        2: "二进制",
        3: "三进制",
        4: "四进制",
        5: "五进制",
        6: "六进制",
        7: "七进制",
        8: "八进制",
        9: "九进制",
        10: "十进制",
        11: "十一进制",
        12: "十二进制",
        13: "十三进制",
        14: "十四进制",
        15: "十五进制",
        16: "十六进制",
        17: "十七进制",
        18: "十八进制",
        19: "十九进制",
        20: "二十进制",
        21: "二十一进制",
        22: "二十二进制",
        23: "二十三进制",
        24: "二十四进制",
        25: "二十五进制",
        26: "二十六进制",
        27: "二十七进制",
        28: "二十八进制",
        29: "二十九进制",
        30: "三十进制",
        31: "三十一进制",
        32: "三十二进制",
        33: "三十三进制",
        34: "三十四进制",
        35: "三十五进制",
        36: "三十六进制",
    }

    def test_all_bases_covered(self):
        self.assertEqual(sorted(BASE_NAMES), list(range(MIN_BASE, MAX_BASE + 1)))
        for base in range(MIN_BASE, MAX_BASE + 1):
            self.assertEqual(BASE_NAMES[base], self.EXPECTED[base], msg=f"base {base}")

    def test_base_name_function(self):
        self.assertEqual(base_name(17), "十七进制")
        self.assertEqual(base_name(20), "二十进制")
        self.assertEqual(base_name(30), "三十进制")
        self.assertEqual(base_name(32), "三十二进制")
        self.assertEqual(base_name(36), "三十六进制")
        for base in range(MIN_BASE, MAX_BASE + 1):
            self.assertTrue(base_name(base).endswith("进制"))

    def test_names_are_unique(self):
        self.assertEqual(len(set(BASE_NAMES.values())), len(BASE_NAMES))

    def test_result_base_names(self):
        result = build_conversion("FF", 16, 17)
        self.assertEqual(result.source_name, "十六进制")
        self.assertEqual(result.target_name, "十七进制")


class RouteTextTests(unittest.TestCase):
    """D13：转换路线文案不能声称“没有直接的逐位换算规则”。"""

    def test_no_false_claim(self):
        for source, target in ((16, 2), (3, 7), (2, 36), (4, 8)):
            with self.subTest(source=source, target=target):
                route = build_conversion("10", source, target).steps[0]
                self.assertNotIn("没有直接的逐位换算规则", route.description)

    def test_power_of_two_mentions_grouping_shortcut(self):
        route = build_conversion("FF", 16, 2).steps[0]
        self.assertIn("2 的幂", route.description)
        self.assertIn("分组", route.description)
        self.assertIn("3 位", route.description)
        self.assertIn("4 位", route.description)
        self.assertIn("5 位", route.description)
        self.assertIn("十进制", route.description)

    def test_both_power_of_two_mentions_grouping(self):
        route = build_conversion("10", 4, 8).steps[0]
        self.assertIn("2 的幂", route.description)
        self.assertIn("分组", route.description)

    def test_non_power_of_two_uses_decimal_route(self):
        route = build_conversion("12", 3, 7).steps[0]
        self.assertIn("统一使用十进制中转路线", route.description)
        self.assertNotIn("2 的幂", route.description)

    def test_route_title_still_says_decimal_first(self):
        route = build_conversion("FF", 16, 2).steps[0]
        self.assertIn("先转十进制", route.title)


class BoundaryTests(unittest.TestCase):
    """位数上限：96 位可用，97 位报错；MAX_INPUT_DIGITS 保持 96。"""

    def test_max_input_digits_constant(self):
        self.assertEqual(MAX_INPUT_DIGITS, 96)

    def test_96_digits_accepted(self):
        text = "1" * 96
        value, normalized, digits = parse_number(text, 2)
        self.assertEqual(value, 2**96 - 1)
        self.assertEqual(len(digits), 96)
        self.assertEqual(normalized, text)
        result = build_conversion(text, 2, 36)
        self.assertEqual(result.result_text, int_to_base(2**96 - 1, 36))

    def test_97_digits_rejected(self):
        with self.assertRaises(ConversionError) as ctx:
            parse_number("1" * 97, 2)
        self.assertIn("过长", ctx.exception.message)
        self.assertIn("96", ctx.exception.message)

    def test_boundary_with_prefix(self):
        self.assertEqual(parse_number("0b" + "1" * 96, 2)[0], 2**96 - 1)
        with self.assertRaises(ConversionError):
            parse_number("0b" + "1" * 97, 2)


class RandomNonDecimalRoundTripTests(unittest.TestCase):
    def test_random_non_decimal_to_non_decimal_round_trip(self):
        """50 组随机的非十进制 → 非十进制往返转换。"""
        rng = random.Random(20261031)
        for index in range(50):
            source_base = rng.randint(MIN_BASE, MAX_BASE)
            target_base = rng.randint(MIN_BASE, MAX_BASE)
            while target_base == source_base:
                target_base = rng.randint(MIN_BASE, MAX_BASE)
            value = rng.randint(-(10**12), 10**12)
            text = int_to_base(value, source_base)
            result = build_conversion(text, source_base, target_base)
            message = (
                f"case {index}: ({text}) base {source_base} -> base {target_base}"
            )
            self.assertEqual(result.value, value, message)
            self.assertEqual(result.result_text, int_to_base(value, target_base), message)
            back = build_conversion(result.result_text, target_base, source_base)
            self.assertEqual(back.result_text, text, message)


class LazyImportTests(unittest.TestCase):
    """P2-12：base_converter/__init__.py 不能急切导入 tkinter。"""

    def run_python(self, code: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    def test_import_converter_without_tkinter(self):
        code = (
            "import sys\n"
            "sys.modules['tkinter'] = None\n"
            "import base_converter.converter as c\n"
            "print(c.MAX_INPUT_DIGITS)\n"
            "print(c.parse_number('ff', 16)[0])\n"
        )
        proc = self.run_python(code)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(proc.stdout.split(), ["96", "255"])

    def test_package_import_does_not_load_tkinter(self):
        code = (
            "import sys\n"
            "sys.modules['tkinter'] = None\n"
            "import base_converter\n"
            "assert sys.modules.get('tkinter') is None\n"
            "print('ok')\n"
        )
        proc = self.run_python(code)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ok")

    def test_unknown_package_attribute_raises_attribute_error(self):
        import base_converter

        with self.assertRaises(AttributeError):
            base_converter.NotAnAttribute


class PublicApiTests(unittest.TestCase):
    def test_constants_unchanged(self):
        self.assertEqual(MIN_BASE, 2)
        self.assertEqual(MAX_BASE, 36)
        self.assertEqual(MAX_INPUT_DIGITS, 96)
        self.assertEqual(len(DIGITS), 36)
        self.assertEqual(DIGITS[:10], "0123456789")
        self.assertEqual(DIGITS[35], "Z")

    def test_validate_base(self):
        for base in range(MIN_BASE, MAX_BASE + 1):
            validate_base(base)
        for base in (0, 1, 37, -2, True, "16"):
            with self.subTest(base=base):
                with self.assertRaises(ConversionError):
                    validate_base(base)

    def test_allowed_digits_hint(self):
        self.assertEqual(allowed_digits_hint(2), "0–1")
        self.assertEqual(allowed_digits_hint(10), "0–9")
        self.assertEqual(allowed_digits_hint(16), "0–9、A–F")
        self.assertEqual(allowed_digits_hint(36), "0–9、A–Z")

    def test_build_quick_examples(self):
        examples = list(build_quick_examples())
        self.assertEqual(len(examples), 4)
        for label, text, source, target in examples:
            self.assertIsInstance(label, str)
            self.assertEqual(build_conversion(text, source, target).raw, text)

    def test_public_result_fields(self):
        result = build_conversion("FF", 16, 2)
        self.assertEqual(result.raw, "FF")
        self.assertEqual(result.source_base, 16)
        self.assertEqual(result.target_base, 2)
        self.assertEqual(result.normalized, "FF")
        self.assertEqual(result.source_digits, "FF")
        self.assertEqual(result.target_digits, "11111111")
        self.assertEqual(result.value, 255)
        self.assertFalse(result.is_negative)
        self.assertEqual(result.source_text, "FF")
        self.assertEqual(result.decimal_text, "255")


if __name__ == "__main__":
    unittest.main()
