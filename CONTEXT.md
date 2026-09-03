# CRMWolf Domain Context

## 当前领域

本上下文记录 CRMWolf 客户活动（跟进记录、会议纪要）从旧 Agent 流程迁移到统一 Workflow 的稳定术语和不变量。具体实施合同、Parity Matrix、验收用例和代码状态分别见：

- `CRM-Docs/design-agent/roadmap/legacy-workflow-parity-matrix.md`
- `CRM-Docs/design-agent/roadmap/customer-activity-workflow-parity-spec.md`
- `CRM-Docs/design-agent/roadmap/customer-activity-workflow-acceptance-matrix.md`
- `CRM-Docs/design-agent/roadmap/customer-activity-workflow-implementation-status.md`
- `docs/adr/0001-customer-activity-workflow-parity.md`

## 领域词汇

- **客户活动（Customer Activity）**：客户下的跟进记录或会议纪要。本期只有“新增”和“删除”，没有修改操作。
- **Agent 路径**：用户通过 Agent 输入并完成语义解析、整理、评分和下一步行动门禁后，直接一次性写入最终活动。
- **页面表单路径**：用户通过页面表单提交原始活动，接口立即保存并登记 durable `CustomerActivityAIJob`，由后台异步完成整理、评分和既有后处理。
- **最终评分（Final Evaluation）**：canonical evaluator 对最终整理稿产出的唯一业务评分。只保存最终结果，不保存中间分数、评分历史或补充前低分过程。
- **下一步行动门禁（Next-action Gate）**：评分通过后对下一步行动进行的独立判断。缺失或模糊行动需要追问；明确动作无时间不猜日期；明确暂无下一步时保留原因或复查条件。
- **AIJob**：页面表单活动的 durable 整理/评分任务。它可 claim、续租、恢复、重试和在活动删除或 revision 过期时静默跳过。
- **PostCommitJob**：活动最终写入后的 durable 后处理任务，承接既有任务投影、客户智能刷新等副作用。它不阻塞、不回滚活动事实。
- **商机建议**：活动完成后独立生成的商机候选/建议，不属于活动写入事务。高置信度匹配已有商机时静默去重；创建新商机需 Agent UI 确认并使用页面内嵌表单。
- **操作原子（Command Atomicity）**：创建客户、创建活动、创建商机、推进商机阶段分别是独立原子；一个原子失败不能回滚另一个已成功原子。
- **Activity Revision**：活动最终化后的版本栅栏。后台任务必须校验版本，不能用旧结果覆盖新事实。
- **Checkpoint 记忆**：Workflow 为恢复交互保存的最新 JSON-safe 领域状态，包括已确认客户引用；补充轮次默认复用客户，不重复搜索，除非用户明确切换客户。
- **Cutover watermark**：T20 一次性历史切换第一次运行确定的时间水位；后续重跑不得扩大范围。
- **Cutover evidence**：迁移运行键、watermark、接管/跳过/替代/保留计数的持久证据，固定运行键完成后重跑为 no-op。

## 稳定不变量

1. Agent 活动必须携带最终整理稿和最终评分一次写入，不创建 AIJob，不重复评分。
2. 页面表单活动先保存原始内容并创建 AIJob；接口不等待模型，不提前创建 PostCommitJob。
3. 活动评分、客户智能、任务投影和商机建议彼此独立；后台失败不能回滚主活动。
4. 低于 60 分的 Agent 活动不写入、不创建商机建议，只问一个最关键的补充问题；补充后重新解析完整用户语义。
5. 客户未匹配时只说明“没有匹配客户”，不自动创建客户、不创建线索。
6. 本期范围止步于商机，不实现线索、回款、合同等后续业务。
7. 活动删除不新增“删除评分”；后台任务保留证据并静默标记为跳过，不能继续写回。
8. 前端活动列表和详情展示方式保持不变；商机确认使用 Agent UI 的确认组件和内嵌表单，不使用旧重型弹窗。
9. 旧活动修改、手工 process/evaluate、同步模式和旧处理 service 不作为长期兼容轨保留。
10. T20 只接管未完成历史活动；已完成活动不重新整理、不重新评分；旧 PostCommitJob 按活动最终化状态分别替代、保留或跳过。
11. `activity_kind` 是客户活动唯一 canonical 字段；旧 `method` 只允许在线索历史边界适配器中转换，不能回到客户活动运行时主链路。
