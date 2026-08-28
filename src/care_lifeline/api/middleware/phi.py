from __future__ import annotations

import re

from care_lifeline.safety.phi import mask

_METHODS_WITH_BODY = ("POST", "PUT", "PATCH")

# 与 safety/phi.mask 同源的正则，用于「输出落库前」复查是否残留标识符。
_NAME_RE = re.compile(r"(姓名[：:]|我叫|患者[：:])\s*(\S+)")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]")
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_MEDICAL_REC_RE = re.compile(r"(病历号|就诊号|门诊号)[：: ]?(\w+)")


class PHIMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODY:
            await self.app(scope, receive, send)
            return

        async def new_receive():
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if body:
                    try:
                        text = body.decode("utf-8")
                    except UnicodeDecodeError:
                        text = body.decode("utf-8", "replace")
                    message["body"] = mask(text).encode("utf-8")
            return message

        await self.app(scope, new_receive, send)


def detect_phi_leak(text: str) -> str | None:
    """检测输出文本中的 PHI 泄漏形态（P1-10）。

    命中任一种即返回泄漏类型，全部未命中返回 ``None``：
    - ``phi_marker_residual``：模型把脱敏占位符 ``[PHI]`` 原样输出了；
    - ``id_card`` / ``phone`` / ``name`` / ``medical_record_id``：脱敏遗漏的原始标识符。

    Args:
        text: 待检测的输出文本（助手回复草稿）。

    Returns:
        泄漏类型，或 ``None``。
    """
    if not text:
        return None
    if "[PHI]" in text:
        return "phi_marker_residual"
    if _ID_CARD_RE.search(text):
        return "id_card"
    if _PHONE_RE.search(text):
        return "phone"
    if _NAME_RE.search(text):
        return "name"
    if _MEDICAL_REC_RE.search(text):
        return "medical_record_id"
    return None
