# CRMWolf 动画开发规范

## 一、核心原则

### 1.1 必须有动画的交互

| 交互类型 | 动画要求 | 时长 | 实现方式 |
|---------|---------|------|---------|
| **Tab 切换** | ✅ 必须 | 150ms | Vue Transition + fade |
| **Modal 打开/关闭** | ✅ 必须 | 200ms | scale + fade |
| **Dropdown 展开/收起** | ✅ 必须 | 150ms | height + fade |
| **Button Hover/Active** | ✅ 必须 | 150ms | background-color |
| **Toast 显示/隐藏** | ✅ 必须 | 150ms | slide-in + fade |
| **Skeleton Loading** | ✅ 必须 | shimmer | CSS animation |

### 1.2 禁止的动画

| 类型 | 原因 |
|------|------|
| ❌ 瞬间切换（0ms） | 用户感知突兀 |
| ❌ 超过 500ms | 用户感知慢 |
| ❌ animating width/height/top/left | 性能差 |
| ❌ Decorative-only animation | UI/UX Pro Max §7 |

---

## 二、实现规范

### 2.1 Tab 切换动画（Segmented Control）

**必须使用 Vue Transition 组件**：

```vue
<template>
  <Tabs v-model="activeTab">
    <TabsList>...</TabsList>

    <!-- ✅ 正确：使用 Transition 包裹 -->
    <Transition name="fade" mode="out-in">
      <TabsContent v-if="activeTab === 'login'" value="login">
        <form>...</form>
      </TabsContent>
      <TabsContent v-else-if="activeTab === 'register'" value="register">
        <form>...</form>
      </TabsContent>
    </Transition>
  </Tabs>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease-out;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
}
</style>
```

**关键点**：
- ✅ 使用 `mode="out-in"`（先退出再进入）
- ✅ 使用 `v-if` / `v-else-if`（条件渲染）
- ✅ Reduced motion fallback

---

### 2.2 Modal 动画

```vue
<template>
  <Transition name="modal">
    <div v-if="isOpen" class="modal">...</div>
  </Transition>
</template>

<style scoped>
.modal-enter-active {
  transition: all 200ms ease-out;
}

.modal-leave-active {
  transition: all 150ms ease-in;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

@media (prefers-reduced-motion: reduce) {
  .modal-enter-active,
  .modal-leave-active {
    transition: none;
  }
}
</style>
```

---

### 2.3 Dropdown 动画

```vue
<template>
  <Transition name="dropdown">
    <div v-show="isOpen" class="dropdown">...</div>
  </Transition>
</template>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 150ms ease-out;
  transform-origin: top;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scaleY(0.95);
}

@media (prefers-reduced-motion: reduce) {
  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}
</style>
```

---

## 三、Reduced Motion（减少动态效果）

### 3.1 什么是 Reduced Motion？

**定义**：
- 用户可以在系统设置中启用 "减少动态效果"（iOS/macOS/Windows/Linux）
- 这是一个无障碍访问特性，帮助有眩晕症、 vestibular disorders（前庭障碍）的用户
- 前端必须尊重这个设置，禁用或减少动画

**用户群体**：
- 眩晕症患者
- 前庭障碍患者
- 对动画敏感的用户
- 使用老旧设备的用户

### 3.2 如何检测？

**CSS Media Query**：
```css
@media (prefers-reduced-motion: reduce) {
  /* 禁用所有动画 */
  * {
    animation: none !important;
    transition: none !important;
  }
}
```

**JavaScript 检测**：
```javascript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (prefersReducedMotion) {
  // 禁用动画
}
```

### 3.3 实现规范

**所有动画必须提供 Reduced Motion Fallback**：

```css
/* ✅ 正确 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: none; /* 禁用动画 */
  }
}
```

**禁止的做法**：

```css
/* ❌ 错误：没有 Reduced Motion 支持 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease-out;
}
/* 缺少 @media (prefers-reduced-motion: reduce) */
```

---

## 四、验证清单

### 4.1 开发时验证

- [ ] 所有 Tab 切换有 fade 动画
- [ ] 所有 Modal 有 scale + fade 动画
- [ ] 所有 Dropdown 有 height + fade 动画
- [ ] 所有动画时长 150-300ms
- [ ] 所有动画有 Reduced Motion fallback

### 4.2 测试时验证

```bash
# 1. 启动 Chrome DevTools
# 2. 打开 Rendering 面板
# 3. 勾选 "Emulate CSS media feature: prefers-reduced-motion: reduce"
# 4. 验证动画是否禁用
```

### 4.3 Storybook 验证（推荐）

为每个组件创建 Animation Story：

```typescript
// Tabs.stories.ts
export const Animated: Story = {
  render: () => ({
    components: { Tabs, TabsList, TabsTrigger, TabsContent },
    template: `
      <Tabs v-model="activeTab">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <Transition name="fade" mode="out-in">
          <TabsContent v-if="activeTab === 'tab1'" value="tab1">Content 1</TabsContent>
          <TabsContent v-else value="tab2">Content 2</TabsContent>
        </Transition>
      </Tabs>
    `,
  }),
};
```

---

## 五、常见问题

### Q1: 为什么使用 Vue Transition 而不是 CSS animation？

**A**: Radix Vue 的 TabsContent 在 inactive 时使用 `display: none`，CSS animation 无法执行。Vue Transition 可以在元素隐藏前触发动画。

### Q2: 为什么使用 `mode="out-in"`？

**A**: 确保：
1. 旧内容完全退出（fade-out）
2. 新内容才开始进入（fade-in）
避免两个内容同时显示，造成视觉混乱。

### Q3: Reduced Motion 是禁用还是减少？

**A**: 根据场景：
- **简单动画**：完全禁用（`transition: none`）
- **复杂动画**：减少时长（`transition: all 0.01ms`）
- **关键动画**：保留但简化（去掉 transform，保留 opacity）

---

## 六、参考资料

- [UI/UX Pro Max §7: Animation](https://github.com/your-org/ui-ux-pro-max#animation)
- [Vue Transition 文档](https://vuejs.org/guide/built-ins/transition.html)
- [WCAG 2.3.3: Animation from Interactions](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)
- [prefers-reduced-motion MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion)

---

**版本：V1.0 | 最后更新：2026-07-09**