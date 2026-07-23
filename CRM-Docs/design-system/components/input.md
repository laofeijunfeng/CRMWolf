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

表单输入、选择、日期选择和同等数据录入控件的默认最小高度为 44px，保证桌面端与移动端在弹窗、Sheet 和表单页中拥有一致的可点区域。信息密集型表格、工具栏中的紧凑筛选控件如需更小视觉高度，必须由对应复合组件显式声明紧凑变体，不得在业务表单中局部手写高度。

字段间距遵循[间距与布局](../foundations/spacing-layout.md)，圆角遵循[圆角与层级](../foundations/radius-elevation.md)。窄视口的输入文字和可触达尺寸遵循[排版](../foundations/typography.md)与[响应式与移动端](../foundations/responsive-mobile.md)。状态过渡和减少动效遵循[动效与性能](../foundations/motion-performance.md)。
