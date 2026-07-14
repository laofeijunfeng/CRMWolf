# 侧栏

- **用途：**提供桌面与宽视口的一级导航。
- **适用范围：**components 领域。
- **权威性：**本主题是侧栏导航层级与响应式行为的唯一事实来源。
- **相关规范：**[组件索引](README.md) · [颜色令牌](../foundations/color-tokens.md) · [间距与布局](../foundations/spacing-layout.md) · [动效与性能](../foundations/motion-performance.md) · [无障碍](../foundations/accessibility.md) · [响应式与移动端](../foundations/responsive-mobile.md)

## 导航结构

侧栏承载产品的一级目的地，可按稳定业务域分组。每个目的地使用名称和图标共同表达；当前目的地必须明确可辨，分组标题不应充当导航入口。侧栏不承载对象内的上下文切换，使用[标签页](tabs.md)处理该任务。

活动态应同时使用位置、文字或指示物和语义颜色表达。悬停仅增强可指向环境的反馈，不能是发现目的地或操作的唯一方式。颜色与间距分别遵循[颜色令牌](../foundations/color-tokens.md)和[间距与布局](../foundations/spacing-layout.md)。

## 响应式行为

768px 是可折叠侧栏断点：达到或超过该宽度时，侧栏可在展开与折叠形式之间切换，并保留一级目的地的可发现性；低于该宽度时，侧栏退出常驻导航，由[底部导航](bottom-navigation.md)承担移动端一级目的地。

断点、安全区域和页面滚动边界遵循[响应式与移动端](../foundations/responsive-mobile.md)。展开、收起和活动态反馈遵循[动效与性能](../foundations/motion-performance.md)，并尊重减少动效偏好。

## 可达性

折叠控制具有可读名称和当前状态。键盘可按视觉顺序进入目的地，焦点始终可见；图标不替代目的地文字。完整要求遵循[无障碍](../foundations/accessibility.md)。
