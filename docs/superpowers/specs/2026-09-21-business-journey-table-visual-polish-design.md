# 业务旅程表格名称与阶段视觉优化设计

- 日期：2026-09-21
- 状态：已确认，待实施
- 范围：业务旅程表格的旅程名称链接样式、当前阶段标签配色
- 非范围：本轮不增加「新建商机」入口，不修改业务旅程查询、权限、保存视图或详情 Sheet 行为

## 1. 问题

业务旅程表格目前有两处与系统既有列表页及看板视觉不一致：

1. 「旅程名称」是普通文本；客户、商机、合同等列表的主要识别字段使用蓝色链接样式提示可查看详情。
2. 「当前阶段」统一使用中性 Badge；同一业务阶段在看板中已有稳定颜色语义，但表格没有复用。

## 2. 方案比较

### 方案 A：共享阶段展示配置（采用）

把看板现有阶段颜色映射提取为业务旅程共享展示配置，表格和看板共同引用。

- 优点：阶段颜色只有一个事实来源；看板视觉不变；表格无需复制映射。
- 代价：新增一个很小的业务展示配置文件，并调整两个消费者导入。

### 方案 B：表格单独维护阶段颜色

仅在 `BusinessJourneyTableView.vue` 新增一份映射。

- 优点：改动最少。
- 缺点：形成第二套颜色配置，阶段新增或改色时容易漂移。

### 方案 C：按阶段拼接动态 Tailwind class

根据 stage key 生成类名。

- 优点：代码表面更短。
- 缺点：动态类名不利于 Tailwind 静态扫描，也把业务语义隐含在字符串规则中。

## 3. 视觉与交互设计

### 3.1 旅程名称

- 在 `BusinessJourneyTableView` 的 `cell-name` slot 中渲染蓝色链接文本。
- 样式复用现有列表页语义：`$wolf-text-link-v2`、中等字重、pointer cursor，hover 使用 `$wolf-text-link-hover-v2`。
- 点击名称调用现有 `handleRowClick(row)`，打开同一个业务旅程 Sheet。
- 点击名称使用 `stop`，避免与整行点击重复触发。
- DataTable 既有整行点击和命名详情入口保持不变，不增加第二套详情逻辑。

### 3.2 当前阶段标签

表格使用看板同色系的浅色 Badge，不使用看板卡片内的实心强调 Badge，避免表格视觉过重：

| 阶段 key | 表格 / 看板色系 |
|---|---|
| `early_communication` | sky：浅蓝底、深蓝字 |
| `active_progress` | blue：蓝底、蓝字 |
| `closing_soon` | emerald：浅绿底、绿字 |
| `contract_processing` | violet：浅紫底、紫字 |
| `payment_processing` | amber：浅琥珀底、琥珀字 |
| `invoice_processing` | cyan：浅青底、青字 |
| `completed` | slate：浅灰底、灰字 |
| `lost` | rose：浅红底、红字 |

共享配置包含：

```ts
Record<DealJourneyBoardStage, {
  columnClass: string
  badgeClass: string
  emphasisBadgeClass: string
}>
```

- `BusinessJourneyBoardView` 继续使用 `columnClass`、`badgeClass` 和 `emphasisBadgeClass`，视觉保持不变。
- `BusinessJourneyTableView` 使用 `badgeClass`。
- 阶段文案保持现有接口返回的 `current_board_stage_label`；只在缺失时使用既有 fallback，不顺带改名。

## 4. 组件边界

新增：

- `CRM-Client/src/components/business-journey/businessJourneyStagePresentation.ts`

修改：

- `CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue`
- `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue`
- 对应组件行为测试

不新增 UI 组件，不修改通用 `Badge`、`DataTable` 或全局 Button。

### 4.1 设计系统治理

阶段色是既有看板业务编码，当前由 `DS-EX-004` 精确白名单保护。颜色 class token 移入共享配置后：

- `DS-EX-004.files` 增加 `businessJourneyStagePresentation.ts` 和新的表格测试文件。
- 看板组件若不再直接包含阶段色 class，可从例外文件列表移除；年龄色仍留在看板组件时继续保留。
- 白名单仍只接受当前明确列出的 class token，不能恢复按整组色阶放行的宽泛正则。
- `DS-EX-005` 的原始 RGB 列背景仍留在 `BusinessJourneyBoardView.vue`，本轮不移动、不扩展。

## 5. 验证

行为测试覆盖：

1. 旅程名称呈现现有蓝色链接语义，点击只发出一次既有 row-click payload。
2. 八个阶段分别呈现与看板一致的浅色 Badge class。
3. 看板仍使用原阶段列背景、计数 Badge 和实心强调 Badge。
4. 未知阶段不进入页面：前端 Zod enum 继续作为输入边界。

运行：

- `BusinessJourneyTableView` focused test
- `BusinessJourneyBoardView` focused test
- `BusinessJourneys` page focused test
- 真实浏览器检查表格名称、八阶段颜色和详情点击

## 6. 验收标准

- 旅程名称与现有客户/商机/合同主识别列一样显示为蓝色可查看文本。
- 点击旅程名称和点击行打开相同的业务旅程 Sheet，且不会重复打开。
- 当前阶段的颜色与看板对应阶段一致。
- 看板视觉、筛选/排序、保存视图、表格高度和移动端行为不回归。
- 页面右上角不出现「新建商机」。
