# 质量门禁

- **用途：**定义 Agent 文档和实现的最低质量检查。
- **适用范围：**Agent PR、需求变更、功能扩展。
- **权威性：**本文件拥有 Agent 质量门禁规则。
- **相关规范：**[文档写作](authoring.md) · [权限边界](permission-boundary.md)

## 文档检查

- 每个 Markdown 文件不超过 100 行。
- 新增主题必须从根 README 可达。
- 规则冲突时更新唯一事实来源。

## 语义检查

顶层自然语言意图路由不得使用正则、关键词或硬编码分类来替代结构化语义判断。这个边界与 [ADR 0002](../../../docs/adr/0002-root-semantic-route-recovery.md) 中旧 Agent 的路由教训一致，但不把旧 Root 架构带入 `/assistant`。`temporal_evidence.py` 只做日历计算和交叉核对，不得作为时间语义的唯一来源（详见 [ADR 0006](../../../docs/adr/0006-assistant-temporal-model-structured.md)）。

语义结果必须由 AI structured output 产生，并通过 schema 校验。

## 写命令检查

业务写入以当前用户身份，经领域写服务及访问策略完成。

检查签发确认、冻结载荷、团队与对象权限、幂等、防重放及未知结果的恢复边界。

## 观测检查

按轮次和阶段关联模型调用、错误、写命令及确认状态；用户按服务端事件和回执区分处理中、确定失败、结果待核对和已提交。
