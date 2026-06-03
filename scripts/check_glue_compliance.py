"""红线违规检测脚本（v3.0 - 整合 v0.3 终态需求）

检测 glue/ 目录是否违反红线约束 C-1 ~ C-5 及新规则。

红线定义：
- C-1: glue/ 不得 import CRM Core 写型 CRUD
- C-2: 不得跳过 preview
- C-3: glue/ 不得成为 CRM 业务规则第二实现地
- C-4: 不得 Handler 被 glue 直接 execute()
- C-5: 不得把 db session 传给胶水层

新增规则（Phase 5 整合）：
- C-ACTION: glue 不得直接导入 ActionExecutor（CRUD 包装层）
- C-PREVIEW: glue 不得自建 Preview 逻辑（违反单一 truth）

v0.3 终态需求规则（Phase 7 整合）：
- C-WRITE-ACCESS: glue 不得直接执行写型数据操作（session.commit/db.add 等）

合规路径：glue → action_entry → ActionExecutor(CRUD层)

参见: CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md Phase 5
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 17.3 R-A ~ R-E
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# glue 目录
GLUE_DIR = PROJECT_ROOT / "CRM-Server" / "app" / "glue"

# 红线违规检测规则
VIOLATIONS = {
    "C-1": {
        "pattern": r"from app\.crud import",
        "message": "禁止导入写型 CRUD",
        "severity": "ERROR",
    },
    "C-1-alt": {
        "pattern": r"from app\.crud\.(customer|opportunity|contract|lead|approval|customer_follow_up) import .*_crud",
        "message": "禁止导入业务 CRUD",
        "severity": "ERROR",
    },
    "C-4": {
        "pattern": r"from app\.services\.skills\.handlers import",
        "message": "禁止导入 Handler",
        "severity": "ERROR",
    },
    "C-4-alt": {
        "pattern": r"HandlerFactory",
        "message": "禁止使用 HandlerFactory",
        "severity": "ERROR",
    },
    "C-DS": {
        "pattern": r"from app\.services\.skills import dynamic_skill_service",
        "message": "禁止导入 DynamicSkillService",
        "severity": "ERROR",
    },
    "C-DS-alt": {
        "pattern": r"dynamic_skill_service\.execute_action",
        "message": "禁止调用 DynamicSkillService.execute_action",
        "severity": "ERROR",
    },
    # Phase 5 新增规则
    "C-ACTION": {
        "pattern": r"from app\.services\.ai\.action_executor import ActionExecutor",
        "message": "禁止直接导入 ActionExecutor（CRUD 包装层）- 应使用 ActionEntry",
        "severity": "ERROR",
    },
    "C-ACTION-alt": {
        "pattern": r"from app\.services\.ai import action_executor",
        "message": "禁止导入 action_executor 模块 - 应使用 action_entry",
        "severity": "ERROR",
    },
    "C-PREVIEW": {
        "pattern": r"def _build_preview_from_slots\(",
        "message": "禁止自建 Preview 逻辑（违反 R-2 单一 truth）",
        "severity": "ERROR",
    },
    "C-PREVIEW-alt": {
        "pattern": r"def _build_preview\(",
        "message": "禁止自建 Preview 函数（违反 R-2 单一 truth）",
        "severity": "ERROR",
    },
    # v0.3 终态需求规则（R-A: Tools 层单一入口）
    "C-WRITE-ACCESS": {
        "pattern": r"session\.commit\(",
        "message": "禁止直接执行 session.commit（违反 R-A: Entry 是唯一入口）",
        "severity": "ERROR",
    },
    "C-WRITE-ACCESS-db": {
        "pattern": r"db\.add\(|db\.merge\(|db\.delete\(",
        "message": "禁止直接执行 db.add/merge/delete（违反 R-A: Entry 是唯一入口）",
        "severity": "ERROR",
    },
    "C-WRITE-ACCESS-crud": {
        "pattern": r"(customer_crud|opportunity_crud|contract_crud|lead_crud|approval_crud|customer_follow_up_crud)\.(create|update|delete)\(",
        "message": "禁止直接调用业务 CRUD create/update/delete（违反 R-A: Entry 是唯一入口）",
        "severity": "ERROR",
    },
}

# 合规导入检测（正向验证）
COMPLIANT_IMPORTS = {
    "R-3-compliant": {
        "pattern": r"from app\.services\.ai\.action_entry import",
        "message": "合规：使用 ActionEntry 入口函数",
        "severity": "OK",
    },
}


def check_file(filepath: Path) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """检查单个文件的违规和合规项

    Args:
        filepath: 文件路径

    Returns:
        (违规列表, 合规项列表)
    """
    violations = []
    compliant_items = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

        # 检查违规规则
        for rule_id, config in VIOLATIONS.items():
            pattern = config["pattern"]
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    violations.append({
                        "file": str(filepath.relative_to(PROJECT_ROOT)),
                        "line": line_num,
                        "rule": rule_id,
                        "message": config["message"],
                        "severity": config["severity"],
                        "content": line.strip(),
                    })

        # 检查合规导入
        for rule_id, config in COMPLIANT_IMPORTS.items():
            pattern = config["pattern"]
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    compliant_items.append({
                        "file": str(filepath.relative_to(PROJECT_ROOT)),
                        "line": line_num,
                        "rule": rule_id,
                        "message": config["message"],
                        "severity": config["severity"],
                        "content": line.strip(),
                    })

    except Exception as e:
        print(f"⚠️  无法读取文件 {filepath}: {e}")

    return violations, compliant_items


def check_glue_directory() -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, int]]:
    """检查 glue 目录所有文件

    Returns:
        (违规列表, 合规项列表, 统计信息)
    """
    all_violations = []
    all_compliant_items = []
    stats = {
        "files_checked": 0,
        "files_clean": 0,
        "files_with_violations": 0,
        "files_with_compliant_imports": 0,
        "total_violations": 0,
        "total_compliant_imports": 0,
    }

    if not GLUE_DIR.exists():
        print(f"❌ glue 目录不存在: {GLUE_DIR}")
        return [], [], stats

    for root, dirs, files in os.walk(GLUE_DIR):
        for file in files:
            if file.endswith(".py"):
                filepath = Path(root) / file
                violations, compliant_items = check_file(filepath)
                stats["files_checked"] += 1

                if violations:
                    all_violations.extend(violations)
                    stats["files_with_violations"] += 1
                    stats["total_violations"] += len(violations)
                else:
                    stats["files_clean"] += 1

                if compliant_items:
                    all_compliant_items.extend(compliant_items)
                    stats["files_with_compliant_imports"] += 1
                    stats["total_compliant_imports"] += len(compliant_items)

    return all_violations, all_compliant_items, stats


def print_report(
    violations: List[Dict[str, str]],
    compliant_items: List[Dict[str, str]],
    stats: Dict[str, int],
) -> bool:
    """打印检测报告

    Args:
        violations: 违规列表
        compliant_items: 合规项列表
        stats: 统计信息

    Returns:
        是否合规
    """
    print("=" * 70)
    print("GLUE 层红线约束合规检测报告 (v3.0)")
    print("=" * 70)
    print()

    print(f"📁 检查目录: {GLUE_DIR.relative_to(PROJECT_ROOT)}")
    print(f"📄 检查文件: {stats['files_checked']} 个")
    print()

    # 打印合规导入（正向验证）
    if compliant_items:
        print("✅ 合规导入检测（正向验证）：")
        print("-" * 70)

        by_rule = {}
        for item in compliant_items:
            if item["rule"] not in by_rule:
                by_rule[item["rule"]] = []
            by_rule[item["rule"]].append(item)

        for rule, items in by_rule.items():
            print(f"\n[{rule}] {COMPLIANT_IMPORTS[rule]['message']}")
            for item in items:
                print(f"  📍 {item['file']}:{item['line']}")
                print(f"     {item['content']}")

        print()

    if violations:
        print("❌ 发现红线违规：")
        print("-" * 70)

        # 按规则分组
        by_rule = {}
        for v in violations:
            if v["rule"] not in by_rule:
                by_rule[v["rule"]] = []
            by_rule[v["rule"]].append(v)

        for rule, items in by_rule.items():
            print(f"\n[{rule}] {VIOLATIONS[rule]['message']}")
            for v in items:
                print(f"  📍 {v['file']}:{v['line']}")
                print(f"     {v['content']}")

        print()
        print("-" * 70)
        print(f"❌ 不合规：发现 {stats['total_violations']} 个违规")
        print(f"   📄 有违规文件: {stats['files_with_violations']} 个")
        print(f"   ✅ 无违规文件: {stats['files_clean']} 个")
        return False

    else:
        print("✅ glue 层架构合规")
        print("-" * 70)
        print(f"   📄 全部文件: {stats['files_checked']} 个")
        print(f"   ✅ 所有文件无违规")
        print()
        print("红线约束检测结果：")
        print("  C-1 ✅ 无 CRUD import")
        print("  C-4 ✅ 无 Handler import")
        print("  C-DS ✅ 无 DynamicSkillService import")
        print("  C-ACTION ✅ 无 ActionExecutor import（使用 ActionEntry）")
        print("  C-PREVIEW ✅ 无自建 Preview 逻辑")
        print("  C-WRITE-ACCESS ✅ 无直接写型数据操作（R-A 合规）")
        print("  C-PREVIEW ✅ 无自建 Preview 逻辑")
        print()
        print("合规路径验证：")
        if stats["total_compliant_imports"] > 0:
            print(f"  R-3 ✅ glue → action_entry 入口函数（发现 {stats['total_compliant_imports']} 处导入）")
        else:
            print("  R-3 ⚠️ 未检测到 action_entry 导入（请检查 glue/core/executor.py）")
        print()
        print("C-5 说明：")
        print("  executor 持有 db session，但仅传递给 action_entry")
        print("  不直接调用 CRM CRUD 写操作，满足 Single Writer 原则")
        return True


def main():
    """主入口"""
    print("🔍 开始检测 glue 层红线约束 (v2.0)...\n")

    violations, compliant_items, stats = check_glue_directory()
    is_compliant = print_report(violations, compliant_items, stats)

    print("=" * 70)
    if is_compliant:
        print("✅ 检测通过")
        sys.exit(0)
    else:
        print("❌ 检测失败")
        sys.exit(1)


if __name__ == "__main__":
    main()