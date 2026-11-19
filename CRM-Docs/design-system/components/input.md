# 输入

- **用途：**收集、校验和反馈用户输入。
- **适用范围：**components 领域。
- **权威性：**本主题是输入控件行为与组合的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [排版](../foundations/typography.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 结构

每个输入必须有可见标签；标签说明所需信息，必要时标明必填或格式。帮助文字放在字段附近，解释格式、限制或后果。占位文字只能给出示例，不能替代标签。

将相关字段组织为可理解的组，按任务顺序排列。选择、日期、长文本和搜索等输入采用匹配其数据类型的交互方式，不用自由文本模拟受约束的选择。

## 校验与反馈

在不打断录入的前提下尽早反馈可确定的问题；提交时汇总未解决问题。错误信息紧贴对应字段，说明问题和修复方法。提交失败后，焦点移至首个需要处理的字段，已填写内容不得丢失。

默认、悬停、焦点、已填、错误、只读、禁用和处理中状态必须可辨。遵循[无障碍](../foundations/accessibility.md)的标签、焦点、错误与禁用规则；颜色语义遵循[颜色令牌](../foundations/color-tokens.md)，不得只靠颜色标识错误。

## 响应式与视觉

表单输入、选择、日期选择和同等数据录入控件桌面默认使用 md 高度（`--control-h-md`），列表筛选栏与工具栏内的字段统一用 sm，行内用 xs、强调场景用 lg，由组件 `size` 声明，不得在业务表单中局部手写高度。窄视口下统一抬高到 `--touch-target`，保证弹窗、Sheet 和表单页的可点区域。数值见[令牌数值](../foundations/token-values.md#控件与版式)。

字段间距遵循[间距与布局](../foundations/spacing-layout.md)，圆角遵循[圆角与层级](../foundations/radius-elevation.md)。窄视口的输入文字和可触达尺寸遵循[排版](../foundations/typography.md)与[响应式与移动端](../foundations/responsive-mobile.md)。状态过渡和减少动效遵循[动效与性能](../foundations/motion-performance.md)。

## 实现契约

页面表单只用 crmwolf `InputField`、`SelectField`、`TextareaField`、`DateField`、`SearchableSelectField`；`ui/form` 只在 Field 内部使用，页面不得直接导入，见[受限原件](registry.md#受限原件)。

- **共同属性：**`modelValue`、`id`、`label`、`placeholder`、`helperText`、`error`、`required`、`disabled`、`class`；单行、多行、日期另有 `controlClass`，两种选择另有 `triggerClass`、`contentClass`。`controlClass` 等只用于布局，不得改高度、圆角或字号。
- **值类型：**InputField / TextareaField 为字符串或数字，DateField 为 `Date | null`，两种选择均回传字符串。
- **事件：**全部发出 `update:modelValue`；SelectField 另有 `add`（配合 `addActionLabel`、`addActionDisabled`）与 `ariaLabel`；SearchableSelectField 另有 `searchValue` / `update:searchValue`、`update:open`、`loading`、`emptyText`、`loadingText`、`searchPlaceholder`。
- **校验：**用 vee-validate 的 `Field` 或 `defineField` 绑定值，把错误文本传给 `error`；`aria-describedby` 依次指向错误与 `helperText`，出错时说明文字只对读屏保留；`required` 同时输出 `aria-required`。不得在页面手拼 Label + 控件 + 错误文本。
- **选项：**`options` 为 `{ value, label, disabled? }`；SelectField 另支持 `disabledReason`，禁用项必须给出原因。
