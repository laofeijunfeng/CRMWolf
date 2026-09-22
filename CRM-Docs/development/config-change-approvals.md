# Configuration Change Approvals

本文件记录受 CI 配置锁保护的配置变更。每次修改 `tsconfig.json`、`eslint.config.js` 或 `pyproject.toml`，必须在同一变更中追加审批记录；CI 不接受只有配置文件、没有本文件记录的提交。

## 2026-08-21 — CRM Agent 依赖基线锁定

- **批准范围**：`CRM-Server/pyproject.toml` 中 LangChain、LangGraph、模型 provider 与 Pydantic 的精确版本。
- **批准依据**：`CRM-Docs/requirements/2026-08-21-crm-agent-query-architecture-trd.md` §5.3、§21、§23.1，以及产品负责人于 2026-08-21 发出的按 TRD 开始实施授权。
- **原因**：消除 Agent 运行时依赖漂移，生成带 hash 的 `CRM-Server/requirements.lock`，确保干净环境可重复安装。
- **验证**：`CRM-Server/scripts/verify_agent_dependency_baseline.py` 校验精确版本及 `langchain.agents.create_agent` 导入；CI、Docker 和本地安装统一使用 `pip install --require-hashes -r requirements.lock`。
- **回退约束**：不得恢复 `>=` 的无上界 Agent 依赖声明；后续升级必须新增独立审批记录并通过 Query、Workflow checkpoint/resume 与 structured-output 回归。

## 2026-08-21 — CRM Agent 开发与 CI 工具依赖锁定

- **批准范围**：`CRM-Server/pyproject.toml` 中 `dev` 依赖改为精确版本，并新增 `requirements-dev.txt` / `requirements-dev.lock`。
- **批准依据**：TRD §5.3、§21、§23.1 的干净环境可重复安装门禁，以及产品负责人于 2026-08-21 发出的继续实施授权。
- **原因**：CI 原先在安装生产锁后无约束安装 pytest、Ruff 和 MyPy，仍可能因工具或传递依赖漂移产生不可重复结果。
- **验证**：CI 统一通过两个带 hash 的锁文件安装；依赖校验器同时核对 pyproject、锁文件输入和实际安装版本；全新 Python 3.11 临时环境完成安装、`pip check`、schema 校验和依赖测试。
- **回退约束**：不得恢复 CI 中无版本或无 hash 的 `pip install pytest/ruff/mypy`；开发工具升级必须同步修改精确声明、重新生成锁文件并通过完整门禁。

## 2026-09-21 — Excel 导出依赖（openpyxl）

- **批准范围**：`CRM-Server/pyproject.toml` 生产依赖新增 `openpyxl==3.1.5`，dev 依赖新增 `types-openpyxl==3.1.5.20260827`；同步更新 `requirements.txt`、`requirements-dev.txt` 并重新生成两个带 hash 的锁文件。
- **批准依据**：已批准的规格 `docs/superpowers/specs/2026-09-21-datatable-filtered-excel-export-design.md` §10 依赖交付，以及产品负责人 2026-09-21 对 DataTable 导出方案的批准。
- **原因**：服务端需以 openpyxl write-only 模式生成受控 `.xlsx` 导出；本仓库此前无任何 Excel 生成依赖。
- **验证**：`uv pip compile` 重新生成 `requirements.lock` / `requirements-dev.lock`；`uv pip install --require-hashes` 干净安装；`tests/unit/test_list_export_service.py` 通过；Ruff 与 MyPy 对新增文件零诊断。
- **回退约束**：openpyxl 升级必须保持精确版本并重新生成双锁文件；不得引入运行时动态安装或无 hash 安装路径。
