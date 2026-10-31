"""进制转换的核心逻辑。

本模块只负责“计算”与“生成讲解步骤”，不依赖任何图形界面，
方便单独测试，也方便在命令行或其它界面中复用。

核心思路：
1. 任意进制 -> 十进制：按权展开（每一位乘以基数的位序次方后求和）。
2. 十进制 -> 任意进制：除基取余（不断除以目标基数，余数倒序排列）。
3. 源进制与目标进制都不是十进制时，先用方法 1，再用方法 2。

输入处理说明：
- 先做 NFKC 规范化，全角数字/字母/空格/符号会统一成 ASCII；
- 允许正负号、数字之间的空格与下划线，以及 0b/0o/0x 前缀；
- 只在整数范围内演示，出现小数点或中文间隔号会明确报错。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

# 支持的数码。0-9 表示 0-9，A-Z 表示 10-35，因此最多支持 36 进制。
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MIN_BASE = 2
MAX_BASE = 36
MAX_INPUT_DIGITS = 96

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
# 出现这些字符时说明用户输入了小数，而本程序只演示整数。
_DECIMAL_MARKS = (".", "。", "·")

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
    kind: str = "info"  # info / expand / divide
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    footer: str = ""
    formula: str = ""


@dataclass(frozen=True)
class ConversionResult:
    """一次成功转换的完整结果。"""

    raw: str
    source_base: int
    target_base: int
    normalized: str
    source_digits: str
    target_digits: str
    value: int
    steps: tuple[Step, ...] = field(default_factory=tuple)

    @property
    def is_negative(self) -> bool:
        return self.value < 0

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
        return str(self.value)

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


def parse_number(text: str, base: int) -> tuple[int, str, str]:
    """解析输入字符串。

    返回 (带符号的整数值, 规范化文本, 去掉符号和前缀后的数码串)。
    允许正负号、前后空格、数字之间的空格与下划线，以及 0b/0o/0x 前缀；
    输入会先做 NFKC 规范化，因此全角字符也能正确识别。只支持整数。
    """
    validate_base(base)
    # 先把全角数字、字母、空格、正负号等统一成 ASCII 写法。
    normalized_text = unicodedata.normalize("NFKC", text or "")

    # 小数明确报错，避免把 "." 当成无效数码（那样提示不够清楚）。
    if any(mark in normalized_text for mark in _DECIMAL_MARKS):
        raise ConversionError("当前版本只演示整数，不支持小数部分（例如 3.14）。")

    located = _located_chars(normalized_text)
    if not located:
        raise ConversionError("请输入一个数字，例如 255、FF 或 1010。")

    start = 0
    sign = 1
    if located[0][0] in "+-":
        if located[0][0] == "-":
            sign = -1
        start = 1
        if start >= len(located):
            raise ConversionError("正负号后面还需要数字。")

    # 正负号之后允许 0b/0o/0x 前缀；前缀与源进制不匹配时给出明确提示。
    if len(located) - start >= 2 and located[start][0] == "0":
        candidate = (located[start][0] + located[start + 1][0]).upper()
        detected_base = _PREFIX_BASES.get(candidate)
        if detected_base is not None:
            if detected_base != base:
                raise _prefix_error(detected_base, base)
            start += 2
            if start >= len(located):
                raise ConversionError("进制前缀后面还需要数字。")

    digit_chars = [char for char, _ in located[start:]]
    digits = "".join(digit_chars)
    if len(digits) > MAX_INPUT_DIGITS:
        raise ConversionError(
            f"数字过长，最多支持 {MAX_INPUT_DIGITS} 位数码，以免步骤列表失去可读性。"
        )

    upper = digits.upper()
    for offset, char in enumerate(upper):
        if char not in DIGITS[:base]:
            position = located[start + offset][1]
            raise ConversionError(
                f"“{char}” 不是 {base} 进制中的有效数码"
                f"（可用：{allowed_digits_hint(base)}），位置：第 {position} 位。"
            )

    digits = upper.lstrip("0") or "0"
    value = int(digits, base)
    if value == 0:
        sign = 1  # 避免出现 -0
    normalized = ("-" if sign < 0 else "") + digits
    return sign * value, normalized, digits


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


def _expansion_step(
    digits: str, base: int, magnitude: int, negative: bool = False
) -> Step:
    """生成“按权展开”步骤。

    负数只对绝对值做展开演算，并在文案中显式说明最后补回负号。
    """
    rows: list[tuple[str, ...]] = []
    terms: list[str] = []
    products: list[str] = []

    for offset, char in enumerate(digits):
        position = len(digits) - offset - 1
        digit_value = DIGITS.index(char)
        weight = base**position
        product = digit_value * weight
        rows.append(
            (
                str(position),
                char,
                str(digit_value),
                f"{base}^{position}",
                str(weight),
                str(product),
            )
        )
        coefficient = "" if digit_value == 1 else f"{digit_value}×"
        terms.append(f"{coefficient}{base}^{position}")
        products.append(str(product))

    if negative:
        formula = f"绝对值：{' + '.join(terms)} = {magnitude}；补回负号后 = -{magnitude}"
        footer = (
            f"各项求和（绝对值）：{' + '.join(products)} = {magnitude}；"
            f"补回负号后结果为 -{magnitude}。"
        )
        title = f"按权展开（绝对值）：{digits} → 十进制"
        description = (
            f"输入是负数，先取绝对值 {digits} 计算：从右向左给每一位编号，"
            f"位序从 0 开始。第 n 位的权值是 {base}ⁿ，这一位的贡献 = 数码值 × 权值；"
            f"算完后再补回负号，最终十进制结果为 -{magnitude}。"
        )
    else:
        formula = f"{' + '.join(terms)} = {magnitude}"
        footer = f"各项求和：{' + '.join(products)} = {magnitude}"
        title = f"按权展开：{digits} → 十进制"
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


def _division_step(magnitude: int, base: int, negative: bool = False) -> Step:
    """生成“除基取余”步骤。

    负数只对绝对值做除法演算，并在文案中显式说明最后补回负号。
    """
    if magnitude == 0:
        return Step(
            kicker="方法二 · 除基取余",
            title=f"除基取余：0 → {base} 进制",
            description="被除数已经是 0，不需要再做除法，结果就是 0。",
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
        description = (
            f"输入是负数，先对绝对值 {magnitude} 做除基取余："
            f"不断用目标进制 {base} 去除被除数，记录商和余数，直到商为 0。"
            f"最后把余数从下往上读，再补回负号，结果为 -{result_digits}。"
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
        description = (
            f"不断用目标进制 {base} 去除被除数，记录商和余数，"
            "直到商为 0。最后把余数从下往上读。"
        )
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


def _route_step(source_base: int, target_base: int, negative: bool = False) -> Step:
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
    if negative:
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


def _same_base_step(value: int, base: int, normalized: str) -> Step:
    description = (
        f"输入已经是 {base_name(base)}（{base} 进制），数值保持不变。"
        "下面的结果只是去掉了前导零，并统一为大写字母。"
    )
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
    """完成一次转换并生成所有讲解步骤。"""
    validate_base(source_base, "source_base")
    validate_base(target_base, "target_base")
    value, normalized, digits = parse_number(text, source_base)
    magnitude = abs(value)
    negative = value < 0
    target_digits = int_to_base(magnitude, target_base)
    sign = "-" if negative else ""
    target_signed = sign + target_digits

    steps: list[Step] = []
    if source_base == target_base:
        steps.append(_same_base_step(value, source_base, normalized))
    else:
        if source_base != 10 and target_base != 10:
            steps.append(_route_step(source_base, target_base, negative))
        if source_base != 10:
            steps.append(_expansion_step(digits, source_base, magnitude, negative))
        if target_base != 10:
            steps.append(_division_step(magnitude, target_base, negative))

    return ConversionResult(
        raw=text,
        source_base=source_base,
        target_base=target_base,
        normalized=normalized,
        source_digits=digits,
        target_digits=target_signed,
        value=value,
        steps=tuple(steps),
    )


def build_quick_examples() -> Iterable[tuple[str, str, int, int]]:
    """给界面使用的示例数据：(按钮文字, 输入, 源进制, 目标进制)。"""
    return (
        ("255 → 二进制", "255", 10, 2),
        ("FF → 十进制", "FF", 16, 10),
        ("二进制 → 十六进制", "10101010", 2, 16),
        ("2024 → 36 进制", "2024", 10, 36),
    )
