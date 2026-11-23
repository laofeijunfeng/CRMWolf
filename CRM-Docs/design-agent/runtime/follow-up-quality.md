# 跟进质量评估

适用于 `/assistant` 在确认写入前对 `FOLLOW_UP`、`ONLINE_MEETING`、`OFFLINE_MEETING` 的质量门禁。先确定客户与活动类型，再根据用户原文和最终整理稿评分；不推测未表达的事实。

## 评分与结构化结果

评分维度和权重由 [`customer_activity_ai/rules.py`](../../../CRM-Server/app/services/customer_activity_ai/rules.py) 定义，跟进和会议各用相应 rubric，页面表单异步评估复用该领域规则。助手 [`quality_gate.py`](../../../CRM-Server/app/services/assistant/quality_gate.py) 通过共享模型传输发起原生 `json_schema` 请求（兼容模式按团队配置选择），用 Pydantic 校验 `AssistantQualityResponse`：

| 字段 | 含义 |
| --- | --- |
| `score` | 0–100 整数。 |
| `reason` | 非空质量结论。 |
| `principle_scores` | 非空分项列表，每项含 `name`、`score`、`max_score`、`comment`，名称不可重复；校验后转为分项映射。 |
| `supplement_question` | 可空；未达阈值时采用一个最重要的补充问题，无可用模型问题时使用服务端问题。 |

`passed` 由服务端按 `score >= 60` 计算，不由模型声明。模型输出或依赖失败属于技术失败，不用伪造低分引导用户补充。

## 门禁与顺序

- 低于 60 分不写入活动、不发商机建议，本轮只问一个最关键的缺口。客户未确定时先解决客户选择，不与质量问题并发。
- 按 [ADR 0001 §7](../../../docs/adr/0001-customer-activity-workflow-parity.md) 合并补充或修订，评价完整的最终稿，不单独评分最后一句。只持久化最终业务分数。
- 达到 60 分不再要求质量补充，但仍要独立通过下一步行动门禁。`CLEAR` 需有可执行的行动证据，不凭空补时间；`EXPLICITLY_NONE` 保留明确暂无下一步的语义；`MISSING` 或 `VAGUE` 时只追问当前缺口。下一步行动状态不是评分模型返回字段。
- 门禁通过后才展示冻结写入确认；确认执行不重复评分。交互顺序见[交互编排策略](interaction-policy.md)。
