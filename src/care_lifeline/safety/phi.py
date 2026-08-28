from __future__ import annotations

import re

_NAME_RE = re.compile(r"(姓名[：:]|我叫|患者[：:])\s*(\S+)")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]")
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_MEDICAL_REC_RE = re.compile(r"(病历号|就诊号|门诊号)[：: ]?(\w+)")


def mask(text: str) -> str:
    if not text:
        return text
    text = _NAME_RE.sub(r"\1[PHI]", text)
    text = _ID_CARD_RE.sub("[PHI]", text)
    text = _PHONE_RE.sub("[PHI]", text)
    text = _MEDICAL_REC_RE.sub(r"\1[PHI]", text)
    return text
