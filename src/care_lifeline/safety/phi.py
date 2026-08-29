"""PHI 识别与脱敏引擎（入口中间件与出口泄漏检测共用的单一实现）。

检测器管线：每条规则 = (类型, 编译正则, 替换模板)。带标签的规则只替换
值、保留「病历号/年龄」等字段名（信息结构不丢），无标签的强标识符
（身份证/手机/邮箱）整体替换。

当前为纯规则实现：零依赖、热路径毫秒级、CI 确定性可回归；模型 NER
（HanLP 等）作为 real 模式演进位，见 ADR-0016——接口保持 ``mask`` /
``detect_phi_leak`` 不变，可平滑升级。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 常见中文姓氏（覆盖百家姓前 100），供「姓 + 称谓」「老/小 + 姓」两种
# 无标签姓名启发式使用。
_COMMON_SURNAMES = (
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董"
    "潘袁蔡蒋余于杜叶程魏苏吕丁任卢姚沈钟姜崔谭陆范汪廖石金韦贾夏付方邹熊"
    "白孟秦邱侯江尹薛闫段雷龙黎史陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)

_NAME_TITLES = "先生|女士|小姐|同学|护士|医生|主任|教授|老师|阿姨|叔叔|大爷|大妈|爷爷|奶奶"


@dataclass(frozen=True)
class PHIRule:
    """单条 PHI 检测规则。

    Attributes:
        kind: PHI 类型名（泄漏检测/审计用）。
        pattern: 编译好的正则。
        replacement: ``re.sub`` 替换模板；``\\1[PHI]`` 形式保留标签前缀。
    """

    kind: str
    pattern: re.Pattern[str]
    replacement: str


def _rule(kind: str, pattern: str, replacement: str) -> PHIRule:
    return PHIRule(kind=kind, pattern=re.compile(pattern), replacement=replacement)


# 规则按特异性排序：无标签强标识符在前，标签兜底规则在后；
# mask 按序应用保证幂等（masked 文本不会再次命中）。
_RULES: tuple[PHIRule, ...] = (
    _rule("id_card", r"\d{17}[\dXx]", "[PHI]"),
    _rule("phone", r"1[3-9]\d{9}", "[PHI]"),
    _rule("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[PHI]"),
    _rule(
        "birth_date",
        r"(出生日期|出生|生日|DOB)[：:]?\s*(\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?|\d{8})",
        r"\1[PHI]",
    ),
    _rule(
        "medical_record_id",
        r"(病历号|就诊号|门诊号|住院号|就诊卡号|检查号|影像号)[：: ]?([\w-]{1,32})",
        r"\1[PHI]",
    ),
    _rule(
        "name",
        r"(姓名[：:]|患者姓名[：:]|我叫|患者[：:])\s*([\u4e00-\u9fa5a-zA-Z·]{2,4})",
        r"\1[PHI]",
    ),
    _rule(
        "name",
        rf"([{_COMMON_SURNAMES}]{{1,2}})({_NAME_TITLES})",
        r"[PHI]\2",
    ),
    _rule("name", rf"(老|小)([{_COMMON_SURNAMES}])", "[PHI]"),
    _rule("age", r"(年龄|年纪)[：:]?\s*(\d{1,3})", r"\1[PHI]"),
    _rule("address", r"(住址|地址|家庭住址)[：:]?\s*([\u4e00-\u9fa5\d]{2,30})", r"\1[PHI]"),
    _rule(
        "social_account",
        r"(微信号|微信|QQ号|QQ)[：:]?\s*([A-Za-z][\w-]{5,19}|\d{5,11})",
        r"\1[PHI]",
    ),
    _rule("phone", r"(电话|联系电话|联系方式|手机号)[：:]?\s*([\d-]{7,13})", r"\1[PHI]"),
)


def detect_kinds(text: str) -> list[str]:
    """按规则顺序返回文本命中的 PHI 类型（去重）。

    Args:
        text: 待检测文本。

    Returns:
        命中类型列表（如 ``["id_card", "phone"]``）；无命中为空表。
    """
    if not text:
        return []
    kinds: list[str] = []
    for rule in _RULES:
        if rule.kind not in kinds and rule.pattern.search(text):
            kinds.append(rule.kind)
    return kinds


def mask(text: str) -> str:
    """脱敏文本：命中的 PHI 替换为 ``[PHI]`` 占位符（幂等）。"""
    if not text:
        return text
    for rule in _RULES:
        text = rule.pattern.sub(rule.replacement, text)
    return text


def detect_phi_leak(text: str) -> str | None:
    """检测输出文本中的 PHI 泄漏形态（P1-10）。

    命中任一种即返回泄漏类型，全部未命中返回 ``None``：
    - ``phi_marker_residual``：模型把脱敏占位符 ``[PHI]`` 原样输出了；
    - ``id_card`` / ``phone`` / ``email`` / ``birth_date`` / ``name`` /
      ``age`` / ``address`` / ``social_account`` / ``medical_record_id``：
      脱敏遗漏的原始标识符。

    Args:
        text: 待检测的输出文本（助手回复草稿）。

    Returns:
        泄漏类型，或 ``None``。
    """
    if not text:
        return None
    if "[PHI]" in text:
        return "phi_marker_residual"
    kinds = detect_kinds(text)
    return kinds[0] if kinds else None
