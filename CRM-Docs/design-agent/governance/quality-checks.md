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

Agent 语义理解不得出现正则、关键词或硬编码分类。

语义结果必须由 AI structured output 产生，并通过 schema 校验。

## Tool 检查

所有业务 tool 必须调用现有 API。

写入 tool 必须有 HITL 测试、权限上下文测试和 payload 校验测试。

## 观测检查

每次请求必须能定位模型、解析来源、fallback、tool 调用和确认状态。

用户能从事件或日志判断是否真正走 AI。
