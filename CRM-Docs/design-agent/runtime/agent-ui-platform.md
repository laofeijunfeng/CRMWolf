# CRM Agent UI 平台边界

`/assistant` 的销售助手任务表仍是业务权威。Web 只渲染 `crm.agent.ui.v1` 的 blocks，入口是 `AgentUIMessage`。`ConversationMessage.text` 继续保存，供搜索和没有界面时回看，页面不再把它和卡片一起画出来。

投影在读取对话时完成，不另写一份任务状态。一条助手消息只有一个需要回应的交互：

| 来源 | 可见块 |
| --- | --- |
| 普通回复 | TextBlock |
| 边界选择、客户/商机/活动类型、时间候选 | choice InteractionBlock |
| 缺字段 | text_input InteractionBlock，可另附已确认事实 |
| 活动或提案确认 | confirmation InteractionBlock，事实只来自冻结预览 |
| 活动已写入 | ActionResultBlock |
| 已分类失败 | ErrorBlock，标题看错误码，不看句子 |
| 未知提交结果 | NoticeBlock，不提供盲目重试 |
| 历史交互 | READ_ONLY，没有 submit_action_id |

交互提交仍翻译成现有 assistant command / choice。时间消歧的手动日期仍走底部输入框和同一个等待。确认旁边的「修改内容」「改为线下 / 跟进」是次要命令，不是第二个交互块。

不在这条页面上新做查询列表或后台异步任务列表。共享 block 的圆角和边框跟随 CRMWolf 面板，不改全局色板。
