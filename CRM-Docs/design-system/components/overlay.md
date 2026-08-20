# 浮层表面

- **用途：**统一临时浮起面板的视觉合同，不合并交互组件。
- **适用范围：**菜单、面板、提示和模态浮层的外壳。
- **权威性：**本主题是浮层视觉分档的唯一事实来源。令牌值由[圆角与层级](../foundations/radius-elevation.md)拥有。
- **相关规范：**[组件索引](README.md) · [圆角与层级](../foundations/radius-elevation.md) · [排版](../foundations/typography.md) · [间距与布局](../foundations/spacing-layout.md) · [模态框与抽屉](modal-sheet.md) · [用户菜单](user-menu.md) · [表格](table.md)

## 选择分档

用户看到的是浮在页面上的面板，不区分 ContextMenu、HoverCard 或 Popover 的技术实现。交互模型保持各自组件；外壳必须同一套表面。

- **Menu：**右键菜单、下拉菜单、Select 与 Combobox 列表。紧凑操作项，无遮罩。
- **Panel：**筛选、排序、字段配置和内容型 Hover 卡片。可有标题或分组，无遮罩。
- **Tooltip：**一行说明或截断预览。体积小，不承担操作面板。
- **Modal：**必须先处理的对话框与抽屉。有遮罩；任务边界由[模态框与抽屉](modal-sheet.md)拥有。

不得把 Menu 做成 Modal 的内边距和遮罩，也不得把 Panel 画成控件圆角。

## 表面合同

颜色遵循[颜色令牌](../foundations/color-tokens.md)。圆角、阴影和叠放遵循[圆角与层级](../foundations/radius-elevation.md)：

- Menu 与 Panel 使用 overlay 圆角和 overlay 阴影。
- Tooltip 使用控件圆角和 hover 阴影。
- Modal 使用 overlay 圆角和 modal 阴影。
- 只有向上展开的底部面板才使用 dropdown 阴影。

Menu 容器使用紧凑内边距；Panel 容器内边距为 0 时，内部 chrome 使用模块内间距。标题使用正文半粗，菜单项使用正文中等，辅助信息使用说明字号，均见[排版](../foundations/typography.md)。图标边长 16px，与文字间距使用关联元素间距。

## 落地边界

新浮层改 `ui/*Content` 默认表面或 crmwolf 封装，不在页面覆盖圆角和阴影。内容宽度、打开延迟和触发方式仍由各组件拥有。窄视口规则遵循[响应式与移动端](../foundations/responsive-mobile.md)。动效遵循[动效与性能](../foundations/motion-performance.md)。
