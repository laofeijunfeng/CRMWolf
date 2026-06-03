"""AI 对话胶水层

提供从用户口语 → 意图解析 → 槽位收集 → 预览确认 → 执行的完整对话流程。

三层归属模型:
- L1: CRM Core (/api/v1/) - 业务数据一致性、权限、事务
- L2: AI 能力 API (/ai/) - 原子动作、preview/execute、风险分级
- L3: 对话胶水层 (glue/) - 消息处理、状态机、意图解析、歧义消解
- L4: 渠道适配 (glue/channels/) - webhook 验签、文本收发

红线约束:
- glue/ 禁止直接操作 CRM Core Models
- 所有写必须过 /ai/actions/ 的 preview→execute 双步
- 风险规则权威在 ai_rules.py + /ai/metadata/

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md
"""

__version__ = "0.1.0"