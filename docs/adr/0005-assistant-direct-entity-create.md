# ADR 0005：销售助手直接新建资料

- **状态：**已接受（CRM-165 方案，用户回复「进入开发」后批准）
- **日期：**2026-11-26
- **范围：**`/assistant` 直接新建联系人、开票抬头、部署信息、客户和商机，跟进后资料提议，以及「待补充」入口；不改 CRM 页面表单与既有 CRM 接口。

## 背景

销售助手原来只处理客户活动，新建资料要跳到页面表单。用户希望一句话说「给华润加个联系人张总 138…」就能在对话里补齐并保存，跟进纪要里出现的新联系人、开票信息和部署地址也能顺手建档。原有不变量「客户未匹配时不自动创建客户」必须保留。

## 决策

1. **一条资料一个任务。**`AssistantTask.task_kind` 区分 `customer_activity` 与五种实体（`contact_create`、`invoice_title_create`、`deployment_create`、`customer_create`、`opportunity_create`），`parent_task_id` 关联跟进任务派生的子任务（迁移 `172_assistant_task_kind`）。每种实体一个表单模块（`app/services/assistant/entity_forms/`），声明字段、校验、写入和查重说明。
2. **只有提交的表单才写入。**模型抽取的值和用户后续打字都只填表（打字算「刚补充」）；表单以 `ENTITY_FORM` 等待签发，提交 `submit_form{form_revision, values}` 后服务端重新校验。取消与「稍后补充」是同一等待的次要动作。
3. **来源标签由服务端生成。**每个字段值带 `FieldSource`（`ORIGINAL`/`DERIVED`/`DEFAULT`/`USER_CHOICE`/`SUPPLEMENT`/`NORMALIZED`/`AUTO_NAME`/`CUSTOMER_DEFAULT`），由 `entity_forms.source_label` 统一转成「来自原文」「按“…”」等文案，前端不推导。
4. **客户须明确。**客户未匹配时只问或给候选；新建客户只能是用户明确发起的 `customer_create` 任务（或表单内显式「新建客户」）并经表单提交，不因未匹配自动创建。
5. **跟进后资料是子任务。**活动提交后，`profile_proposals` 以一个 `PROFILE_PROPOSALS` 选择块列出联系人/开票/部署提议（`go:i` / `skip:i` / `none`），排在商机与后续任务建议之前；选中的提议另开子任务，经「待补充」打开。
6. **「待补充」是导航，不是第二个交互。**`GET /v1/assistant/pending-drafts` 返回本人本团队 ACTIVE 的实体任务（最近修改优先，最多 50 条）；`POST /v1/assistant/conversation/focus` 按会话版本 CAS 切换焦点，有进行中的轮次或待选项时返回 409。不放宽 `command` 的焦点校验。
7. **写入沿用命令账本。**提交先持久化 `proposal_command_claim`，再执行 CRM 写入；联系人、开票、部署、客户的 CRM 事实与 `crm_assistant_crm_effects` 效果（`effect_kind` 同任务类型）同事务提交，商机由 CRM 服务在创建与审批事务里写效果。
8. **重复不是失败。**`DuplicateRecordError` 时 claim 记 `NO_EFFECT`，不覆盖、不重复创建；用户有权查看时给已有记录回执，否则只提示「已存在，请联系负责人」。
9. **提交未知只核对一次。**数据库异常后读一次效果：无效果则 `NO_EFFECT` 并重开表单；读失败或有效果但回执未提交则发布 `UNKNOWN`，不自动重试，交给既有核对员裁决（`adjudicate_entity_claim`）。

## 结果与风险

- 资料在对话里补齐保存，页面表单与接口不变；历史卡片只读。
- 新的等待类型、回执和 `task_kind` 要求前后端同批发布。
- 风险：模型抽取错误只会进入表单，由用户在提交前修正；字段建议每个字段最多 8 个，点选只填充不提交。跟进后资料提议不阻塞活动完成。

## 验证与回滚

- `tests/unit/test_assistant_entity_create.py`、`test_assistant_entity_routing.py`、`test_assistant_api.py` 覆盖路由、表单、查重、权限、未知结果与待补充；Vitest 覆盖字段建议、稍后补充和待补充入口。

回滚需还原代码并降级迁移 172。回滚前先取消或完成 ACTIVE 的实体任务，否则旧版本加载带 `task_kind`/实体草稿的任务会失败；已完成任务的回执不受影响。
