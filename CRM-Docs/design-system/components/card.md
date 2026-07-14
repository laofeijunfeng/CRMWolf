# 卡片

- **用途：**分组独立但相关的内容与操作。
- **适用范围：**components 领域。
- **权威性：**本主题是卡片层级、内容与交互的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [间距与布局](../foundations/spacing-layout.md) · [颜色令牌](../foundations/color-tokens.md) · [圆角与层级](../foundations/radius-elevation.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md)

## 结构

卡片承载一个可独立理解的内容组。标题说明内容或任务，正文呈现必要信息，操作放在与内容关系明确的位置。没有独立语义的装饰性分组不应使用卡片。

同一区域的卡片采用一致的信息顺序和间距。卡片内的交互元素保留自身语义；不得让整张卡片与其中的链接、按钮产生相互冲突的点击目标。

## 层级与状态

默认卡片使用基础内容层级，只有可整体激活的卡片才提供悬停或按压反馈。选中、警示或不可用状态必须与任务语义对应，并有文字、图标或结构性线索辅助颜色。

视觉颜色遵循[颜色令牌](../foundations/color-tokens.md)，圆角、阴影和叠放关系遵循[圆角与层级](../foundations/radius-elevation.md)，内边距和卡片间距遵循[间距与布局](../foundations/spacing-layout.md)。

## 可达性与响应式

可激活卡片必须可通过键盘到达并显示焦点；卡片内控件遵循[无障碍](../foundations/accessibility.md)。窄视口按[响应式与移动端](../foundations/responsive-mobile.md)收紧布局而不丢失任务信息。状态过渡和减少动效遵循[动效与性能](../foundations/motion-performance.md)。
