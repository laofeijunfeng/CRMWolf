# 操作选项卡片

- **用途：**在弹窗内列出若干带说明的下一步操作，每张卡片是一个独立动作。
- **适用范围：**components 领域；`crmwolf/ActionOptionCard.vue` 及全部调用方。
- **权威性：**本主题是操作选项卡片的实现契约；按钮层级与文案由[按钮](button.md)拥有。
- **相关规范：**[组件索引](README.md) · [组件选型](registry.md) · [按钮](button.md) · [模态框与抽屉](modal-sheet.md) · [无障碍](../foundations/accessibility.md)

## 属性

| 属性 | 说明 | 默认 |
| --- | --- | --- |
| `title` | 动作名称 | 必填 |
| `description` | 一句话说明动作后果 | 必填 |
| `icon` | lucide 图标组件 | 必填 |
| `variant` | `primary`（主操作）/ `default` | default |
| `loading` | 进行中：显示旋转图标、禁用并设置 `aria-busy` | false |
| `disabled` | 禁用 | false |

事件：原生 `click`。

## 使用约束

- 卡片渲染为 `<button type="button">`，是动作而非单选项；需要“先选后提交”时用单选或[分段选择](registry.md#字段与输入)。
- 一组卡片中最多一张 `primary`，其余为 `default`；次要出口（如“查看详情”）用 ghost 按钮，见[按钮](button.md)。
- 页面不得手写同类整卡按钮，也不得用 class 覆写卡片配色。

[返回组件契约](README.md)
