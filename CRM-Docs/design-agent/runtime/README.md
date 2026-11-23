# 运行时规范

本目录按主题说明销售助手 `/assistant` 的运行时契约。

| 主题 | 使用场景 |
| --- | --- |
| [结构化输出](structured-output.md) | 定义 AI 输出 schema、校验和 fallback 行为。 |
| [跟进质量评估](follow-up-quality.md) | 定义跟进记录创建前的质量评分、补充问题和阈值策略。 |
| [交互编排策略](interaction-policy.md) | 选择单轮唯一用户交互动作和动作优先级。 |
| [Agent UI 平台边界](agent-ui-platform.md) | 读取任务投影、发起当前交互、展示回执和只读历史。 |
| [销售助手命令契约](assistant-command-contract.md) | 冻结确认、幂等、目标效果、对账权限及恢复。 |

[返回 Agent 根入口](../README.md)
