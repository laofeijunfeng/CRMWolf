# 模态框与抽屉

- **用途：**在保留当前页面上下文时承载临时任务或补充内容。
- **适用范围：**components 领域。
- **权威性：**本主题是模态框、抽屉的任务边界与焦点管理的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [浮层表面](overlay.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md) · [响应式与移动端](../foundations/responsive-mobile.md)

## 选择承载方式

模态框用于必须先处理才能继续当前任务的短时确认、编辑或决定。抽屉用于需要保留页面参照的补充信息或较长任务。两者都不应用作长期页面、复杂多阶段流程或常规一级导航的替代。

每个浮层有明确标题、关闭方式和任务结果。不可逆操作说明影响并取得确认；提交期间避免关闭或重复提交造成数据不确定。关闭前应在必要时提示未保存内容。

放弃未保存内容统一文案：标题「放弃未保存的更改？」，正文「关闭后，本次修改不会保存。」（离开页面时用「离开后，本次修改不会保存。」），确认「放弃更改」（destructive），取消「继续编辑」，默认焦点在「继续编辑」。

## 焦点与层级

打开后焦点进入浮层，交互范围保持在浮层内；关闭后焦点返回启动它的元素。可通过明确的关闭操作和键盘关闭，且不得只依赖点击遮罩。遵循[无障碍](../foundations/accessibility.md)的名称、焦点和动态反馈规则。

颜色遵循[颜色令牌](../foundations/color-tokens.md)，圆角、遮罩和浮层层级遵循[圆角与层级](../foundations/radius-elevation.md)。外壳分档遵循[浮层表面](overlay.md)的 Modal。进入、退出和减少动效遵循[动效与性能](../foundations/motion-performance.md)。

## 宽度

Dialog 宽度只取 `DialogContent` 的 `size` 五档，数值见[令牌数值](../foundations/token-values.md#控件与版式)的 `--dialog-w-*`：

- **sm：**单字段或纯确认（重命名、确认赢单/输单、简单设置）。
- **md（默认）：**常规单列表单与说明。
- **lg：**双列表单、带明细的业务单据。
- **xl：**带表格或流程编排的复杂编辑。
- **full：**大图、文件预览与比对。

AlertDialog 固定 sm，不提供 `size`。页面不得再写 `max-w-[…]`、`w-[calc(…)]` 或在 scoped 样式里设置弹窗宽度；窄视口宽度由 `DialogContent` 统一处理。抽屉（Sheet / DetailSheet）不使用这套档位。

## 响应式

窄视口按[响应式与移动端](../foundations/responsive-mobile.md)选择不遮挡关键操作的承载形式，避开安全区域并支持内容内部滚动。页面背景不得因浮层内容而产生横向滚动。
