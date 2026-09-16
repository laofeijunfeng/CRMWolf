# 回款计划合计不超过合同金额

- 日期：2026-09-16
- 状态：已确认方向，待书面审阅
- 范围：回款计划创建/编辑弹窗；`PaymentPlanCRUD.batch_create` / `create` / `update`；商机详情传入的 `fixedContract.total_amount`
- 上游决定：所有创建和编辑入口；填写时前端即时红字，不边填边请求；本地超限拦住提交；后端按合同下全部计划重算兜底；统一预填剩余可分配金额；编辑只拦「会让合计更高」的改动；弹窗自己按合同拉计划合计（方案 A）
- 相关规范：`CRM-Docs/design-system/patterns/form-page.md`、`CRM-Docs/design-system/components/input.md`
- 相关实现：`CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue`、`CRM-Client/src/components/panels/OpportunityDetailContent.vue`、`CRM-Client/src/components/ContractPaymentPlans.vue`、`CRM-Client/src/views/PaymentPlans.vue`、`CRM-Server/app/crud/payment.py`、`CRM-Server/app/api/payments.py`

## 1. 背景与目标

合同金额 40000、已有一笔回款计划 12000 时，再创建第二笔可以填 30000 并保存成功，合计变成 42000。

原因：

- 前端 `PaymentPlanFormDialog` 只校验金额 `> 0`，没有和合同总额、已有计划比较。
- 商机详情会把第二笔预填成剩余 28000，但预填可改，改完不拦截。
- 合同页 / 回款计划列表预填的是合同总额，不是剩余可分配。
- 后端 `batch_create` 只加**本次请求**的金额，不计库里已有计划。接口文案写「所有阶段之和不能超过合同总金额」，实现没做到。
- `update` 完全不校合同合计。`PaymentPlanCRUD.create` 现在没有调用方，同样没有合计校验。

目标：

1. 同一合同下全部回款计划 `planned_amount` 之和不得超过该合同 `total_amount`。等额允许。
2. 填写或修改金额时，用页面已加载的合同额和已有计划合计即时提示，不边填边请求。
3. 本地已超限时拦住提交，不发请求、不 toast。
4. 后端按库里该合同全部计划重算，作为并发、脏数据、Agent 和其他入口的门禁。
5. 所有创建入口预填剩余可分配金额，不再把剩余额塞进 `fixedContract.total_amount`。

## 2. 非目标

- 不改回款登记「累计实收 ≤ 该计划金额」规则。
- 不改开票金额相对计划金额的规则。
- 不给合同列表/详情 API 增加 `allocated_planned_amount`。
- 不使用 `payment-summary.remaining_amount`。该字段是「计划合计 − 已回款」，不是可分配余额。
- 不在金额变化时请求后端。
- 不禁用提交按钮。超限时按钮可点，本地校验失败不发请求。
- 不把商机详情「分完隐藏创建」扩到合同页和回款计划列表。
- 不改 Agent 前端即时校验。Agent 走同一 create API，只吃后端 400。
- 不做历史超限数据自动纠偏。编辑只拦继续抬高合计。
- 不改合同金额本身，也不在改合同金额时重算已有计划。

## 3. 方案选择

采用「弹窗按合同拉计划合计 + CRUD 按库里全部计划重算」。

放弃：

- 调用方传入剩余可分配：商机详情改动小，但三个入口各算一遍，`fixedContract.total_amount` 继续被当成剩余额。
- 合同接口带已分配合计：少一次请求，但合同 API 和前端类型一起改，超出这次校验范围。

上限计算收口在 `PaymentPlanFormDialog` 和 `PaymentPlanCRUD`。入口只负责打开表单。

## 4. 不变量

同一合同下：

```text
Σ PaymentPlan.planned_amount  ≤  Contract.total_amount
```

金额列都是 `Numeric(12, 2)`。比较量化到分（`0.01`），等额通过。

编辑时的放行条件：改完后的合计不高于改前合计，即使改前已经超限。只有「改完合计比改前高，且改完合计超过合同额」才拒绝。

## 5. 前端交互

入口：商机详情、合同回款计划、回款计划列表。创建和编辑都走 `PaymentPlanFormDialog`。

### 5.1 预填

合同 ID 和已有计划就绪后：

```text
已分配 = Σ 该合同其他计划 planned_amount
         （新建：全部已有；编辑：全部已有 − 本笔原金额）
剩余可分配 = max(0, 合同总额 − 已分配)
```

- 新建：金额框填剩余可分配的十进制字符串（例如 `28000`）。剩余为 0 时金额框保持空字符串，不填 `0`（`0` 过不了「大于 0」校验）。
- 编辑：金额框仍填本笔原金额，不改成剩余额。
- 换合同后按新合同重算并覆盖金额框（仅新建）。计划尚未返回前金额框保持空，禁止先填合同总额再改成剩余额。

例子：合同 40000、已有 12000 → 打开第二笔默认 28000。

### 5.2 帮助文字

金额框未超限时，用 `InputField` 的 `helperText`：

```text
还可分配 {formatCurrency(剩余可分配)}
```

例如 `还可分配 ¥28,000.00`。金额展示复用 `@/utils/format` 的 `formatCurrency`，不手拼 `¥`。

计划列表或合同总额尚未就绪时，不写剩余额，也不用合同总额冒充剩余。

### 5.3 红字时机

已输入的金额一变就算。不 toast、不禁用按钮。`InputField` 已在输入时同步 `v-model`。

| 条件 | 何时 | 字段错误 |
|---|---|---|
| 空字符串 | 仅提交 | `请输入大于 0 的计划金额` |
| 非数字或 `≤ 0` | 输入时 | `请输入大于 0 的计划金额` |
| 新建，且填写额（分）> 剩余可分配（分） | 输入时 | 超限文案 |
| 编辑，且改完合计（分）> 改前合计（分），且改完合计（分）> 合同总额（分） | 输入时 | 超限文案 |
| 编辑，改小 / 改阶段 / 改日期 / 改备注，即使合计仍超 | — | 不因合同总额红 |
| 计划或合同总额未就绪 | — | 不做超限红字 |

空金额不在打开时立刻报「大于 0」，否则 `InputField` 的 error 会盖住「还可分配」帮助文字。剩余为 0 且金额为空时，只显示 `还可分配 ¥0.00`；用户填了任何 `> 0` 再出超限红字。

超限文案：

```text
回款计划合计不能超过合同金额 {formatCurrency(合同总额)}，当前还可分配 {formatCurrency(剩余可分配)}
```

编辑且合计已超、剩余为 0：`当前还可分配 ¥0.00`。

本地超限或提交时金额非法：`validateForm()` 失败，不发请求，红字留在字段上。不额外 toast。

前端金额比较用分：`Math.round(Number(value) * 100)`，与后端 `Decimal` 量化到 `0.01` 对齐。不要用裸 `float` / 裸 `Number` 累加后直接 `>`。

### 5.4 计划列表失败

拉计划或编辑时拉合同失败：不编造剩余、不预填剩余额、不做超限红字。阶段/日期等本地校验仍生效。空金额仍报「大于 0」。提交仍走后端，由 400 toast 兜底。

### 5.5 剩余为 0 时的新建

- 商机详情继续用自己的计划列表判断 `isPaymentPlanAmountComplete`，分完隐藏创建按钮。这是入口收口，不是弹窗校验。
- 合同页、回款计划列表仍可打开弹窗。金额框为空，帮助文字 `还可分配 ¥0.00`；填任何 `> 0` 立刻红，提交被本地拦住。

## 6. 数据流

弹窗自己拿合同总额和已有计划。调用方不再把剩余额塞进 `total_amount`。

```text
打开弹窗 / 选中合同 / 进入编辑
  → 确定 contractId
  → GET /v1/payments/contracts/{id}/payment-plans   （一次，不是边填边拉）
  → 合同总额：fixedContract 或合同列表项；仅列表页编辑才 GET /v1/contracts/{id}
  → 计算已分配、剩余可分配
  → 新建预填剩余；编辑保留本笔原金额
  → 金额输入时用本地数字即时校验
        ↓ 本地通过
POST /v1/payments/contracts/{id}/payment-plans
  或 PUT /v1/payments/payment-plans/{id}
        ↓ 后端按库重算
成功 / 400
```

### 6.1 合同总额来源

| 场景 | 来源 |
|---|---|
| 新建 + `fixedContract` | `fixedContract.total_amount`，必须是合同总额 |
| 新建 + 自选合同 | `contracts` 列表里选中项的 `total_amount` |
| 编辑 + `fixedContract` | 同样用 `fixedContract.total_amount`，不再打合同详情。商机详情和合同页编辑都传了固定合同 |
| 编辑且无 `fixedContract` | `plan.contract_id` → `contractApi.getContract` 的 `total_amount`。回款计划列表编辑走这条。计划对象没有合同总额 |

不要用 `GET /v1/payments/contracts/{id}/payment-summary` 的 `remaining_amount`。

### 6.2 调用方

- `OpportunityDetailContent.vue`：`fixedContractForPaymentPlan.total_amount` 改回 `contract.total_amount`。不再传 `remainingPaymentPlanAmount`。
- `ContractPaymentPlans.vue`：已经传合同总额，保持。
- `PaymentPlans.vue`：继续不传 `fixedContract`，选客户/合同后由弹窗拉计划。

三个入口都不向弹窗传入已分配合计。商机详情「分完隐藏创建」继续用自己的 `paymentPlans` 列表，与弹窗校验独立。

### 6.3 请求时机

只在合同 ID 确定时拉一次计划：打开固定合同、换下拉合同、进入编辑。金额每次按键只用内存里的合计，不请求。

## 7. 后端门禁

最终事实在 `PaymentPlanCRUD`，不在 API 层重复一套。API 继续把 `ValueError` 转 400，`detail` 原样返回。前端 `handleApiError` 对 400 已经 toast「创建/更新回款计划失败」+ `detail`。

### 7.1 合计断言

抽出同一套函数，`create` / `batch_create` / `update` 都走它。`create` 现在没有调用方，也接上，避免以后绕过。

用 `Decimal`，量化到分：

```python
TWOPLACES = Decimal("0.01")

def as_money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES)
```

比较前把合同总额、已有计划、本次金额都 `as_money`。禁止 `float(contract.total_amount)`。

### 7.2 创建

同一事务：

1. `SELECT Contract … WHERE id = :contract_id FOR UPDATE`（对齐现有回款登记对计划行的 `with_for_update`）
2. 读该合同全部已有 `PaymentPlan.planned_amount`
3. `已有合计 + 本次请求全部金额 > 合同总额` → `ValueError`

`create()` 走同一锁和断言，本次金额就是这一笔。一次请求里两笔 20000 + 20001 按 40001 算，不是只看第一笔。等额通过。

### 7.3 更新

同样锁合同行后重算。

```text
改前合计 = 该合同全部计划（含本笔原金额）
改后合计 = 改前合计 − 本笔原金额 + 新金额
```

拒绝当且仅当：`改后合计 > 改前合计` 且 `改后合计 > 合同总额`。

放行：改小、改阶段/日期/备注、金额未变，即使改前已经超限。

未改 `planned_amount` 时不走「抬高合计」分支。

### 7.4 并发

两人同时看到剩余 28000、都提交 28000：先提交的成功（合计 40000），后提交的等锁后看到已有 28000，400。不锁合同行会出现双过。不升全局隔离级别。

### 7.5 错误文案

```text
回款计划总额({合计})不能超过合同总额({合同额})
```

数字用量化后的金额，避免 `40000.0000000001`。与现有 `batch_create` 文案句式一致，只是合计含义改为「已有 + 本次」或「改后全部」。

Agent `create_payment_plan` 走同一 `POST /v1/payments/contracts/{id}/payment-plans`，只吃这条 400。

## 8. 测试与验收

### 8.1 后端

在 `CRM-Server/tests/unit/test_payment_plan_crud.py` 扩展，覆盖合计逻辑。假查询要能返回合同下已有计划，不能只返回合同对象。

合同 40000：

- 已有 12000，再 `batch_create` 30000 → `ValueError`，文案含合同总额
- 已有 12000，再 `batch_create` 28000 → 成功
- 无已有，一次请求 `[20000, 20001]` → 失败
- 无已有，一次请求 `[20000, 20000]` → 成功
- `update` 把 12000 改成 41000（无其他计划）→ 失败
- 已有 12000 + 30000（历史超限），把 30000 改成 25000 → 成功
- 同上，只改阶段名、不改金额 → 成功
- `create()` 在已有 12000 时再写 30000 → 失败（与 `batch_create` 同一断言）
- 比较使用分：合同 `40000.00` + 已有 `12000` + 本次 `28000.00` 通过；本次 `28000.01` 失败。不要用 `float` 累加。

不要求单测真实并发锁。规格要求 `create` / `batch_create` / `update` 在合计前对合同行 `with_for_update`。

### 8.2 前端

在 `PaymentPlanFormDialog.test.ts` 增加行为测试。现有关闭/success 用例必须 mock `paymentApi.getPaymentPlans` 返回 `[]`，否则打开弹窗会请求计划列表；它们传入 `total_amount: 100` 且填写 `100`，无已有计划时应仍通过。

- 固定合同 40000，mock 已有计划 12000：打开且计划返回后金额框为 `28000`；帮助文字含 `还可分配 ¥28,000.00`
- 把金额改成 30000：字段立刻出现超限红字；点提交不调用 `createPaymentPlans`
- 改回 28000：红字消失，提交调用接口
- 编辑计划原金额 12000、合同 40000、另有 30000：打开不因已超红；把 12000 改成 13000 红；改成 11000 不红
- 拉计划失败：不出现超限红字；提交仍调用接口
- `OpportunityDetailContent.vue` 的 `fixedContractForPaymentPlan.total_amount` 使用 `contract.total_amount`，不得把 `remainingPaymentPlanAmount` 赋给 `total_amount`。用与 `PaymentPlansContract.test.ts` 相同的源码契约测试钉住，不挂完整弹窗交互。

不测合同页「分完仍显示创建按钮」。那是有意保留。

### 8.3 手工场景

合同 40000：

1. 商机详情创建第一笔 12000，再打开第二笔，默认 28000。
2. 改成 30000，金额框下红字，提交无 toast、无新计划。
3. 改成 28000，保存成功。
4. 合同页 / 回款计划列表再打开新建，默认 0 可分配或立刻红。
5. 两人几乎同时用剩余 28000 创建：一个成功，一个 400 toast。

## 9. 文件

- 修改 `CRM-Server/app/crud/payment.py`：合计断言、锁合同行、`create` / `batch_create` / `update` 接入
- 修改 `CRM-Server/tests/unit/test_payment_plan_crud.py`
- 修改 `CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue`
- 修改 `CRM-Client/src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts`
- 修改 `CRM-Client/src/components/panels/OpportunityDetailContent.vue`：`fixedContract.total_amount` 改回合同总额
- 不改 `CRM-Server/app/api/payments.py` 的路由形状；400 映射保持 `ValueError` → `detail`
- 不改合同 schema、payment-summary 语义、回款登记金额规则

## 10. 风险

- 回款计划列表新建要等选合同后再拉计划。选合同到计划返回前金额框保持空，不要先填合同总额再改成剩余额。
- 回款计划列表编辑要额外打合同详情。失败时降级为「只拦 > 0，提交靠后端」，不要用计划金额冒充合同总额。商机详情和合同页编辑用已传入的 `fixedContract.total_amount`，不打合同详情。
- 商机详情去掉「剩余额当合同额」后，若弹窗还用 `getSelectedContractAmount()` 当预填且计划尚未返回，会短暂预填 40000。预填必须等计划列表就绪。
- 历史合计已超的合同，编辑改小可以保存，创建新笔会被拦。不在这次做纠偏向导。
