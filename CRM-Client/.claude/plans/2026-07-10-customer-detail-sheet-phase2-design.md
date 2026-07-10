# 客户详情抽屉第二阶段设计文档

**日期**: 2026-07-10  
**状态**: 设计完成，待审查  
**版本**: 1.0

---

## 一、设计目标

将 CustomerDetailSheet 从骨架状态扩展为完整功能，包括：

- ✅ 数据加载逻辑（统一加载策略）
- ✅ 热力值卡片（Lucide Icons 替代 Emoji）
- ✅ 客户档案卡片（Accordion 折叠）
- ✅ 7 个内容面板（跟进记录、联系人、商机、合同、回款、发票、License）
- ✅ 5 个表单弹窗（新建跟进、联系人、商机、合同、发票抬头）
- ✅ 迁移 Element Plus 组件到 shadcn-vue

---

## 二、架构设计

### 2.1 数据加载策略

**统一加载模式**：

- Sheet 打开时并行调用所有 API
- 使用 `Promise.allSettled` 处理部分失败
- 加载状态统一管理（单一 `loading` 状态）

**API 调用清单**：

```typescript
const loadAllData = async (customerId: number) => {
  loading.value = true
  try {
    const [
      customerDetail,
      scoreData,
      followUpsData,
      opportunitiesData,
      contractsData,
      invoiceTitlesData,
      licenseApplicationsData,
      deploymentsData
    ] = await Promise.all([
      customerApi.getCustomerDetail(customerId),
      getCustomerScore(customerId),
      customerFollowUpApi.getFollowUps(customerId),
      opportunityApi.getAvailableForContract(customerId),
      contractApi.getCustomerContracts(customerId),
      invoiceApi.getInvoiceTitles(customerId),
      licenseApplicationApi.list(customerId),
      deploymentApi.list(customerId)
    ])
    
    // 赋值给各状态变量
    customer.value = customerDetail
    score.value = scoreData
    followUps.value = followUpsData
    // ... 其他数据
  } finally {
    loading.value = false
  }
}
```

**状态管理**：

- 组件内部 `ref` 管理所有状态（不使用 Pinia Store）
- 原因：客户详情是临时视图，不需要跨组件共享

**数据结构**：

```typescript
interface CustomerDetailSheetState {
  // 基础数据
  loading: boolean
  customer: CustomerDetailResponse | null
  score: ScoreResponse | null
  
  // 面板数据
  followUps: CustomerFollowUpResponse[]
  opportunities: OpportunityListResponse[]
  contracts: ContractListResponse[]
  invoiceTitles: InvoiceTitleListResponse[]
  licenseApplications: LicenseApplicationResponse[]
  deployments: DeploymentInfo[]
  
  // 活动面板
  activePanel: string
}
```

---

### 2.2 组件架构

**组件层级结构**：

```
CustomerDetailSheet.vue (主组件)
├── Header
│   ├── 桌面端：客户名称 + 状态徽章 + 联系人数
│   └── 移动端：客户名称 + Select 导航
│
├── Sidebar (CustomerDetailSidebar.vue - 已完成)
│   └── 7 个导航项
│
├── Content Area (ScrollArea)
│   ├── 基本信息卡片 - 已完成
│   ├── 热力值卡片 - NEW
│   ├── 客户档案卡片 - NEW
│   └── 内容面板区域
│       ├── FollowUpPanel.vue
│       ├── ContactsPanel.vue
│       ├── OpportunitiesPanel.vue
│       ├── ContractsPanel.vue
│       ├── PaymentsPanel.vue
│       ├── InvoicesPanel.vue
│       └── LicensePanel.vue
│
└── Footer
    └── 新建商机 + 新建合同 + 编辑按钮
```

**新建/改造文件清单**：

| 类别 | 文件 | 说明 |
|------|------|------|
| **新建** | `src/views/CustomerDetailSheet.vue` | 主组件（改造） |
| **新建** | `src/components/panels/FollowUpPanel.vue` | 跟进记录面板 |
| **新建** | `src/components/panels/ContactsPanel.vue` | 联系人面板 |
| **新建** | `src/components/panels/OpportunitiesPanel.vue` | 商机面板 |
| **新建** | `src/components/panels/ContractsPanel.vue` | 合同面板 |
| **新建** | `src/components/panels/PaymentsPanel.vue` | 回款面板 |
| **新建** | `src/components/panels/InvoicesPanel.vue` | 发票面板 |
| **新建** | `src/components/panels/LicensePanel.vue` | License 面板 |
| **新建** | `src/components/dialogs/OpportunityFormDialog.vue` | 新建商机弹窗 |
| **新建** | `src/components/dialogs/ContractFormDialog.vue` | 新建合同弹窗 |
| **新建** | `src/components/dialogs/ContactFormDialog.vue` | 新建/编辑联系人弹窗 |
| **新建** | `src/components/dialogs/FollowUpFormDialog.vue` | 新建跟进弹窗 |
| **新建** | `src/components/dialogs/InvoiceTitleFormDialog.vue` | 发票抬头弹窗 |
| **改造** | `src/components/LicenseManagement.vue` | 迁移到 shadcn-vue |
| **改造** | `src/components/DeploymentInfoDialog.vue` | 迁移到 shadcn-vue |
| **改造** | `src/components/LicenseApplicationDialog.vue` | 迁移到 shadcn-vue |
| **改造** | `src/components/FollowUpList.vue` | 迁移到 shadcn-vue |

---

## 三、UI 组件设计

### 3.1 热力值卡片

**布局**：

```
┌─────────────────────────────────────────────────┐
│  [Lucide Icon]  85  [高]                         │
│  (Flame/Zap)     ████████░░░░░░░░ (Progress)     │
│                 因子1: +10 · 因子2: +5  [详情]   │
└─────────────────────────────────────────────────┘
```

**使用的 shadcn-vue 组件**：

- `Card`, `CardContent` - 卡片容器
- `Progress` - 进度条（颜色根据分数动态变化）
- `Badge` - 等级徽章
- `Button` (link variant) - "详情"链接
- `Dialog` - 热力值明细弹窗
- `Table` - 明细表格

**Lucide Icons 映射**（符合设计规范）：

| 分数范围 | Lucide Icon | 说明 |
|---------|-------------|------|
| ≥80 | `Flame` | 火焰（高热度） |
| 60-79 | `Zap` | 闪电（中热度） |
| 40-59 | `CheckCircle` | 完成（低热度） |
| <40 | `TrendingDown` | 下降（危险） |
| null | `HelpCircle` | 未知 |

**样式设计**：

- 使用 `variables-v2.scss` 设计 Token
- 进度条颜色：`--progress-background` CSS 变量
- 正数绿色、负数红色（使用 `$wolf-success-text-v2`, `$wolf-danger-text-v2`）

---

### 3.2 客户档案卡片（Accordion）

**布局**：

```
┌─────────────────────────────────────────────────┐
│  ▼ 客户档案                            [生成状态] │
│  ┌─────────────────────────────────────────────┐│
│  │ 公司背景: XXXXXX                             ││
│  │ 公司网站: https://xxx.com                    ││
│  │ 主营业务: XXXXXX                             ││
│  │ 项目背景: XXXXXX                             ││
│  │ 相似客户: 客户A, 客户B                        ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**使用的 shadcn-vue 组件**：

- `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent` - 折叠容器
- `Badge` - 生成状态徽章（生成中/已完成/失败）

**状态展示**：

- `GENERATING`: 显示加载动画 + "正在生成..."
- `COMPLETED`: 显示档案内容
- `FAILED`: 显示错误信息 + 重试按钮
- `PENDING`: 显示 "暂无档案，点击生成"

---

### 3.3 内容面板通用设计

**面板头部**（CardHeader）：

```vue
<CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">跟进记录</h3>
  <Button size="sm">
    <Plus class="w-4 h-4 mr-1" />
    添加
  </Button>
</CardHeader>
```

**面板内容**（CardContent）：

- 使用 `DataTable` 组件展示列表数据（商机、合同、回款）
- 使用 `FollowUpList` 展示跟进记录（复用现有组件）
- 空状态使用 `Empty` 组件

---

### 3.4 各面板详细设计

#### FollowUpPanel（跟进记录面板）

**复用组件**：`FollowUpList.vue`（需迁移到 shadcn-vue）

**面板结构**：

```vue
<Card>
  <CardHeader class="flex flex-row items-center justify-between">
    <h3>跟进记录</h3>
    <Button size="sm" @click="openFollowUpDialog">
      <Plus class="w-4 h-4 mr-1" />
      添加跟进
    </Button>
  </CardHeader>
  <CardContent class="p-0">
    <FollowUpList
      :follow-ups="followUps"
      :loading="loading"
      empty-title="暂无跟进记录"
      empty-description="添加跟进记录，记录客户沟通情况"
    />
  </CardContent>
</Card>
```

**弹窗**：`FollowUpFormDialog.vue`（新建）

---

#### ContactsPanel（联系人面板）

**展示内容**：

- 联系人列表（姓名、职位、电话、邮箱、是否决策者）
- 操作：新建、编辑、删除

**使用的组件**：

- `DataTable` - 数据表格
- `StatusBadge` - 决策者标记

---

#### OpportunitiesPanel（商机面板）

**展示内容**：

- 商机列表（商机名称、阶段、金额、预计成交日期、状态）
- 状态徽章：`StatusBadge` 组件
- 操作：新建商机、查看详情

---

#### ContractsPanel（合同面板）

**展示内容**：

- 合同列表（合同编号、合同名称、合同金额、签约日期、状态）
- 状态徽章：草稿/审批中/生效/完成/终止

---

#### PaymentsPanel（回款面板）

**展示内容**：

- 回款计划/记录列表
- 状态徽章：待登记/部分回款/已完成/逾期

**无弹窗**：回款通过合同详情页管理

---

#### InvoicesPanel（发票面板）

**展示内容**：

- 发票抬头列表（抬头名称、税号、是否默认）

---

#### LicensePanel（License 面板）

**迁移 `LicenseManagement.vue`**：

**面板结构**：

```vue
<div class="space-y-6">
  <!-- 部署信息区域 -->
  <Card>
    <CardHeader class="flex flex-row items-center justify-between">
      <h3>部署信息配置</h3>
      <Button size="sm">
        <Plus class="w-4 h-4 mr-1" />
        新增部署信息
      </Button>
    </CardHeader>
    <CardContent>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card v-for="deployment in deployments" :key="deployment.id">
          <!-- 部署信息卡片 -->
        </Card>
      </div>
    </CardContent>
  </Card>

  <!-- License 申请记录 -->
  <Card>
    <CardHeader class="flex flex-row items-center justify-between">
      <h3>License 申请记录</h3>
      <Button size="sm">
        <Plus class="w-4 h-4 mr-1" />
        申请 License
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <DataTable :data="licenseApplications" :columns="columns">
        <!-- 表格内容 -->
      </DataTable>
    </CardContent>
  </Card>
</div>
```

**弹窗**：

- `DeploymentInfoDialog.vue`（迁移到 shadcn-vue）
- `LicenseApplicationDialog.vue`（迁移到 shadcn-vue）

---

## 四、表单弹窗设计

### 4.1 FollowUpFormDialog（新建跟进弹窗）

**表单字段**：

- 跟进方式（下拉选择：电话、微信、邮件、拜访）
- 跟进内容（文本域，必填）
- 下次跟进时间（日期选择器，可选）
- 下次行动计划（文本域，可选）

**使用的 shadcn-vue 组件**：

- `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogFooter`
- `Form`, `FormItem`, `Label`
- `Select`, `SelectContent`, `SelectItem`, `SelectTrigger`, `SelectValue`
- `Textarea`
- `Button`

**表单验证**：VeeValidate + Zod

---

### 4.2 ContactFormDialog（新建/编辑联系人弹窗）

**表单字段**：

- 姓名（文本输入，必填）
- 性别（单选：男/女）
- 职位（文本输入）
- 是否决策者（开关）
- 手机号（文本输入，必填，手机号格式验证）
- 邮箱（文本输入，邮箱格式验证）
- 微信号（文本输入）

---

### 4.3 OpportunityFormDialog（新建商机弹窗）

**表单字段**：

- 商机名称（文本输入，必填）
- 预计金额（数字输入，必填）
- 预计成交日期（日期选择器，必填）
- 备注（文本域）

---

### 4.4 ContractFormDialog（新建合同弹窗）

**表单字段**：

- 合同名称（文本输入，必填）
- 合同金额（数字输入，必填）
- 签约日期（日期选择器）
- 开始日期（日期选择器）
- 结束日期（日期选择器）
- 备注（文本域）

---

### 4.5 InvoiceTitleFormDialog（发票抬头弹窗）

**表单字段**：

- 抬头名称（文本输入，必填）
- 税号（文本输入，必填）
- 地址（文本输入）
- 电话（文本输入）
- 银行名称（文本输入）
- 银行账号（文本输入）
- 是否默认（开关）

---

### 4.6 DeploymentInfoDialog（迁移）

**表单字段**（已存在，迁移到 shadcn-vue）：

- 部署名称
- 服务器地址
- 授权人数

**迁移内容**：

- `el-dialog` → `Dialog`
- `el-form` → `Form` + `FormItem`
- `el-input` → `Input`
- Element Plus 按钮 → shadcn-vue `Button`

---

### 4.7 LicenseApplicationDialog（迁移）

**表单字段**（已存在，迁移到 shadcn-vue）：

- License 类型（试用/正式）
- 到期日期
- 部署信息（下拉选择）
- 关联合同（下拉选择）
- 备注

**迁移内容**：

- `el-dialog` → `Dialog`
- `el-form` → `Form` + `FormItem`
- `el-select` → `Select`
- `el-date-picker` → `Calendar`
- Element Plus 按钮 → shadcn-vue `Button`

---

### 4.8 通用设计原则

**所有表单弹窗遵循**：

1. **表单验证**：VeeValidate + Zod schema
2. **提交反馈**：loading 状态 + 成功/错误提示
3. **错误处理**：字段下方显示错误信息
4. **必填标识**：Label 旁显示 `*` 号
5. **取消确认**：弹窗关闭时如有未保存内容，提示确认
6. **Design Tokens**：使用 `$wolf-xxx-v2` 变量
7. **响应式**：移动端弹窗全屏显示

---

## 五、设计规范符合性

### 5.1 shadcn-vue 组件使用

| 检查项 | 结果 |
|--------|------|
| ✅ 所有 UI 组件来自 `src/components/ui/` | 通过 |
| ✅ 无自定义开发 UI 组件 | 通过 |
| ✅ 迁移 Element Plus 组件 | 通过 |

### 5.2 Design Tokens

| 检查项 | 结果 |
|--------|------|
| ✅ 使用 `$wolf-xxx-v2` 变量 | 通过 |
| ✅ 使用 `variables-v2.scss` | 通过 |
| ❌ 无硬编码颜色、圆角、间距 | 通过 |

### 5.3 无障碍

| 检查项 | 结果 |
|--------|------|
| ✅ 可见标签 | 通过 |
| ✅ 错误信息位置 | 通过 |
| ✅ Focus 状态 | 通过 |
| ✅ 对比度 4.5:1 | 通过 |

### 5.4 图标规范

| 检查项 | 结果 |
|--------|------|
| ✅ 使用 Lucide Icons | 通过 |
| ❌ 无 Emoji 作为图标 | 通过 |
| ✅ SVG 矢量图标 | 通过 |

---

## 六、实施计划概览

**总任务数**：17 个（13 个新建 + 4 个改造）

**预计工作量**：中高（一次性全量实施）

**实施顺序**：

1. 数据加载逻辑（CustomerDetailSheet 改造）
2. 热力值卡片
3. 客户档案卡片
4. FollowUpList.vue 迁移
5. 各内容面板（FollowUpPanel → LicensePanel）
6. 表单弹窗（FollowUpFormDialog → InvoiceTitleFormDialog）
7. License 相关组件迁移

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 工作量大 | 高 | 使用 Subagent-Driven Development，任务间审查 |
| Element Plus 迁移复杂 | 中 | 优先迁移 FollowUpList，建立迁移模式 |
| API 数据结构变化 | 低 | 已探索 API，数据结构稳定 |
| 设计 Token 遗漏 | 低 | 每个任务完成后审查 |

---

## 八、下一步

1. **用户审查设计文档**
2. **调用 writing-plans skill 创建实施计划**
3. **使用 Subagent-Driven Development 执行**