"""进制转换的核心逻辑。

本模块只负责“计算”与“生成讲解步骤”，不依赖任何图形界面，
方便单独测试，也方便在命令行或其它界面中复用。

核心思路：
1. 任意进制 -> 十进制：
   - 整数部分按权展开（每一位乘以基数的位序次方后求和）；
   - 小数部分同样按权展开，位序从 -1 开始（即 1/基数 的幂）。
2. 十进制 -> 任意进制：
   - 整数部分除基取余（不断除以目标基数，余数倒序排列）；
   - 小数部分乘基取整（不断乘以目标基数，整数部分依次排列）。
3. 源进制与目标进制都不是十进制时，先用方法 1，再用方法 2。

小数说明：
- 全程使用 ``fractions.Fraction`` 做精确有理数运算，不经过二进制浮点数，
  因此 0.1、0.625 这类输入不会因为浮点误差得到错误数码。
- 换算到目标进制后，小数可能终止，也可能无限循环。循环小数用括号标注
  循环节，例如 ``(0.1)₁₀ = (0.0(0011))₂``；循环节过长时只展开前
  ``MAX_FRACTION_OUTPUT_DIGITS`` 位并用 ``…`` 标记。

输入处理说明：
- 先做 NFKC 规范化，全角数字/字母/空格/符号会统一成 ASCII；
- 允许正负号、数字之间的空格与下划线，以及 0b/0o/0x 前缀；
- 支持小数点（``.``、``。``、``·``）和循环节括号，例如 3.14、0.1(6)；
- 输入位数上限同时约束整数部分、小数部分与循环节。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable

# 支持的数码。0-9 表示 0-9，A-Z 表示 10-35，因此最多支持 36 进制。
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MIN_BASE = 2
MAX_BASE = 36
MAX_INPUT_DIGITS = 96

# 目标进制的小数最多展开多少位。超过时标记为截断，避免循环节过长拖慢界面。
MAX_FRACTION_OUTPUT_DIGITS = 64

# 2–36 进制的完整中文名称，供界面和讲解文案使用。
BASE_NAMES = {
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

# 0b / 0o / 0x 前缀对应的进制。
_PREFIX_BASES = {"0B": 2, "0O": 8, "0X": 16}
# 这些进制是 2 的幂，理论上相邻/相关的 2 的幂进制可以按二进制位分组快速换算。
_POWER_OF_TWO_BASES = frozenset({2, 4, 8, 16, 32})
# 中文间隔号与全角句号也当作小数点使用，避免用户切换输入法后无法输入小数。
_DECIMAL_MARKS = {"。": ".", "·": ".", "・": "."}

SUBSCRIPT_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


class ConversionError(ValueError):
    """输入不合法时抛出的异常，message 可以直接展示给用户。"""

    def __init__(self, message: str, field: str = "number") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True)
class Step:
    """一个讲解步骤。

    headers/rows 为空时，该步骤只展示说明文字（例如“转换路线”）。
    """

    kicker: str
    title: str
    description: str
    kind: str = "info"  # info / expand / divide / multiply
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    footer: str = ""
    formula: str = ""


@dataclass(frozen=True)
class _MultiplyRow:
    """乘基取整的一轮演算（原始数值，格式化在步骤生成时完成）。"""

    round_no: int
    multiplicand: Fraction
    product: Fraction
    digit: str
    remainder: Fraction


@dataclass(frozen=True)
class FractionExpansion:
    """小数部分在某个进制下的数码展开结果。

    digits   循环节之前（含有尽小数的全部数码）的部分；
    repeat   循环节；为空表示有尽小数；
    truncated 为 True 时说明小数部分在位数上限内没有结束
             （可能是很长的有限小数，也可能是循环节过长）；
    steps    乘基取整的逐轮演算，供界面表格使用。
    """

    digits: str
    repeat: str = ""
    truncated: bool = False
    steps: tuple[_MultiplyRow, ...] = ()

    @property
    def is_repeating(self) -> bool:
        return bool(self.repeat)

    def text(self) -> str:
        """返回可直接显示的数码串，循环节用括号、截断用省略号。"""
        if self.repeat:
            return f"{self.digits}({self.repeat})"
        if self.truncated:
            return f"{self.digits}…"
        return self.digits


@dataclass(frozen=True)
class ParsedNumber:
    """解析后的输入（包含小数信息）。"""

    raw: str
    base: int
    value: Fraction
    negative: bool
    normalized: str
    integer_digits: str
    fraction_digits: str = ""
    repeat_digits: str = ""
    fraction_truncated: bool = False

    @property
    def has_fraction(self) -> bool:
        return bool(self.fraction_digits or self.repeat_digits)

    @property
    def fraction_text(self) -> str:
        if not self.has_fraction:
            return ""
        text = self.fraction_digits
        if self.repeat_digits:
            text += f"({self.repeat_digits})"
        elif self.fraction_truncated:
            text += "…"
        return text


@dataclass(frozen=True)
class ConversionResult:
    """一次成功转换的完整结果。"""

    raw: str
    source_base: int
    target_base: int
    normalized: str
    source_digits: str
    target_digits: str
    value: Fraction
    steps: tuple[Step, ...] = field(default_factory=tuple)
    integer_value: int = 0
    fraction_value: Fraction = Fraction(0)
    target_integer_digits: str = ""
    target_fraction_digits: str = ""
    target_repeat_digits: str = ""
    target_truncated: bool = False

    @property
    def is_negative(self) -> bool:
        return self.value < 0

    @property
    def is_fraction(self) -> bool:
        """输入或结果是否包含小数部分（2.0 这类值仍按整数处理）。"""
        return self.value.denominator != 1

    @property
    def is_repeating(self) -> bool:
        """目标进制下是否为循环小数。"""
        return bool(self.target_repeat_digits)

    @property
    def source_name(self) -> str:
        return BASE_NAMES.get(self.source_base, f"{self.source_base} 进制")

    @property
    def target_name(self) -> str:
        return BASE_NAMES.get(self.target_base, f"{self.target_base} 进制")

    @property
    def result_text(self) -> str:
        # target_digits 已包含负号，这里直接返回，避免出现 "--FF"。
        return self.target_digits

    @property
    def source_text(self) -> str:
        return self.normalized

    @property
    def decimal_text(self) -> str:
        return value_to_text(self.value, 10, MAX_FRACTION_OUTPUT_DIGITS)

    def expression(self) -> str:
        """返回形如 (FF)₁₆ → (11111111)₂ 的展示表达式。"""
        return (
            f"({self.normalized}){_subscript(self.source_base)}"
            f"  →  ({self.result_text}){_subscript(self.target_base)}"
        )


def _subscript(number: int) -> str:
    return str(number).translate(SUBSCRIPT_DIGITS)


def base_name(base: int) -> str:
    return BASE_NAMES.get(base, f"{base} 进制")


def validate_base(base: int, field: str = "base") -> None:
    if not isinstance(base, int) or isinstance(base, bool):
        raise ConversionError("进制必须是 2–36 之间的整数。", field)
    if not MIN_BASE <= base <= MAX_BASE:
        raise ConversionError(f"进制必须在 {MIN_BASE}–{MAX_BASE} 之间。", field)


def allowed_digits_hint(base: int) -> str:
    if base <= 10:
        return f"0–{base - 1}"
    return f"0–9、A–{DIGITS[base - 1]}"


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    for mark, dot in _DECIMAL_MARKS.items():
        normalized = normalized.replace(mark, dot)
    return normalized


def _located_chars(text: str) -> list[tuple[str, int]]:
    """返回 (字符, 在规范化文本中的 1 基位置) 列表，忽略空格与下划线。

    位置基于 NFKC 规范化后的原始文本计算，而不是去掉符号/前缀后的数码串，
    这样报错时指向的仍然是用户实际输入的位置。
    """
    return [
        (char, index)
        for index, char in enumerate(text, start=1)
        if not char.isspace() and char != "_"
    ]


def _prefix_error(detected_base: int, source_base: int) -> ConversionError:
    prefix = next(
        key.lower() for key, base in _PREFIX_BASES.items() if base == detected_base
    )
    return ConversionError(
        f"检测到 {prefix} 前缀（{base_name(detected_base)}），"
        f"但当前源进制是 {base_name(source_base)}；"
        f"请把源进制改为 {detected_base}，或去掉前缀。"
    )


# --------------------------------------------------------------------------- 格式化


def _terminating_parts(denominator: int) -> tuple[int, int, bool]:
    """分解分母中的 2 与 5，判断该分数能否写成有限十进制小数。"""
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    return twos, fives, denominator == 1


def _exact_decimal(value: Fraction) -> str:
    """把有限十进制分数精确格式化为字符串（不使用浮点数）。"""
    sign = "-" if value < 0 else ""
    numerator = abs(value.numerator)
    denominator = value.denominator
    twos, fives, _ = _terminating_parts(denominator)
    places = max(twos, fives)
    if places == 0:
        return sign + str(numerator)
    scaled = numerator * (10**places) // denominator
    digits = str(scaled).rjust(places + 1, "0")
    integer_part = digits[:-places]
    fraction_part = digits[-places:].rstrip("0")
    if not fraction_part:
        return sign + integer_part
    return f"{sign}{integer_part}.{fraction_part}"


def _scalar(value: Fraction | int, limit: int = 24) -> str:
    """把一个数值格式化为适合表格展示的短文本。

    能写成有限十进制小数时优先使用十进制（例如 0.625），否则使用 p/q
    （例如 1/3），保证信息量足够且不出现浮点误差。
    """
    if not isinstance(value, Fraction):
        value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    _, _, terminating = _terminating_parts(value.denominator)
    if terminating:
        text = _exact_decimal(value)
        if len(text) <= limit:
            return text
    return f"{value.numerator}/{value.denominator}"


def expand_fraction(
    value: Fraction, base: int, max_digits: int = MAX_FRACTION_OUTPUT_DIGITS
) -> FractionExpansion:
    """用“乘基取整”把 0 ≤ value < 1 的小数展开成 base 进制数码。

    通过记录出现过的剩余小数来识别循环节（剩余小数重复即意味着数码开始循环），
    因此有尽小数会自然终止，循环小数会得到准确的循环节，而不是近似值。
    """
    validate_base(base)
    if value < 0 or value >= 1:
        raise ValueError("expand_fraction 只接受 [0, 1) 之间的小数。")

    digits: list[str] = []
    steps: list[_MultiplyRow] = []
    seen: dict[Fraction, int] = {}
    current = value

    while True:
        if current == 0:
            return FractionExpansion("".join(digits), "", False, tuple(steps))
        if current in seen:
            split = seen[current]
            return FractionExpansion(
                "".join(digits[:split]),
                "".join(digits[split:]),
                False,
                tuple(steps),
            )
        if len(digits) >= max_digits:
            return FractionExpansion("".join(digits), "", True, tuple(steps))

        seen[current] = len(digits)
        product = current * base
        digit = int(product)  # product ≥ 0，int() 等价于向下取整
        remainder = product - digit
        steps.append(
            _MultiplyRow(
                round_no=len(digits) + 1,
                multiplicand=current,
                product=product,
                digit=DIGITS[digit],
                remainder=remainder,
            )
        )
        digits.append(DIGITS[digit])
        current = remainder


def value_to_text(
    value: Fraction, base: int, max_digits: int = MAX_FRACTION_OUTPUT_DIGITS
) -> str:
    """把任意有理数写成指定进制的文本，循环小数用括号标注循环节。"""
    validate_base(base)
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    integer_part = int(magnitude)
    fraction_part = magnitude - integer_part
    text = int_to_base(integer_part, base)
    if fraction_part:
        text += "." + expand_fraction(fraction_part, base, max_digits).text()
    return sign + text


def _decimal_note(value: Fraction) -> str:
    """当值不能写成有限十进制小数时，补充说明它的十进制写法。"""
    if value.denominator == 1:
        return ""
    _, _, terminating = _terminating_parts(value.denominator)
    if terminating:
        return ""
    return f"（十进制写作 {value_to_text(value, 10)}）"


# --------------------------------------------------------------------------- 解析


def parse_decimal(text: str, base: int) -> ParsedNumber:
    """解析输入，返回包含小数信息的 ParsedNumber。

    支持的写法：
        255、-FF、0x1F、1010 1010、3.14、.5、0.625、0.(3)、0.1(6)
    括号表示循环节；小数部分与整数部分合计最多 MAX_INPUT_DIGITS 位数码。
    """
    validate_base(base)
    if "…" in (text or ""):
        raise ConversionError(
            "“…”表示结果被截断，不能直接作为输入；"
            "请粘贴完整数值，或用括号表示循环节（例如 0.1(6)）。"
        )
    normalized_text = _normalize_text(text)
    located = _located_chars(normalized_text)
    if not located:
        raise ConversionError("请输入一个数字，例如 255、3.14、FF 或 0.1(6)。")

    chars = [char for char, _ in located]
    positions = [position for _, position in located]

    start = 0
    negative = False
    if chars[0] in "+-":
        negative = chars[0] == "-"
        start = 1
        if start >= len(chars):
            raise ConversionError("正负号后面还需要数字。")

    # 正负号之后允许 0b/0o/0x 前缀；前缀与源进制不匹配时给出明确提示。
    if len(chars) - start >= 2 and chars[start] == "0":
        candidate = (chars[start] + chars[start + 1]).upper()
        detected_base = _PREFIX_BASES.get(candidate)
        if detected_base is not None:
            if detected_base != base:
                raise _prefix_error(detected_base, base)
            start += 2
            if start >= len(chars):
                raise ConversionError("进制前缀后面还需要数字。")

    body = chars[start:]
    body_positions = positions[start:]

    if body.count(".") > 1:
        raise ConversionError("小数点只能有一个，例如 3.14。")

    dot_index = body.index(".") if "." in body else -1
    if dot_index >= 0:
        integer_chars = body[:dot_index]
        integer_positions = body_positions[:dot_index]
        rest_chars = body[dot_index + 1 :]
        rest_positions = body_positions[dot_index + 1 :]
    else:
        integer_chars = body
        integer_positions = body_positions
        rest_chars = []
        rest_positions = []

    # 循环节括号只能出现在小数点之后，并且必须包住结尾的数字。
    if "(" in body or ")" in body:
        if dot_index < 0:
            raise ConversionError(
                "循环节括号必须写在小数点之后，例如 0.1(6)。"
            )
        if integer_chars and ("(" in integer_chars or ")" in integer_chars):
            raise ConversionError(
                "循环节括号必须写在小数点之后，例如 0.1(6)。"
            )
        if rest_chars.count("(") != 1 or rest_chars.count(")") != 1:
            raise ConversionError(
                "循环节要用一对括号括起来，例如 0.1(6)。"
            )
        open_index = rest_chars.index("(")
        if rest_chars[-1] != ")" or open_index > len(rest_chars) - 2:
            raise ConversionError(
                "循环节括号要写在数字末尾，例如 0.1(6)。"
            )
        if ")" in rest_chars[:open_index]:
            raise ConversionError(
                "循环节要用一对括号括起来，例如 0.1(6)。"
            )
        fraction_chars = rest_chars[:open_index]
        fraction_positions = rest_positions[:open_index]
        repeat_chars = rest_chars[open_index + 1 : -1]
        repeat_positions = rest_positions[open_index + 1 : -1]
        if not repeat_chars:
            raise ConversionError(
                "循环节括号里至少需要一位数码，例如 0.1(6)。"
            )
    else:
        fraction_chars = rest_chars
        fraction_positions = rest_positions
        repeat_chars = []
        repeat_positions = []

    if not integer_chars and not fraction_chars and not repeat_chars:
        if dot_index >= 0:
            raise ConversionError("小数点前后至少需要一位数字，例如 3.14。")
        raise ConversionError("请输入一个数字，例如 255、3.14、FF 或 0.1(6)。")
    if dot_index >= 0 and not fraction_chars and not repeat_chars:
        raise ConversionError("小数点后面还需要数字，例如 3.14。")

    digit_groups = (
        (integer_chars, integer_positions),
        (fraction_chars, fraction_positions),
        (repeat_chars, repeat_positions),
    )
    total_digits = sum(len(group) for group, _ in digit_groups)
    if total_digits > MAX_INPUT_DIGITS:
        raise ConversionError(
            f"数字过长，最多支持 {MAX_INPUT_DIGITS} 位数码，以免步骤列表失去可读性。"
        )

    for group, group_positions in digit_groups:
        for char, position in zip(group, group_positions):
            if char.upper() not in DIGITS[:base]:
                raise ConversionError(
                    f"“{char}” 不是 {base} 进制中的有效数码"
                    f"（可用：{allowed_digits_hint(base)}），位置：第 {position} 位。"
                )

    integer_digits = "".join(integer_chars) or "0"
    fraction_digits = "".join(fraction_chars)
    repeat_digits = "".join(repeat_chars)

    integer_value = int(integer_digits, base)
    fraction_places = len(fraction_digits)
    repeat_length = len(repeat_digits)

    fraction_value = Fraction(0)
    if fraction_places:
        fraction_value += Fraction(int(fraction_digits, base), base**fraction_places)
    if repeat_length:
        # 0.(R) = R / (base^k - 1)，再按位置除以 base^m 左移 m 位。
        fraction_value += Fraction(
            int(repeat_digits, base),
            (base**repeat_length - 1) * (base**fraction_places),
        )

    value = Fraction(integer_value) + fraction_value
    # 0.(9)₁₀、0.(1)₂ 这类循环节会恰好进到 1，需要把整数部分与小数部分重新拆分。
    integer_value = int(value)
    fraction_value = value - integer_value
    if negative and value:
        value = -value

    # 用“值”重新生成规范写法：去掉前导零、末尾多余零，并把循环节写规范。
    canonical_integer = int_to_base(integer_value, base)
    canonical_fraction = ""
    canonical_repeat = ""
    truncated = False
    if fraction_value:
        expansion = expand_fraction(
            fraction_value, base, max(MAX_INPUT_DIGITS, fraction_places + repeat_length)
        )
        canonical_fraction = expansion.digits
        canonical_repeat = expansion.repeat
        truncated = expansion.truncated

    normalized = canonical_integer
    if fraction_value:
        normalized += "." + canonical_fraction
        if canonical_repeat:
            normalized += f"({canonical_repeat})"
        elif truncated:
            normalized += "…"
    if value < 0:
        normalized = "-" + normalized

    return ParsedNumber(
        raw=text,
        base=base,
        value=value,
        negative=value < 0,
        normalized=normalized,
        integer_digits=canonical_integer,
        fraction_digits=canonical_fraction,
        repeat_digits=canonical_repeat,
        fraction_truncated=truncated,
    )


def parse_number(text: str, base: int) -> tuple[Fraction, str, str]:
    """兼容旧接口：返回 (带符号的值, 规范化文本, 整数部分数码串)。

    值现在是精确的 Fraction（整数输入的 Fraction 与 int 比较相等）。
    需要小数部分或循环节信息时，请使用 :func:`parse_decimal`。
    """
    parsed = parse_decimal(text, base)
    return parsed.value, parsed.normalized, parsed.integer_digits


def int_to_base(value: int, base: int) -> str:
    """把十进制整数转为目标进制字符串（不含正号，负数带负号）。"""
    validate_base(base)
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    value = abs(value)
    out: list[str] = []
    while value:
        value, remainder = divmod(value, base)
        out.append(DIGITS[remainder])
    return sign + "".join(reversed(out))


# --------------------------------------------------------------------------- 步骤


def _expansion_step(
    integer_digits: str,
    fraction_digits: str,
    base: int,
    magnitude: Fraction,
    negative: bool = False,
) -> Step:
    """生成“按权展开”步骤（整数部分位序 ≥ 0，小数部分位序 < 0）。

    负数只对绝对值做展开演算，并在文案中显式说明最后补回负号。
    """
    rows: list[tuple[str, ...]] = []
    terms: list[str] = []
    products: list[str] = []

    for offset, char in enumerate(integer_digits):
        position = len(integer_digits) - offset - 1
        digit_value = DIGITS.index(char)
        weight = Fraction(base**position)
        product = digit_value * weight
        rows.append(
            (
                str(position),
                char,
                str(digit_value),
                f"{base}^{position}",
                _scalar(weight),
                _scalar(product),
            )
        )
        coefficient = "" if digit_value == 1 else f"{digit_value}×"
        terms.append(f"{coefficient}{base}^{position}")
        products.append(_scalar(product))

    for offset, char in enumerate(fraction_digits):
        position = -(offset + 1)
        digit_value = DIGITS.index(char)
        weight = Fraction(1, base ** (-position))
        product = digit_value * weight
        rows.append(
            (
                str(position),
                char,
                str(digit_value),
                f"{base}^{position}",
                _scalar(weight),
                _scalar(product),
            )
        )
        coefficient = "" if digit_value == 1 else f"{digit_value}×"
        terms.append(f"{coefficient}{base}^{position}")
        products.append(_scalar(product))

    has_fraction = bool(fraction_digits)
    number_text = integer_digits
    if has_fraction:
        number_text += "." + fraction_digits

    sum_text = _scalar(magnitude) + _decimal_note(magnitude)
    if negative:
        formula = (
            f"绝对值：{' + '.join(terms)} = {sum_text}；"
            f"补回负号后 = -{_scalar(magnitude)}"
        )
        footer = (
            f"各项求和（绝对值）：{' + '.join(products)} = {sum_text}；"
            f"补回负号后结果为 -{_scalar(magnitude)}。"
        )
        title = f"按权展开（绝对值）：{number_text} → 十进制"
        description = (
            f"输入是负数，先取绝对值 {number_text} 计算：从右向左给整数部分编号，"
            f"位序从 0 开始；小数部分从左向右编号，位序从 −1 开始。"
            f"第 n 位的权值是 {base}ⁿ，这一位的贡献 = 数码值 × 权值；"
            f"算完后再补回负号。"
        )
        if has_fraction:
            description += "带小数的结果同样是精确值，不会产生浮点误差。"
    else:
        formula = f"{' + '.join(terms)} = {sum_text}"
        footer = f"各项求和：{' + '.join(products)} = {sum_text}"
        title = f"按权展开：{number_text} → 十进制"
        if has_fraction:
            description = (
                f"给每一位编号：整数部分从右向左，位序从 0 开始；"
                f"小数部分从左向右，位序从 −1 开始（−1 位的权值是 1/{base}）。"
                f"第 n 位的权值是 {base}ⁿ，这一位的贡献 = 数码值 × 权值。"
            )
        else:
            description = (
                f"从右向左给每一位编号，位序从 0 开始。"
                f"第 n 位的权值是 {base}ⁿ，这一位的贡献 = 数码值 × 权值。"
            )

    return Step(
        kicker="方法一 · 按权展开",
        title=title,
        description=description,
        kind="expand",
        headers=("位序 n", "数码", "数码值", f"权值 {base}ⁿ", "权值大小", "贡献"),
        rows=tuple(rows),
        footer=footer,
        formula=formula,
    )


def _division_step(
    magnitude: int, base: int, negative: bool = False, has_fraction: bool = False
) -> Step:
    """生成“除基取余”步骤。

    负数只对绝对值做除法演算，并在文案中显式说明最后补回负号。
    """
    if magnitude == 0:
        description = "被除数是 0，不需要再做除法，整数部分的结果就是 0。"
        if has_fraction:
            description += "小数部分由下一步“乘基取整”单独换算。"
        return Step(
            kicker="方法二 · 除基取余",
            title=f"除基取余：0 → {base} 进制",
            description=description,
            kind="divide",
            headers=("轮次", "被除数", f"÷ {base}", "商", "余数", "余数数码"),
            rows=(("1", "0", f"0 ÷ {base}", "0", "0", "0"),),
            footer="余数从下往上读：0",
            formula=f"0 = 0（{base} 进制）",
        )

    rows: list[tuple[str, ...]] = []
    remainders: list[str] = []
    current = magnitude
    round_no = 0
    while current > 0:
        round_no += 1
        quotient, remainder = divmod(current, base)
        digit = DIGITS[remainder]
        rows.append(
            (
                str(round_no),
                str(current),
                f"{current} ÷ {base}",
                str(quotient),
                str(remainder),
                digit,
            )
        )
        remainders.append(digit)
        current = quotient

    read_order = " ".join(reversed(remainders))
    result_digits = "".join(reversed(remainders))

    if negative:
        title = f"除基取余（绝对值）：{magnitude} → {base} 进制"
        if has_fraction:
            title = f"整数部分除基取余（绝对值）：{magnitude} → {base} 进制"
        description = (
            f"输入是负数，先对绝对值 {magnitude} 做除基取余："
            f"不断用目标进制 {base} 去除被除数，记录商和余数，直到商为 0。"
            f"最后把余数从下往上读，再补回负号，结果为 -{result_digits}。"
        )
        if has_fraction:
            description += (
                "这里只换算整数部分；小数部分会在「乘基取整」步骤中单独处理。"
            )
        footer = (
            f"余数从下往上读：{read_order}  →  {result_digits}；"
            f"补回负号后结果为 -{result_digits}。"
        )
        formula = (
            f"绝对值：({magnitude})₁₀ = ({result_digits}){_subscript(base)}；"
            f"补回负号得 (-{result_digits}){_subscript(base)}"
        )
    else:
        title = f"除基取余：{magnitude} → {base} 进制"
        if has_fraction:
            title = f"整数部分除基取余：{magnitude} → {base} 进制"
        description = (
            f"不断用目标进制 {base} 去除被除数，记录商和余数，"
            "直到商为 0。最后把余数从下往上读。"
        )
        if has_fraction:
            description += "这一步只处理整数部分；小数部分由下一步「乘基取整」换算。"
        footer = f"余数从下往上读：{read_order}  →  {result_digits}"
        formula = f"({magnitude})₁₀ = ({result_digits}){_subscript(base)}"

    return Step(
        kicker="方法二 · 除基取余",
        title=title,
        description=description,
        kind="divide",
        headers=("轮次", "被除数", f"÷ {base}", "商", "余数", "余数数码"),
        rows=tuple(rows),
        footer=footer,
        formula=formula,
    )


def _multiplication_step(
    base: int,
    expansion: FractionExpansion,
    *,
    source_base: int,
    source_fraction_text: str,
    negative: bool = False,
) -> Step:
    """生成“乘基取整”步骤，用于把小数部分换算成目标进制。"""
    rows: list[tuple[str, ...]] = []
    for row in expansion.steps:
        multiplicand = _scalar(row.multiplicand)
        product = _scalar(row.product)
        remainder = _scalar(row.remainder)
        rows.append(
            (
                str(row.round_no),
                multiplicand,
                f"{multiplicand} × {base}",
                product,
                row.digit,
                remainder,
            )
        )

    read_order = " ".join(expansion.digits)
    target_fraction = expansion.text()
    source_text = f"0.{source_fraction_text}"
    target_text = f"0.{target_fraction}"
    symbol = "≈" if expansion.truncated else "="

    if expansion.repeat:
        footer = (
            f"每轮乘积的整数部分从上往下读：{read_order}  →  {target_text}；"
            f"其中 {expansion.repeat} 是循环节，会无限重复。"
        )
    elif expansion.truncated:
        footer = (
            f"已展开前 {len(expansion.digits)} 位：{read_order}  →  {target_text}；"
            f"小数部分在 {MAX_FRACTION_OUTPUT_DIGITS} 位内没有结束"
            f"（有限小数较长或循环节过长），结果只保留前 "
            f"{MAX_FRACTION_OUTPUT_DIGITS} 位。"
        )
    else:
        footer = f"每轮乘积的整数部分从上往下读：{read_order}  →  {target_text}"

    if negative:
        title = f"乘基取整（绝对值）：{source_text} → {base_name(base)}"
        description = (
            f"输入是负数，先对绝对值的小数部分 {source_text} 做乘基取整："
            f"不断乘以目标进制 {base}，把乘积的整数部分依次作为小数数码，"
            "直到剩余小数为 0 或开始循环；最后再补回负号。"
        )
        formula = (
            f"绝对值：({source_text}){_subscript(source_base)} {symbol} "
            f"({target_text}){_subscript(base)}；"
            f"补回负号得 (-{target_text}){_subscript(base)}"
        )
    else:
        title = f"乘基取整：{source_text} → {base_name(base)}"
        description = (
            f"小数部分不断乘以目标进制 {base}，把乘积的整数部分依次作为下一位数码，"
            "直到剩余小数变成 0（有限小数）或开始重复（循环小数）。"
            f"读出的数码从上往下排列，就得到小数部分的 {base} 进制写法。"
        )
        formula = (
            f"({source_text}){_subscript(source_base)} {symbol} "
            f"({target_text}){_subscript(base)}"
        )

    return Step(
        kicker="方法三 · 乘基取整",
        title=title,
        description=description,
        kind="multiply",
        headers=("轮次", "被乘数", f"× {base}", "乘积", "取整", "剩余小数"),
        rows=tuple(rows),
        footer=footer,
        formula=formula,
    )


def _repeating_input_step(parsed: ParsedNumber, negative: bool = False) -> Step:
    """解释带括号的循环小数输入如何换算成精确的十进制值。"""
    base = parsed.base
    fraction_text = parsed.fraction_digits
    repeat_text = parsed.repeat_digits
    places = len(fraction_text)
    repeat_length = len(repeat_text)
    integer_value = int(parsed.integer_digits, base)

    terms: list[str] = []
    if integer_value:
        terms.append(str(integer_value))
    if places:
        pre_value = Fraction(int(fraction_text, base), base**places)
        if pre_value:
            terms.append(_scalar(pre_value))
    repeat_value = int(repeat_text, base)
    repeat_denominator = f"{base}^{repeat_length} − 1"
    if places:
        repeat_denominator = f"({repeat_denominator}) × {base}^{places}"
    terms.append(f"{repeat_value}/({repeat_denominator})")

    magnitude = abs(parsed.value)
    signed_text = parsed.normalized
    absolute_text = signed_text[1:] if signed_text.startswith("-") else signed_text
    if negative:
        formula = (
            f"绝对值：{absolute_text} = {' + '.join(terms)} = {_scalar(magnitude)}"
        )
    else:
        formula = f"{absolute_text} = {' + '.join(terms)} = {_scalar(magnitude)}"

    decimal_text = value_to_text(magnitude, 10)
    footer = (
        f"该输入精确等于 {_scalar(magnitude)}（十进制 {decimal_text}），"
        "后续换算都使用这个精确值。"
    )
    if places:
        description = (
            "输入中的括号表示循环节：括号内的数码会无限重复。"
            f"循环节 {repeat_length} 位，按等比级数求和为 R/({base}^{repeat_length} − 1)，"
            f"再按位置除以 {base}^{places}，最后与整数部分、非循环小数部分相加。"
        )
    else:
        description = (
            "输入中的括号表示循环节：括号内的数码会无限重复。"
            f"循环节 {repeat_length} 位，按等比级数求和为 R/({base}^{repeat_length} − 1)，"
            "再与整数部分相加。"
        )
    if negative:
        description = (
            "输入是负数，这里先按绝对值解释循环节，最后统一补回负号。" + description
        )
        footer = "输入是负数，先用绝对值计算：" + footer

    return Step(
        kicker="方法一 · 循环小数展开",
        title=f"循环小数展开：{parsed.normalized} → 十进制",
        description=description,
        kind="expand",
        footer=footer,
        formula=formula,
    )


def _route_step(
    source_base: int, target_base: int, negative: bool = False, has_fraction: bool = False
) -> Step:
    if source_base in _POWER_OF_TWO_BASES and target_base in _POWER_OF_TWO_BASES:
        route_text = (
            f"{base_name(source_base)}与{base_name(target_base)}都是 2 的幂，"
            "理论上存在按 3 位、4 位或 5 位二进制分组直接换算的快捷方法；"
            "但本程序统一使用通用十进制路线：先按权展开得到十进制数，"
            "再用除基取余法转换为目标进制，以便完整展示每一步演算。"
        )
    else:
        route_text = (
            f"{base_name(source_base)}与{base_name(target_base)}之间的换算，"
            "本程序统一使用十进制中转路线：先按权展开得到十进制数，"
            "再用除基取余法转换为目标进制。"
        )
    if has_fraction:
        route_text += (
            "带小数时，整数部分用除基取余、小数部分用乘基取整；"
            "小数可能是有限小数，也可能出现循环节（用括号标注）。"
        )
    if negative:
        if has_fraction:
            route_text += (
                "输入是负数时，整数部分与小数部分都只对绝对值演算，"
                "最后统一补回负号，结果仍为负数。"
            )
        else:
            route_text += (
                "输入是负数时，两种方法都只对绝对值演算，最后统一补回负号，"
                "结果仍为负数。"
            )
    return Step(
        kicker="转换路线",
        title="转换路线：先转十进制，再转目标进制",
        description=route_text,
        kind="info",
    )


def _same_base_step(
    value: Fraction, base: int, normalized: str, has_fraction: bool = False
) -> Step:
    description = (
        f"输入已经是 {base_name(base)}（{base} 进制），数值保持不变。"
        "下面的结果只是去掉了前导零和末尾多余的零，并统一为大写字母。"
    )
    if has_fraction:
        description += "小数部分和括号表示的循环节会按原进制保留。"
    if value < 0:
        description += "输入的负号会原样保留，结果仍是负数。"
    return Step(
        kicker="无需换算",
        title="无需换算：源进制与目标进制相同",
        description=description,
        kind="info",
        formula=(
            f"({normalized}){_subscript(base)} = ({normalized}){_subscript(base)}"
        ),
    )


def build_conversion(
    text: str, source_base: int, target_base: int
) -> ConversionResult:
    """完成一次转换并生成所有讲解步骤（支持整数、有限小数与循环小数）。"""
    validate_base(source_base, "source_base")
    validate_base(target_base, "target_base")
    parsed = parse_decimal(text, source_base)
    value = parsed.value
    negative = value < 0
    magnitude = abs(value)
    integer_part = int(magnitude)
    fraction_part = magnitude - integer_part

    target_integer = int_to_base(integer_part, target_base)
    target_expansion: FractionExpansion | None = None
    target_text = target_integer
    if fraction_part:
        target_expansion = expand_fraction(
            fraction_part, target_base, MAX_FRACTION_OUTPUT_DIGITS
        )
        target_text += "." + target_expansion.text()
    sign = "-" if negative else ""
    target_signed = sign + target_text

    # 同进制不需要重新展开：直接用规范化写法，避免把很长的循环节截断。
    if source_base == target_base:
        target_signed = parsed.normalized
        target_integer = parsed.integer_digits
        target_fraction = parsed.fraction_digits
        target_repeat = parsed.repeat_digits
        target_truncated = parsed.fraction_truncated
    else:
        target_fraction = target_expansion.digits if target_expansion else ""
        target_repeat = target_expansion.repeat if target_expansion else ""
        target_truncated = target_expansion.truncated if target_expansion else False

    steps: list[Step] = []
    if source_base == target_base:
        steps.append(
            _same_base_step(
                value, source_base, parsed.normalized, parsed.has_fraction
            )
        )
    else:
        if source_base != 10 and target_base != 10:
            steps.append(
                _route_step(
                    source_base, target_base, negative, bool(fraction_part)
                )
            )
        if parsed.repeat_digits:
            steps.append(_repeating_input_step(parsed, negative))
        elif source_base != 10:
            steps.append(
                _expansion_step(
                    parsed.integer_digits,
                    parsed.fraction_digits,
                    source_base,
                    magnitude,
                    negative,
                )
            )
        if target_base != 10:
            if integer_part or not fraction_part:
                steps.append(
                    _division_step(
                        integer_part,
                        target_base,
                        negative,
                        has_fraction=bool(fraction_part),
                    )
                )
            if fraction_part and target_expansion is not None:
                steps.append(
                    _multiplication_step(
                        target_base,
                        target_expansion,
                        source_base=source_base,
                        source_fraction_text=parsed.fraction_text,
                        negative=negative,
                    )
                )

    return ConversionResult(
        raw=text,
        source_base=source_base,
        target_base=target_base,
        normalized=parsed.normalized,
        source_digits=parsed.integer_digits,
        target_digits=target_signed,
        value=value,
        steps=tuple(steps),
        integer_value=integer_part,
        fraction_value=fraction_part,
        target_integer_digits=target_integer,
        target_fraction_digits=target_fraction,
        target_repeat_digits=target_repeat,
        target_truncated=target_truncated,
    )


def build_quick_examples() -> Iterable[tuple[str, str, int, int]]:
    """给界面使用的示例数据：(按钮文字, 输入, 源进制, 目标进制)。"""
    return (
        ("255 → 二进制", "255", 10, 2),
        ("FF → 十进制", "FF", 16, 10),
        ("二进制 → 十六进制", "10101010", 2, 16),
        ("2024 → 36 进制", "2024", 10, 36),
        ("3.14 → 二进制", "3.14", 10, 2),
        ("0.1 → 二进制（循环）", "0.1", 10, 2),
        ("A.8 → 十进制", "A.8", 16, 10),
        ("1.5 → 十六进制", "1.5", 10, 16),
    )
