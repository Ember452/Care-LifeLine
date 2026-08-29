"""PHI 脱敏单测：每条正则分支的脱敏结果都要落到具体值。"""

from care_lifeline.safety.phi import mask


def test_mask_空文本_原样返回() -> None:
    assert mask("") == ""


def test_mask_姓名_替换为PHI占位符() -> None:
    assert mask("姓名：张三") == "姓名：[PHI]"


def test_mask_我叫_整段姓名脱敏() -> None:
    # 姓名值只吃 2-4 个字：脱敏后保留其余临床语境（旧实现吞掉整段）。
    assert mask("我叫李四，最近头晕") == "我叫[PHI]，最近头晕"


def test_mask_身份证号_替换为PHI占位符() -> None:
    assert mask("身份证 11010519900307123X") == "身份证 [PHI]"


def test_mask_手机号_替换为PHI占位符() -> None:
    assert mask("联系方式 13800138000") == "联系方式 [PHI]"


def test_mask_病历号_替换为PHI占位符() -> None:
    assert mask("病历号：MR20260828") == "病历号[PHI]"


def test_mask_就诊号_仅脱敏字母数字段() -> None:
    # 旧实现 \w+ 在连字号处截断、泄漏了「-88231」；新实现整段替换。
    assert mask("就诊号 OPD-88231") == "就诊号[PHI]"


def test_mask_无敏感信息_原样返回() -> None:
    assert mask("血压 150/95，建议复诊") == "血压 150/95，建议复诊"
