"""公司名称归一化工具（R-ST-02）

处理口语化的公司名称，使其能匹配数据库中的法定全称。

功能：
1. 全角→半角（可选）
2. 去括号内容
3. 去法定后缀（股份有限公司/有限公司/集团等）

示例：
- "光大证券股份有限公司" → "光大证券"
- "张三（北京）科技有限公司" → "张三科技"
- "华为技术有限公司" → "华为技术"
"""

import re
import unicodedata


def normalize_corp_name(name: str) -> str:
    """归一化公司名称（R-ST-02 合规）

    Args:
        name: 原始公司名称

    Returns:
        归一化后的名称

    Examples:
        >>> normalize_corp_name("光大证券股份有限公司")
        "光大证券"
        >>> normalize_corp_name("张三（北京）科技有限公司")
        "张三科技"
    """
    if not name:
        return ""

    # 1. Unicode 归一化（NFKC：兼容性分解再组合）
    n = unicodedata.normalize("NFKC", name).strip()

    # 2. 全角→半角（括号）
    n = n.replace("（", "(").replace("）", ")")

    # 3. 去括号内容（如"张三（北京）科技" → "张三科技")
    n = re.sub(r"\s*\(", "(", n)
    n = re.sub(r"\([^)]*\)", "", n)

    # 4. 去法定后缀（业务词典）
    # 按长度排序，优先匹配长后缀（避免"有限公司"误删"股份公司"的一部分）
    suffixes = [
        "股份有限公司",
        "有限责任公司",
        "有限公司",
        "股份公司",
        "集团",
        "分公司",
        "营业部",
        "办事处",
    ]
    for suffix in suffixes:
        if n.endswith(suffix):
            n = n[:-len(suffix)]
            break

    # 5. 清理多余空格
    n = n.strip()

    return n


def build_customer_name_dedupe_key(name: str | None) -> str | None:
    """生成客户名称唯一判重键。

    只合并不改变业务含义的 Unicode 差异: NFKC 兼容等价(康熙部首/全角字符)、
    零宽等格式字符、各类空白。不去后缀、不做相似字检测; 与 normalize_corp_name 区分。

    Examples:
        >>> build_customer_name_dedupe_key("中⼼")  # U+2F3C
        "中心"
    """
    if not name:
        return None
    n = unicodedata.normalize("NFKC", name)
    n = "".join(ch for ch in n if unicodedata.category(ch) != "Cf")
    n = " ".join(n.split())
    return n or None


__all__ = ["build_customer_name_dedupe_key", "normalize_corp_name"]