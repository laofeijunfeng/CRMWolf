# CRM Agent UI 平台边界

`/assistant` 的销售助手任务表仍是业务权威。Web 只渲染 `crm.agent.ui.v1` 的 blocks，入口是 `AgentUIMessage`。`ConversationMessage.text` 继续保存，供搜索和没有界面时回看，页面不再把它和卡片一起画出来。

投影在读取对话时完成，不另写一份任务状态。一条助手消息只有一个需要回应的交互：

写入确认前只说明将执行什么，不得声称已完成；确认后也必须以服务端权威回执为准。一条最终回复只能有一个主确认目标：需要确认活动时，不同时展示等待决策的后续建议。确认/取消和同一确认目标的次要编辑命令不构成多个主交互。

| 来源 | 可见块 |
| --- | --- |
| 普通回复 | TextBlock |
| 边界选择、客户/商机/活动类型、时间候选 | choice InteractionBlock |
| 缺字段 | text_input InteractionBlock，可另附已确认事实 |
| 活动或提案确认 | confirmation InteractionBlock，事实只来自冻结预览 |
| 活动、商机或任务操作已提交 | ActionResultBlock，展示权威回执；可用时附 `entity_ref`，创建商机进入审批时标注“待审批” |
| 已分类失败 | ErrorBlock，标题看错误码，不看句子 |
| 未知提交结果 | NoticeBlock，不提供盲目重试 |
| 历史交互 | READ_ONLY，没有 submit_action_id |

P1 投影约定（接入后适用，不作验收声明）：

| 来源 | 可见块 |
| --- | --- |
| 接受商机创建提议后的补录、活动确认前就地编辑 | form InteractionBlock，表单提交走服务端签发的等待；前一步“是否创建”不授权写入 |
| 未完成任务汇总处置 | `selection_mode="multiple"` 的 choice InteractionBlock；单次提交，逐条复核与独立提交 |
| 汇总处置结算 | 展示逐条结果，区分已完成、保持、过期、失败或待核对；不以整体成功掩盖部分失败 |

交互提交仍翻译成现有 assistant command / choice。时间消歧的手动日期仍走底部输入框和同一个等待。确认旁边的「修改内容」「改为线下 / 跟进」是次要命令，不是第二个交互块。

不在这条页面上新做查询列表或后台异步任务列表。共享 block 的圆角和边框跟随 CRMWolf 面板，不改全局色板。

命令权限、幂等和恢复见[销售助手命令契约](assistant-command-contract.md)。
