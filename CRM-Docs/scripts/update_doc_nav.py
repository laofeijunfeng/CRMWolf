#!/usr/bin/env python3
"""
文档导航更新脚本

用途：完整生成 requirements/README.md, plans/README.md, archive/README.md
执行时机：归档后自动执行

作者：CRMWolf 开发团队
版本：1.0
"""

import os
import re
from datetime import datetime
from pathlib import Path


class DocNavigationUpdater:
    """文档导航更新器"""

    def __init__(self, base_path: str = "CRM-Docs"):
        self.base_path = Path(base_path)
        self.current_date = datetime.now().strftime("%Y-%m-%d")

    def scan_docs(self, directory: str) -> list:
        """扫描目录中的文档并提取状态信息"""
        docs = []
        dir_path = self.base_path / directory

        if not dir_path.exists():
            return docs

        for doc_file in sorted(dir_path.glob("*.md")):
            if doc_file.name == "README.md":
                continue

            # 读取文件开头的前50行
            try:
                with open(doc_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 提取状态标签
                status_match = re.search(r'status:\s*(\w+)', content)
                created_match = re.search(r'created:\s*(\d{4}-\d{2}-\d{2})', content)
                updated_match = re.search(r'updated:\s*(\d{4}-\d{2}-\d{2})', content)

                if status_match:
                    status = status_match.group(1)
                    created = created_match.group(1) if created_match else "未知"
                    updated = updated_match.group(1) if updated_match else "未知"

                    docs.append({
                        "name": doc_file.name,
                        "path": f"{directory}/{doc_file.name}",
                        "status": status,
                        "created": created,
                        "updated": updated,
                        "link": f"[{doc_file.name}]({doc_file.name})"
                    })
            except Exception as e:
                print(f"⚠️ 读取文档失败: {doc_file.name} - {e}")

        return docs

    def generate_requirements_readme(self) -> str:
        """生成 requirements/README.md"""
        docs = self.scan_docs("requirements")

        # 分组：活跃和已完成
        active_docs = [d for d in docs if d['status'] in ['draft', 'review', 'active']]
        completed_docs = [d for d in docs if d['status'] == 'completed']

        # 生成活跃需求表格
        active_table = "| 文档 | 状态 | 创建日期 | 更新日期 | 关联计划 |\n"
        active_table += "|------|------|----------|----------|----------|\n"

        for doc in active_docs:
            # 查找关联计划
            related_plan = "-"
            doc_path = self.base_path / "requirements" / doc['name']
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                plan_match = re.search(r'related_plan:\s*([^\n]+)', content)
                if plan_match and plan_match.group(1) != '-':
                    plan_path = plan_match.group(1).strip()
                    plan_name = Path(plan_path).name
                    related_plan = f"[计划](../plans/{plan_name})"
            except:
                pass

            active_table += f"| {doc['link']} | {doc['status']} | {doc['created']} | {doc['updated']} | {related_plan} |\n"

        if not active_docs:
            active_table += "| _暂无活跃需求_ | - | - | - | - |\n"

        # 生成待归档需求表格
        completed_table = "| 文档 | 状态 | 完成日期 | 关联 PR | 待创建 Changelog |\n"
        completed_table += "|------|------|----------|---------|------------------|\n"

        for doc in completed_docs:
            doc_name = doc['name'].replace('.md', '')
            changelog_link = f"changelog/enhancements/{self.current_date}-{doc_name.lower()}.md"
            completed_table += f"| {doc['link']} | completed | {doc['updated']} | - | {changelog_link} |\n"

        if not completed_docs:
            completed_table += "| _暂无待归档需求_ | - | - | - | - |\n"

        # 生成完整 README
        readme_content = f"""# 需求文档导航

**活跃需求**：开发中或待开发的需求文档

---

## 状态定义

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 初稿编写，待评审 | 文档创建 |
| 评审中 | `review` | 团队评审阶段 | 草稿完成 |
| 进行中 | `active` | 开发实施阶段 | 评审通过 |
| 已完成 | `completed` | 功能已上线 | 代码合并 + 测试通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

---

## 状态汇总表

> 活跃需求清单（status: draft/review/active）

{active_table}

---

## 待归档需求

> status: completed，等待 CI 自动归档

{completed_table}

---

## 已归档需求

> 自动迁移至 `../archive/requirements/`，详见 [归档导航](../archive/README.md)

_暂无已归档需求_

---

## 文档创建规则

### 1. 新需求文档创建

```markdown
---
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_plan: -  ← 评审通过后填写
related_pr: -    ← 完成时填写
---

# [需求名称] 需求文档

...
```

### 2. 状态流转流程

```
创建文档 → status: draft
    ↓
完成初稿 → status: review
    ↓
评审通过 → status: active + 创建计划文档
    ↓
功能上线 → status: completed + 填写 PR
    ↓
CI 自动归档 → archive/requirements/
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 影子文档（未声明状态） | 违反状态管理规则 |
| 手动归档文档 | 应由 CI 自动执行 |
| 状态标签缺失 | 无法触发自动归档 |
| 未创建 Changelog 即归档 | 违反结果沉淀规则 |

---

## 相关规范

| 规范 | 文档位置 |
|------|----------|
| 文档生命周期完整规则 | [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md) |
| Git 提交规范（文档同步） | [GIT-STANDARD.md](../standards/GIT-STANDARD.md) |
| 归档导航 | [archive/README.md](../archive/README.md) |

---

**最后更新**：{self.current_date} | 由 CI 自动维护
"""

        return readme_content

    def generate_plans_readme(self) -> str:
        """生成 plans/README.md"""
        docs = self.scan_docs("plans")

        # 分组
        active_docs = [d for d in docs if d['status'] in ['draft', 'review', 'active']]
        completed_docs = [d for d in docs if d['status'] == 'completed']

        # 生成活跃计划表格
        active_table = "| 文档 | 状态 | 创建日期 | 更新日期 | 关联需求 |\n"
        active_table += "|------|------|----------|----------|----------|\n"

        for doc in active_docs:
            # 查找关联需求
            related_req = "-"
            doc_path = self.base_path / "plans" / doc['name']
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                req_match = re.search(r'related_requirements:\s*([^\n]+)', content)
                if req_match and req_match.group(1) != '-':
                    req_path = req_match.group(1).strip()
                    req_name = Path(req_path).name
                    related_req = f"[需求](../requirements/{req_name})"
            except:
                pass

            active_table += f"| {doc['link']} | {doc['status']} | {doc['created']} | {doc['updated']} | {related_req} |\n"

        if not active_docs:
            active_table += "| _暂无活跃计划_ | - | - | - | - |\n"

        # 生成待归档计划表格
        completed_table = "| 文档 | 状态 | 完成日期 | 关联 PR | 待创建 Changelog |\n"
        completed_table += "|------|------|----------|---------|------------------|\n"

        for doc in completed_docs:
            doc_name = doc['name'].replace('.md', '')
            changelog_link = f"changelog/enhancements/{self.current_date}-{doc_name.lower()}.md"
            completed_table += f"| {doc['link']} | completed | {doc['updated']} | - | {changelog_link} |\n"

        if not completed_docs:
            completed_table += "| _暂无待归档计划_ | - | - | - | - |\n"

        readme_content = f"""# 计划文档导航

**活跃计划**：正在实施或待实施的技术计划

---

## 状态定义

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 技术方案初稿 | 文档创建 |
| 评审中 | `review` | 技术评审阶段 | 草稿完成 |
| 进行中 | `active` | 实施执行阶段 | 评审通过 |
| 已完成 | `completed` | 实施完成 | 代码合并 + 验证通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

---

## 状态汇总表

> 活跃计划清单（status: draft/review/active）

{active_table}

---

## 待归档计划

> status: completed，等待 CI 自动归档

{completed_table}

---

## 已归档计划

> 自动迁移至 `../archive/plans/`，详见 [归档导航](../archive/README.md)

_暂无已归档计划_

---

## 文档创建规则

### 1. 新计划文档创建

```markdown
---
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_requirements: ../requirements/[需求文档].md  ← 必须关联
related_pr: -                                          ← 完成时填写
---

# [计划名称] 实施计划

...
```

### 2. 状态流转流程

```
创建文档 → status: draft + 关联需求文档
    ↓
完成方案 → status: review
    ↓
评审通过 → status: active + 创建任务
    ↓
实施完成 → status: completed + 填写 PR + 创建 Changelog
    ↓
CI 自动归档 → archive/plans/
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 影子文档（未声明状态） | 违反状态管理规则 |
| 手动归档文档 | 应由 CI 自动执行 |
| 状态标签缺失 | 无法触发自动归档 |
| 未创建 Changelog 即归档 | 违反结果沉淀规则 |

---

## 相关规范

| 规范 | 文档位置 |
|------|----------|
| 文档生命周期完整规则 | [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md) |
| Git 提交规范（文档同步） | [GIT-STANDARD.md](../standards/GIT-STANDARD.md) |
| 归档导航 | [archive/README.md](../archive/README.md) |

---

**最后更新**：{self.current_date} | 由 CI 自动维护
"""

        return readme_content

    def generate_archive_readme(self) -> str:
        """生成 archive/README.md"""
        archived_requirements = self.scan_docs("archive/requirements")
        archived_plans = self.scan_docs("archive/plans")

        # 生成归档需求表格
        req_table = "| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |\n"
        req_table += "|------|--------|----------|---------|----------|\n"

        for doc in archived_requirements:
            doc_name = doc['name'].replace('.md', '')
            req_table += f"| [{doc['name']}](requirements/{doc['name']}) | requirements/ | {doc['updated']} | - | [changelog](../changelog/enhancements/{doc_name.lower()}.md) |\n"

        if not archived_requirements:
            req_table += "| _暂无归档记录_ | - | - | - | - |\n"

        # 生成归档计划表格
        plan_table = "| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |\n"
        plan_table += "|------|--------|----------|---------|----------|\n"

        for doc in archived_plans:
            doc_name = doc['name'].replace('.md', '')
            plan_table += f"| [{doc['name']}](plans/{doc['name']}) | plans/ | {doc['updated']} | - | [changelog](../changelog/enhancements/{doc_name.lower()}.md) |\n"

        if not archived_plans:
            plan_table += "| _暂无归档记录_ | - | - | - | - |\n"

        readme_content = f"""# 归档文档导航

**归档文档**：已完成的需求和计划，保留历史参考

---

## 归档记录

> CI 自动维护，记录所有已归档的需求和计划文档

### 归档需求 (archive/requirements/)

{req_table}

### 归档计划 (archive/plans/)

{plan_table}

---

## 归档规则

| 规则 | 说明 |
|------|------|
| 自动归档 | CI 检测 `status: completed` 自动迁移 |
| 保留历史 | 归档文档只读，不修改 |
| 结果沉淀 | 归档前需创建 changelog 文档 |
| 导航更新 | 归档后自动更新本文件 |

---

## 归档流程

```
requirements/ 或 plans/ 中的文档
    ↓
status: completed + PR 合并
    ↓
CI 检测触发自动归档
    ↓
迁移至 archive/requirements/ 或 archive/plans/
    ↓
更新 archive/README.md 导航
    ↓
更新 requirements/README.md 或 plans/README.md
```

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 修改归档文档内容 | 违反历史保留原则 |
| 手动归档文档 | 应由 CI 自动执行 |
| 删除归档文档 | 丢失历史参考 |

---

**最后更新**：{self.current_date} | 由 CI 自动维护
"""

        return readme_content

    def update_all_readmes(self):
        """更新所有导航 README"""
        print("🔄 开始更新导航文档...")

        # 更新 requirements/README.md
        req_readme = self.generate_requirements_readme()
        req_path = self.base_path / "requirements" / "README.md"
        with open(req_path, 'w', encoding='utf-8') as f:
            f.write(req_readme)
        print(f"  ✅ 更新 {req_path}")

        # 更新 plans/README.md
        plan_readme = self.generate_plans_readme()
        plan_path = self.base_path / "plans" / "README.md"
        with open(plan_path, 'w', encoding='utf-8') as f:
            f.write(plan_readme)
        print(f"  ✅ 更新 {plan_path}")

        # 更新 archive/README.md
        archive_readme = self.generate_archive_readme()
        archive_path = self.base_path / "archive" / "README.md"
        with open(archive_path, 'w', encoding='utf-8') as f:
            f.write(archive_readme)
        print(f"  ✅ 更新 {archive_path}")

        print("✅ 导航文档更新完成")


def main():
    """主函数"""
    updater = DocNavigationUpdater()
    updater.update_all_readmes()


if __name__ == "__main__":
    main()