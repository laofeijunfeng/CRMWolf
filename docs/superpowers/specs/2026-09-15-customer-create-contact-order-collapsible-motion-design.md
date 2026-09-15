# 客户创建弹窗联系人顺序与更多信息展开过渡

- 日期：2026-09-15
- 状态：草案，待用户书面审阅
- 范围：`CustomerFormDialog` 创建模式区块顺序；仓库 `Collapsible` 的高度过渡
- 上游：`docs/superpowers/specs/2026-09-11-customer-edit-progressive-disclosure-design.md`
- 相关组件：shadcn-vue / Reka UI `Collapsible`（[文档](https://www.shadcn-vue.com/docs/components/collapsible)、[Reka 高度动画](https://reka-ui.com/docs/components/collapsible#animating-content-size)）

## 1. 问题

创建弹窗当前顺序是「基础资料 → 更多客户信息 → 联系人」。展开更多信息后，必填联系人被挤到折叠区下面，视线跟着跳到底部。

展开/收起没有高度过渡：内容闪现。原因不是缺组件。仓库已经封装了 shadcn-vue `Collapsible`，`CollapsibleContent.vue` 也写了 `animate-collapsible-down/up`，但：

1. `tailwind.config.ts` 只定义了 `accordion-down/up`，没有 `collapsible-down/up`，这两个 class 不会生成动画。
2. 弹窗把 `class="grid ..."` 直接打在 `CollapsibleContent` 上，盖掉封装里的 `overflow-hidden`。Accordion 的做法是外层裁切和动画，内层再放布局。
3. Reka `Collapsible` 默认 `unmountOnHide=true`，关闭时内容立刻卸载，收起动画跑不完。

不换 Accordion，也不自写一套 height 动画。

## 2. 非目标

- 不改保存契约、字段、权限、License 边界。
- 不把联系人放进「更多客户信息」。
- 不新增组件，不把这段改成 Accordion。
- 不改编辑模式结构（编辑没有联系人区块）。
- 不把这次修复扩到其他 Collapsible 调用方；keyframes 一旦补上，其他调用方可顺带受益，但不要求这次改它们的 markup。

## 3. 方案

继续用现有 `Collapsible`。

### 3.1 创建弹窗区块顺序

```text
客户创建 Dialog
├── 基础信息
├── 联系人信息
├── 更多客户信息（默认收起）
└── Footer
```

编辑模式保持：

```text
客户编辑 Dialog
├── 基础信息
├── 更多客户信息（默认收起）
└── Footer
```

联系人仍只在 `mode === 'create'` 渲染。字段、校验、必填标记不变。

### 3.2 展开过渡

对齐现有 Accordion 的 0.2s ease-out 高度动画：

- 在 `tailwind.config.ts` 增加 `collapsible-down` / `collapsible-up`，高度用 `var(--reka-collapsible-content-height)`（Reka Collapsible 实际注入的变量；Accordion 只是把同一变量别名为 `--reka-accordion-content-height`）。
- 弹窗的 `CollapsibleContent` 只保留封装上的裁切/动画 class，把 `grid gap-4 ...` 挪到内层 wrapper。
- 该弹窗的 `Collapsible` 设 `unmount-on-hide="false"`，让关闭动画有内容可播。不在 Content 上使用会拆掉动画的 layout class。

不新增 Accordion，不手写第二套过渡。

### 3.3 为什么不用别的 shadcn 组件

| 选项 | 结论 |
|------|------|
| Accordion | 多段互斥。这里只有一段「更多」，语义不对。 |
| 自写 height / grid-template-rows | 重复 Reka 已提供的 `--reka-collapsible-content-height`。 |
| 保持 Collapsible，补 keyframes + 内层 wrapper | 与现有 Accordion 模式一致，改动最小。 |

## 4. 测试

在 `CustomerFormDialog.test.ts` 增加创建模式 DOM 顺序断言：联系人标题或 `#customer-contact-name` 出现在 `#customer-more-info-trigger` 之前。编辑模式继续没有联系人区块。

现有折叠、保存、恢复测试应保持绿色。不为 keyframes 写快照测试。

## 5. 文件

- 修改 `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`
- 修改 `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- 修改 `CRM-Client/tailwind.config.ts`（仅补 collapsible keyframes / animation）
- 不改 Collapsible 封装的公共 API；若封装 class merge 需要一小处修正以保住 `overflow-hidden`，可以改 `CollapsibleContent.vue`，但弹窗不得再覆盖掉裁切 class。
