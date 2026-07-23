"""Glue 层架构合规检测脚本

检测内容：
- C-1: glue 层无 CRUD import
- C-4: glue 层无 Handler import
- C-DS: glue 层无 DynamicSkillService import
- C-PREVIEW: glue 层无自建 Preview 逻辑
- C-WRITE-ACCESS: glue 层无直接写型数据操作（R-A）
- R-ST-01: EntityResolver 无裸 CRUD（所有路径汇入 EntitySearchService）
- R-ST-05: EntitySearchService 有 load_by_id 方法

执行：
python3 scripts/check_glue_compliance.py
"""

import subprocess
import sys


def run_grep(pattern: str, path: str) -> bool:
    """运行 grep 检测，返回是否命中"""
    result = subprocess.run(
        ["grep", "-rn", "-E", pattern, path, "--include=*.py"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() != ""


def check_glue_compliance():
    """检测 glue 层红线合规"""
    print("=" * 60)
    print("Glue 层架构合规检测")
    print("=" * 60)

    errors = []

    # C-1: glue 层无 CRUD import
    if run_grep(r"from app\.crud\.|import.*_crud", "app/glue/"):
        errors.append("C-1 ❌ glue 层存在 CRUD import")
    else:
        print("C-1 ✅ 无 CRUD import")

    # C-4: glue 层无 Handler import
    if run_grep(r"from app\.api\.|Handler", "app/glue/"):
        errors.append("C-4 ❌ glue 层存在 Handler import")
    else:
        print("C-4 ✅ 无 Handler import")

    # C-DS: glue 层无 DynamicSkillService import
    if run_grep(r"DynamicSkillService", "app/glue/"):
        errors.append("C-DS ❌ glue 层存在 DynamicSkillService import")
    else:
        print("C-DS ✅ 无 DynamicSkillService import")

    # C-PREVIEW: glue 层无自建 Preview 逻辑
    result = subprocess.run(
        ["grep", "-rn", "_build_preview_from_slots", "app/glue/", "--include=*.py"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        # 检查是否仅为注释说明（已删除）
        lines = result.stdout.strip().split("\n")
        # 如果只有注释（包含"已删除"/"移除"等关键词），不视为违规
        is_comment_only = all(
            any(kw in line for kw in ["已删除", "移除", "R-2", "- "])
            for line in lines
        )
        if is_comment_only:
            print("C-PREVIEW ✅ 无自建 Preview 逻辑（仅注释说明已删除）")
        else:
            errors.append("C-PREVIEW ❌ glue 层存在自建 Preview 逻辑")
    else:
        print("C-PREVIEW ✅ 无自建 Preview 逻辑")

    # C-WRITE-ACCESS: glue 层无直接写型数据操作（R-A）
    # 注意：Python dict 的 update() 方法不是数据库操作，需排除
    write_patterns = [
        "Customer\\.query\\(\\)\\.filter",
        "db\\.add\\(",
        "db\\.commit\\(",
        "db\\.delete\\(",
        "\\.save\\(\\)",
    ]
    for pattern in write_patterns:
        if run_grep(pattern, "app/glue/"):
            errors.append(f"C-WRITE-ACCESS ❌ glue 层存在直接写操作: {pattern}")
            break

    # 单独检查 .update()，排除 Python dict 的 update（如 pending.slots.update）
    result = subprocess.run(
        ["grep", "-rn", "\\.update\\(", "app/glue/", "--include=*.py"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        # 检查是否仅为 dict.update（不是 ORM 对象的 update）
        lines = result.stdout.strip().split("\n")
        for line in lines:
            # 如果是 dict.update（包含 "slots.update", "dict.update" 等），不视为违规
            if not any(kw in line for kw in ["slots.update", "dict.update", "Dict"]):
                errors.append(f"C-WRITE-ACCESS ❌ glue 层存在直接写操作: .update()")
                break

    if not any("C-WRITE-ACCESS" in e for e in errors):
        print("C-WRITE-ACCESS ✅ 无直接写型数据操作（R-A 合规）")

    # R-ST-01: EntityResolver 无裸 CRUD
    entity_patterns = [
        "Customer\\.query\\(\\)",
        "db\\.get\\(Customer",
        "db\\.query\\(Customer",
    ]
    for pattern in entity_patterns:
        if run_grep(pattern, "app/glue/core/entity.py"):
            errors.append(f"R-ST-01 ❌ EntityResolver 存在裸 CRUD: {pattern}")
            break
    if not any("R-ST-01" in e for e in errors):
        print("R-ST-01 ✅ EntityResolver 无裸 CRUD（所有路径汇入 EntitySearchService）")

    # R-ST-05: EntitySearchService 有 load_by_id 方法
    result = subprocess.run(
        ["grep", "-n", "load_customer_by_id", "app/services/ai/entity_search.py"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print("R-ST-05 ✅ EntitySearchService 有 load_by_id 方法")
    else:
        errors.append("R-ST-05 ❌ EntitySearchService 缺少 load_by_id 方法")

    print("\n" + "=" * 60)
    if errors:
        print("检测失败，发现以下违规：")
        for error in errors:
            print(f"  {error}")
        print("=" * 60)
        return False
    else:
        print("✅ glue 层架构合规")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = check_glue_compliance()
    sys.exit(0 if success else 1)
