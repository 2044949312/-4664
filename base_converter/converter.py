"""进制转换的核心逻辑。

本模块只负责“计算”与“生成讲解步骤”，不依赖任何图形界面，
方便单独测试，也方便在命令行或其它界面中复用。

核心思路：
1. 任意进制 -> 十进制：按权展开（每一位乘以基数的位序次方后求和）。
2. 十进制 -> 任意进制：除基取余（不断除以目标基数，余数倒序排列）。
3. 源进制与目标进制都不是十进制时，先用方法 1，再用方法 2。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# 支持的数码。0-9 表示 0-9，A-Z 表示 10-35，因此最多支持 36 进制。
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MIN_BASE = 2
MAX_BASE = 36
MAX_INPUT_DIGITS = 96

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
    20: "二十进制",
    32: "三十二进制",
    36: "三十六进制",
}

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


def _strip_prefix(text: str, base: int) -> str:
    """允许用户输入 0b1010、0o17、0x1F 这类带前缀的写法。"""
    prefixes = {2: "0B", 8: "0O", 16: "0X"}
    prefix = prefixes.get(base)
    if prefix and text.upper().startswith(prefix):
        return text[2:]
    return text


def parse_number(text: str, base: int) -> tuple[int, str, str]:
    """解析输入字符串。

    返回 (带符号的整数值, 规范化文本, 去掉符号和前缀后的数码串)。
    允许正负号、前后空格、数字之间的空格与下划线，以及 0b/0o/0x 前缀。
    """
    validate_base(base)
    raw = text or ""
    cleaned = raw.strip().replace(" ", "").replace("_", "")
    if not cleaned:
        raise ConversionError("请输入一个数字，例如 255、FF 或 1010。")

    sign = 1
    if cleaned[0] in "+-":
        if cleaned[0] == "-":
            sign = -1
        cleaned = cleaned[1:]
        if not cleaned:
            raise ConversionError("正负号后面还需要数字。")

    cleaned = _strip_prefix(cleaned, base)
    if not cleaned:
        raise ConversionError("进制前缀后面还需要数字。")

    if len(cleaned) > MAX_INPUT_DIGITS:
        raise ConversionError(
            f"数字过长，最多支持 {MAX_INPUT_DIGITS} 位数码，以免步骤列表失去可读性。"
        )

    upper = cleaned.upper()
    for position, char in enumerate(upper, start=1):
        if char not in DIGITS[:base]:
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


def _expansion_step(digits: str, base: int, decimal_value: int) -> Step:
    """生成“按权展开”步骤。"""
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

    formula = f"{' + '.join(terms)} = {decimal_value}"
    footer = f"各项求和：{' + '.join(products)} = {decimal_value}"
    return Step(
        kicker="方法一 · 按权展开",
        title=f"按权展开：{digits} → 十进制",
        description=(
            f"从右向左给每一位编号，位序从 0 开始。"
            f"第 n 位的权值是 {base}ⁿ，这一位的贡献 = 数码值 × 权值。"
        ),
        kind="expand",
        headers=("位序 n", "数码", "数码值", f"权值 {base}ⁿ", "权值大小", "贡献"),
        rows=tuple(rows),
        footer=footer,
        formula=formula,
    )


def _division_step(decimal_value: int, base: int) -> Step:
    """生成“除基取余”步骤。"""
    if decimal_value == 0:
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
    current = decimal_value
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
    return Step(
        kicker="方法二 · 除基取余",
        title=f"除基取余：{decimal_value} → {base} 进制",
        description=(
            f"不断用目标进制 {base} 去除被除数，记录商和余数，"
            "直到商为 0。最后把余数从下往上读。"
        ),
        kind="divide",
        headers=("轮次", "被除数", f"÷ {base}", "商", "余数", "余数数码"),
        rows=tuple(rows),
        footer=f"余数从下往上读：{read_order}  →  {result_digits}",
        formula=f"({decimal_value})₁₀ = ({result_digits}){_subscript(base)}",
    )


def _route_step(source_base: int, target_base: int) -> Step:
    return Step(
        kicker="转换路线",
        title="转换路线：先转十进制，再转目标进制",
        description=(
            f"{base_name(source_base)}与{base_name(target_base)}之间没有直接的逐位换算规则。"
            "通用做法是：先按权展开得到十进制数，再用除基取余法转换为目标进制。"
        ),
        kind="info",
    )


def _same_base_step(value: int, base: int, digits: str) -> Step:
    return Step(
        kicker="无需换算",
        title="无需换算：源进制与目标进制相同",
        description=(
            f"输入已经是 {base} 进制，数值保持不变。"
            "下面的结果只是去掉了前导零，并统一为大写字母。"
        ),
        kind="info",
        formula=f"({digits}){_subscript(base)} = ({digits}){_subscript(base)}",
    )


def build_conversion(
    text: str, source_base: int, target_base: int
) -> ConversionResult:
    """完成一次转换并生成所有讲解步骤。"""
    validate_base(source_base, "source_base")
    validate_base(target_base, "target_base")
    value, normalized, digits = parse_number(text, source_base)
    magnitude = abs(value)
    target_digits = int_to_base(magnitude, target_base)
    sign = "-" if value < 0 else ""
    target_signed = sign + target_digits

    steps: list[Step] = []
    if source_base == target_base:
        steps.append(_same_base_step(value, source_base, digits))
    else:
        if source_base != 10 and target_base != 10:
            steps.append(_route_step(source_base, target_base))
        if source_base != 10:
            steps.append(_expansion_step(digits, source_base, magnitude))
        if target_base != 10:
            steps.append(_division_step(magnitude, target_base))

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
