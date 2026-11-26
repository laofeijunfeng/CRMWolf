# ADR 0006：销售助手时间结构化提取与同句共用时间动作合并

- **状态：**已接受（CRM-170 方案 1A + 2A）
- **日期：**2026-11-27
- **范围：**销售助手时间契约（`ModelTemporalMention`）、服务端日历计算与交叉核对（`temporal_evidence.py`、`action_evidence.py`）、同句共用时间销售动作合并、非空跟进时间兜底及模型能力探测；不改角色判定、不改确认卡视觉、无数据库迁移。

## 背景

1. 同句里共用一个日期的多个销售动作（如「明年 2 月 26 号再找尚老师跟进使用情况，同时提供新版本进行更新」）原先只把日期绑到首分句，后续动作被视为无日期销售动作并触发 `PRIMARY` 选哪项；用户选中后 `next_follow_time` 被静默清空。
2. 时间语义长期靠服务端正则逐条补语法，导致「明年二月二十六号」「明年2月26」「三天后」「2/26」无法解析，「下下周三」误匹配为「下周三」且无提示。

## 决策

1. **模型输出结构化时间字段**：`ModelTemporalMention` 新增可选字段 `year` / `year_offset`、`month` / `month_offset`、`day`、`week_offset` + `weekday`、`day_offset`、`segment`（`EARLY|MID|LATE|WHOLE_MONTH`）、`vague`、`clock`（24h `HH:MM`）。严格限制枚举与取值区间，禁止接收 ISO 日期；字段越界按 schema 校验失败关闭。全部字段缺省保持旧行为，兼容历史缓存。
2. **服务端单一计算入口**：`compute_temporal(mention, anchor)` 作为唯一日历计算入口，返回 `RESOLVED`、`INVALID_DATE` 或 `UNRESOLVED`。`temporal_evidence._resolve_kind` 与 `action_evidence.parse_deadline` / 截止日期扫描统一走同一入口，不再保留第二套日期语法。模型引用仍须通过 `validate_temporal_quotes`。
3. **正则降级为交叉核对**：正则仅用于交叉核对，不得作为时间语义唯一来源（同步更新 `CRM-Docs/design-agent/governance/quality-checks.md`）。同一引用区间双方均解析且日期/时刻/粒度冲突时，两侧弃用并进入 `AMBIGUOUS`（`DATE`）追问；正则未命中时采用模型结构化结果；正则已要求追问（如裸日期月份歧义或非法日期）时保留追问。
4. **同句共用时间动作合并**：同一句内多个 `SALES`/`PLANNED` 动作共用唯一时间且由「同时/并/顺便/另外/再/逗号」相连、中间无其他时间时，按原文顺序以「，并」合并为一个下一步并共享 mention。不同时间不合并，仍发起 `PRIMARY` 追问且选项标签追加「（YYYY-MM-DD）」。
5. **非空跟进时间兜底与能力探测**：存在已解析 `SALES_FOLLOW_UP` 日期而最终 `next_follow_time` 将为空（且非 `EXPLICITLY_NONE`）时，禁止静默清空，强制进入 `DATE` 追问。`model_capabilities.py` 探测样例加入「下下周三」并校验 `week_offset=2`、`weekday=3`。

## 结果与风险

- 中文数字、无「号/日」日期、相对天数、斜杠日期和跨多周周几不再依赖堆正则；非法日期（如 2 月 30 号）进入 `INVALID_DATE` 追问，模糊时间（如「春节后」）进入具体日期追问，不写错日期。
- 风险：未通过新结构化探测的模型会在能力验证 `MEETING_STREAM` 阶段被拒绝认证；旧模型或未携带结构化字段的历史草稿因字段全可选，加载不受影响。

## 验证与回滚

- 单元测试覆盖 CRM-170 全部验收场景（1–10）、边缘场景（合并后更正、跨年、引用不一致、客户承诺不合并）及 CRM-44～98 时间回归。
- 回滚只需还原代码；无数据库迁移，不破坏既有持久化证据包。
