"""Task 2.4 (B4): safety.py 被 import 不应 NameError。

safety.py:9 导入 `from typing import Dict, Any` 但 :21 使用 `Optional[str]`
未导入 Optional，导致模块被 import 即 NameError。
"""


def test_safety_module_imports_clean():
    """B4: safety.py 被 import 不应 NameError。"""
    import importlib
    mod = importlib.import_module("app.glue.core.safety")
    assert hasattr(mod, "SafetyGateway"), "safety 模块应有 SafetyGateway 类"
    assert hasattr(mod, "SafetyResult"), "safety 模块应有 SafetyResult dataclass"