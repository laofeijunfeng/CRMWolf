# 确认对话框

- **用途：**规定确认、删除、退出与放弃更改的唯一调用方式与文案。
- **适用范围：**components 领域；`crmwolf/ConfirmDialog.vue`、`CRM-Client/src/utils/confirmDialog.ts` 及全部调用方。
- **权威性：**本主题是确认对话框的实现契约与文案来源；任务边界与焦点规则由[模态框与抽屉](modal-sheet.md)拥有。
- **相关规范：**[组件索引](README.md) · [组件选型](registry.md) · [模态框与抽屉](modal-sheet.md) · [按钮](button.md) · [无障碍](../foundations/accessibility.md)

## 调用

页面只调用 `utils/confirmDialog.ts` 的函数，返回 `Promise<boolean>`（确认为 true）：

| 函数 | 场景 | 确认按钮 |
| --- | --- | --- |
| `confirmDialog(message, title?, options?)` | 通用确认；`options` 含 `confirmText`、`cancelText`、`variant` | 默认 default |
| `confirmDelete(itemName?)` | 删除，不可恢复 | 「删除」，destructive |
| `confirmLogout()` | 退出登录 | 「退出登录」，destructive |
| `confirmSubmit(actionName?)` | 提交类确认 | 默认 default |
| `confirmDiscardChanges(kind?)` | 放弃未保存更改；`close`（默认）或 `leave` | 「放弃更改」，destructive |

全局只挂载一个 ConfirmDialog；`ui/alert-dialog` 只由它消费，页面不得直接导入，也不得调用原生 `confirm`、`alert`、`prompt`（门禁 `restricted-primitive`、`native-dialog`，见[组件门禁](../governance/component-lifecycle.md#组件门禁)）。

## 放弃更改文案

标题「放弃未保存的更改？」；正文 close 用「关闭后，本次修改不会保存。」，leave 用「离开后，本次修改不会保存。」；确认「放弃更改」（destructive）；取消「继续编辑」。文案常量为 `DISCARD_CHANGES_COPY`，页面不得另写变体。

## 行为

- **按钮：**取消在左、确认在右，危险操作确认用 destructive；排列规则见[按钮](button.md#变体与内容)。
- **焦点：**打开时默认焦点在取消按钮；Enter 确认、Escape 取消，点击遮罩不关闭。
- **层级：**使用最高层（topmost），可压过表单弹窗与抽屉。
- **外壳：**AlertDialog 固定 sm 宽度，不提供 `size`；圆角 `--radius-xl`、阴影 `--shadow-3`，见[令牌数值](../foundations/token-values.md#圆角与阴影)。
- **内容：**标题说明动作，正文说明对象与影响；不可逆操作必须写明后果。

[返回组件契约](README.md)
