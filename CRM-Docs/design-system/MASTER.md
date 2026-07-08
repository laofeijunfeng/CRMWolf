# CRMWolf 设计系统 - MASTER.md

**全局设计规则唯一来源**

---

## 一、设计原则（核心价值观）

### 1.1 四大核心原则

| 原则 | 说明 | 反模式 |
|------|------|---------|
| **极致克制** | 所有设计元素必须有明确用途，装饰性元素不超过5% | 过度装饰、无意义动画 |
| **柔和低噪** | 避免高饱和色彩，使用中性暖灰为主色调 | 高饱和蓝、荧光色 |
| **统一有序** | 所有组件使用统一的 Design Tokens | 硬编码颜色、圆角、间距 |
| **服务内容** | UI 不抢夺用户注意力，内容为王 | UI 元素比内容更显眼 |

### 1.2 设计优先级

```
功能完整性 > 可用性 > 性能 > 视觉一致性 > 装饰性
```

**决策标准**：
- 如果影响功能，必须优化
- 如果影响可用性，必须优化
- 如果仅影响视觉，可以权衡

### 1.3 移动端设计原则（UI/UX Pro Max）

| 原则 | 说明 | UI/UX Pro Max 规则 |
|------|------|-------------------|
| **Mobile-First** | 先设计移动端，再扩展到桌面端 | §5: `mobile-first` |
| **No Horizontal Scroll** | 移动端禁止横向滚动（页面主体） | §5: `horizontal-scroll` |
| **Touch Target ≥44px** | 所有可点击元素最小 44×44pt | §2: `touch-target-size` |
| **16px Body Text** | 移动端正文最小 16px（避免 iOS auto-zoom） | §5: `readable-font-size` |
| **Safe Areas** | 避开 notch、Dynamic Island、手势区域 | §2: `safe-area-awareness` |
| **Adaptive Navigation** | 大屏用 Sidebar，小屏用 Bottom Nav | §9: `adaptive-navigation` |
| **Dynamic Viewport** | 使用 `min(100vh, 100dvh)` 替代 `100vh` | §5: `viewport-units` |

**移动端禁止事项**：
- ❌ 固定 px 容器宽度（导致横向滚动）
- ❌ `user-scalable=no`（禁止缩放，违反 Accessibility）
- ❌ `100vh`（iOS Safari 地址栏展开时超出可视区域）
- ❌ Bottom Nav 超过 5 个项目
- ❌ Touch targets 放在 notch/Dynamic Island 下方

---

## 二、视觉风格规范

### 2.1 色彩系统（V2）

#### 主色调（现代蓝色）

| 角色 | Hex | CSS Variable | 使用场景 |
|------|-----|--------------|---------|
| **Primary** | `#2563EB` | `$wolf-primary-v2` | 主按钮、导航激活态、链接 |
| **Primary Hover** | `#1E40AF` | `$wolf-primary-hover-v2` | 主按钮 hover |
| **Primary Light** | `rgba(#2563EB, 0.1)` | `$wolf-primary-light-v2` | 浅底色、选中背景 |

#### 中性色（暖灰梯度）

| 角色 | Hex | 用途 |
|------|-----|------|
| **Background** | `#F8FAFC` | 页面画布底色 |
| **Card** | `#FFFFFF` | 卡片、表格背景 |
| **Sidebar** | `#FFFFFF` | 侧边栏背景 |
| **Hover** | `#EEF2FF` | hover 态背景、斑马纹 |
| **Muted** | `#F1F5FD` | 辅助背景、禁用态 |

#### 文字色

| 角色 | Hex | Contrast Ratio | 用途 |
|------|-----|----------------|------|
| **Primary Text** | `#0F172A` | 15:1 | 页面主标题、一级信息 |
| **Secondary Text** | `#64748B` | 4.5:1 | 正文、按钮文字 |
| **Tertiary Text** | `#94A3B8` | 3:1 | 辅助信息、未选中导航 |

#### 功能色（状态）

| 角色 | Hex | 使用场景 |
|------|-----|---------|
| **Success** | `#10B981` | 成功状态、成交标记 |
| **Warning** | `#F59E0B` | 警告状态、待审批 |
| **Danger** | `#DC2626` | 危险操作、驳回状态 |

#### 暗色模式（Dark Mode）

**UI/UX Pro Max 规则**：Dark mode uses desaturated / lighter tonal variants, not inverted colors

| 角色 | Token | Hex | 对比度 | 说明 |
|------|-------|-----|--------|------|
| **页面背景** | `$wolf-bg-page-dark-v2` | `#0F172A` | - | Slate-900 |
| **卡片背景** | `$wolf-bg-card-dark-v2` | `#1E293B` | - | Slate-800 |
| **Sidebar 背景** | `$wolf-bg-sidebar-dark-v2` | `#1E293B` | - | Slate-800 |
| **Hover 背景** | `$wolf-bg-hover-dark-v2` | `#334155` | - | Slate-700 |
| **主文字** | `$wolf-text-primary-dark-v2` | `#F8FAFC` | 15:1 | Slate-50 |
| **次文字** | `$wolf-text-secondary-dark-v2` | `#CBD5E1` | 4.5:1 | Slate-300 |
| **辅助文字** | `$wolf-text-tertiary-dark-v2` | `#94A3B8` | 3:1 | Slate-400 |

**暗色功能色（更亮）**：

| 角色 | Token | Hex | 说明 |
|------|-------|-----|------|
| **成功色** | `$wolf-success-dark-v2` | `#34D399` | 暗色模式更亮 |
| **警告色** | `$wolf-warning-dark-v2` | `#FBBF24` | 暗色模式更亮 |
| **危险色** | `$wolf-danger-dark-v2` | `#F87171` | 暗色模式更亮 |

**关键规则**：
- ✅ 暗色对比度必须独立验证（不假设亮色值可用）
- ✅ 使用 desaturated tonal variants（不直接反转颜色）
- ❌ 禁止黑→白直接反转

---

### 2.2 圆角系统（统一 6px）

| 场景 | Token | 值 |
|------|-------|-----|
| **主要圆角** | `$wolf-radius-v2` | `6px` |
| **小圆角** | `$wolf-radius-sm-v2` | `4px` |
| **大圆角** | `$wolf-radius-lg-v2` | `8px` |
| **完全圆角** | `$wolf-radius-full-v2` | `9999px` |

**应用规则**：
- ✅ 所有按钮：`6px`
- ✅ 所有卡片：`6px`
- ✅ 所有输入框：`6px`
- ✅ 所有下拉框：`6px`
- ❌ 禁止使用 `4px / 8px / 12px / 16px`（旧圆角）

---

### 2.3 间距系统（保留 8dp grid）

| 场景 | Token | 值 |
|------|-------|-----|
| **元素内间距** | `$wolf-space-xs-v2` | `4px` |
| **关联元素间距** | `$wolf-space-sm-v2` | `8px` |
| **模块内间距** | `$wolf-space-md-v2` | `12px` |
| **模块间间距** | `$wolf-space-lg-v2` | `16px` |

**应用规则**：
- ✅ 图标与文字间距：`8px`
- ✅ 按钮左右 padding：`16px`
- ✅ 卡片内边距：`16px`
- ✅ 页面安全边距：`24px`

---

### 2.4 阴影系统（中等强度）

| 场景 | Token | 值 |
|------|-------|-----|
| **卡片阴影** | `$wolf-shadow-card-v2` | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **Hover 阴影** | `$wolf-shadow-hover-v2` | `0 2px 8px rgba(0, 0, 0, 0.15)` |
| **下拉面板阴影** | `$wolf-shadow-dropdown-v2` | `0 -4px 12px rgba(0, 0, 0, 0.15)` |

---

### 2.5 过渡动画系统

| 场景 | Token | 值 |
|------|-------|-----|
| **标准过渡** | `$wolf-transition-v2` | `all 0.15s ease` |
| **Hover 过渡** | `$wolf-transition-hover-v2` | `all 0.2s ease` |

**应用规则**：
- ✅ 所有交互元素 hover：`150ms`
- ✅ 状态切换动画：`150-300ms`
- ❌ 禁止超过 `500ms` 的动画

---

## 三、组件设计规范

### 3.1 Button（按钮）

#### 视觉规范（桌面端）

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **圆角** | `$wolf-radius-v2` | `6px` | 统一圆角 |
| **高度 sm** | `$wolf-button-height-sm-v2` | `24px` | 迷你型（文本按钮，仅桌面） |
| **高度 md** | `$wolf-button-height-md-v2` | `32px` | 常规型（桌面端） |
| **padding sm** | `$wolf-button-padding-sm-v2` | `4px 8px` | 上下 4px，左右 8px |
| **padding md** | `$wolf-button-padding-md-v2` | `8px 16px` | 上下 8px，左右 16px |

#### 视觉规范（移动端 - Touch Target 合规）

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度 mobile** | `$wolf-button-height-mobile-v2` | `44px` | §2: Touch Target ≥44pt |
| **高度 lg** | `$wolf-button-height-lg-v2` | `44px` | 跨平台 touch target |
| **padding mobile** | `$wolf-button-padding-mobile-v2` | `12px 24px` | 移动端更大 padding |

**关键规则**：
- ✅ 桌面端使用 `32px`（鼠标点击精度高）
- ✅ 移动端使用 `44px`（Touch Target 合规）
- ✅ 小于 44px 的图标使用 `hitSlop` 扩展点击区域

#### 状态定义

| 状态 | 背景 | 文字 | 边框 |
|------|------|------|------|
| **Default** | `#FFFFFF` | `#64748B` | `1px #E4ECFC` |
| **Primary** | `#2563EB` | `#FFFFFF` | 无 |
| **Danger** | `#DC2626` | `#FFFFFF` | 无 |
| **Hover** | `#EEF2FF` | `#2563EB` | `1px #2563EB` |
| **Disabled** | `#F1F5FD` | `#94A3B8` | 无 |

#### UX 规则

- ✅ **cursor: pointer**（所有可点击元素）
- ✅ **hover 状态可见**（150ms 过渡）
- ✅ **disabled 状态明确**（opacity: 0.5）
- ✅ **加载反馈**（禁用 + spinner）

---

### 3.2 Input（输入框）

#### 视觉规范（桌面端）

| 属性 | Token | 值 |
|------|-------|-----|
| **高度** | `$wolf-input-height-v2` | `32px` |
| **圆角** | `$wolf-radius-v2` | `6px` |
| **背景 default** | - | `#FFFFFF` |
| **背景 hover** | - | `#EEF2FF` |
| **背景 focus** | - | `#FFFFFF` |

#### 视觉规范（移动端 - Touch Target 合规）

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度 mobile** | `$wolf-input-height-mobile-v2` | `44px` | §8: `touch-friendly-input` |
| **padding mobile** | `$wolf-input-padding-mobile-v2` | `16px` | 更大 padding |
| **字号 mobile** | `$wolf-font-size-body-mobile-v2` | `16px` | §5: 避免 iOS auto-zoom |

**关键规则**：
- ✅ 移动端 input 高度 ≥ 44px
- ✅ 移动端 input 字号 = 16px（iOS Safari 不会 auto-zoom）
- ❌ 禁止移动端 input 字号 < 16px

#### 状态定义

| 状态 | 边框 | 阴影 |
|------|------|------|
| **Default** | `1px #E4ECFC` | 无 |
| **Hover** | `1px #2563EB` | 无 |
| **Focus** | `2px #2563EB` | `0 0 0 3px rgba(#2563EB, 0.1)` |
| **Error** | `2px #DC2626` | 无 |

#### UX 规则

- ✅ **Visible label**（必须有可见标签）
- ✅ **Error near field**（错误提示在输入框下方）
- ✅ **Focus ring**（2px 轮廓 + 外发光）
- ✅ **Helper text**（复杂输入框提供帮助文本）

---

### 3.3 Table（表格）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **行高** | `44px`（自适应，内容多时撑高） |
| **表头背景** | `#F1F5FD` |
| **表头文字** | `#64748B` |
| **表头字号** | `13px` |
| **表头字重** | `600` |
| **行分割线** | `#E4ECFC`（极淡） |
| **Hover 背景** | `#EEF2FF` |

#### 设计原则

- ✅ **无竖分割线**（极简风格）
- ✅ **自适应行高**（内容换行时撑高）
- ✅ **Hover 状态明显**（背景色变化）
- ❌ **禁止固定行高**（导致内容截断）

---

### 3.4 Card（卡片）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **圆角** | `6px` |
| **阴影** | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **边框** | `1px #E4ECFC` |
| **内边距** | `16px` |

#### 状态定义

| 状态 | 阴影 |
|------|------|
| **Default** | `0 1px 3px rgba(0, 0, 0, 0.1)` |
| **Hover** | `0 2px 8px rgba(0, 0, 0, 0.15)` |

---

### 3.5 Tab（标签栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `48px` |
| **圆角** | `6px` |
| **字号** | `14px` |
| **字重 default** | `500` |
| **字重 active** | `600` |

#### 状态定义

| 状态 | 背景 | 文字 |
|------|------|------|
| **Default** | 透明 | `#64748B` |
| **Hover** | `#EEF2FF` | `#2563EB` |
| **Active** | `#F1F5FD` | `#2563EB` |

#### Active 指示条设计

- ✅ **左侧指示条**（`4px` 高亮条）
- ✅ **hover 时显示 3px**
- ✅ **active 时显示 4px**
- ✅ **过渡动画 150ms**

---

## 四、导航组件规范

### 4.1 Sidebar（左侧菜单）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **宽度** | `220px` |
| **背景** | `#FFFFFF` |
| **菜单项高度** | `40px` |
| **菜单项圆角** | `6px` |

#### 左侧指示条设计（核心视觉特征）

```scss
.nav-item {
  position: relative;
  
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;  // default
    height: 16px;
    background: $wolf-primary-v2;
    border-radius: 0 2px 2px 0;
    transition: width 0.15s ease;
  }
  
  &:hover::before {
    width: 3px;  // hover 时显示 3px
  }
  
  &.active::before {
    width: 4px;  // active 时显示 4px
  }
}
```

#### 分组规范

| 分组 | 标题 | 示例 |
|------|------|------|
| **销售流程** | `销售流程` | 我的日历、线索、客户、商机 |
| **财务流程** | `财务流程` | 合同、回款、发票 |
| **管理工具** | `管理工具` | 采购、团队、系统 |

---

### 4.2 TopBar（顶部栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `56px` |
| **背景** | `#FFFFFF` |
| **标题字号** | `20px` |
| **标题字重** | `600` |

#### 三段式布局

| 区域 | 内容 | 宽度 |
|------|------|------|
| **左侧** | 返回按钮 | `48px` |
| **中间** | 页面标题 | 自适应居中 |
| **右侧** | 操作按钮 + 审批铃铛 | 自适应 |

---

### 4.3 ContextTabs（上下文标签栏）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **高度** | `48px` |
| **背景** | `#FFFFFF` |

#### 动态切换规则

| 页面类型 | 标签内容 |
|---------|---------|
| **客户详情页** | 基本信息 / 跟进 / 联系人 / 商机 / 合同 / 回款 / 发票 / License |
| **回款管理页** | 回款计划 / 回款记录 |
| **合同详情页** | 基本信息 / 回款计划 |

---

### 4.4 UserInfoDropdown（用户下拉菜单）

#### 视觉规范

| 属性 | 值 |
|------|-----|
| **展开方向** | 向上（从底部展开） |
| **圆角** | `8px` |
| **阴影** | `0 -4px 12px rgba(0, 0, 0, 0.15)` |
| **过渡** | `0.2s ease` |

#### 内容分组

| 分组 | 内容 |
|------|------|
| **切换团队** | 所有团队列表（当前团队有 ✓ 标记） |
| **个人设置** | 个人资料、账户设置、退出登录 |

---

### 4.5 Bottom Navigation（移动端底部导航）

#### 视觉规范

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **高度** | `$wolf-bottom-nav-height-v2` | `56px` | 固定底部栏高度 |
| **项目高度** | `$wolf-bottom-nav-item-height-v2` | `44px` | Touch Target 合规 |
| **最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | UI/UX Pro Max 规则 |
| **padding** | `$wolf-bottom-nav-padding-v2` | `8px` | 内边距 |

#### 设计原则（UI/UX Pro Max §9）

- ✅ **必须有 Icon + Text Label**（§9: `nav-label-icon`）
- ✅ **最多 5 个项目**（§9: `bottom-nav-limit`）
- ✅ **当前项高亮显示**（§9: `nav-state-active`）
- ❌ **禁止 Icon-only Bottom Nav**（损害可发现性）
- ❌ **禁止嵌套子导航**（§9: `bottom-nav-top-level`）

#### Bottom Nav 项目示例

| 序号 | Icon | Label | 说明 |
|------|------|-------|------|
| 1 | `calendar` | 日历 | 我的日历 |
| 2 | `users` | 客户 | 客户管理 |
| 3 | `opportunities` | 商机 | 商机管理 |
| 4 | `file-text` | 合同 | 合同管理 |
| 5 | `more-horizontal` | 更多 | Overflow Menu（线索/回款/发票/审批/设置） |

#### 响应式切换

```scss
.bottom-nav {
  display: none;  // 桌面端隐藏
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: flex;  // <1024px 显示
    position: fixed;
    bottom: 0;
    padding-bottom: $wolf-safe-area-bottom-v2;  // Safe Area
  }
}
```

---

## 五、交互规范

### 5.1 Hover 状态

| 元素 | Hover 效果 | 过渡时间 |
|------|----------|---------|
| **按钮** | 背景 + 边框变化 | `150ms` |
| **菜单项** | 背景 + 左侧指示条 | `150ms` |
| **卡片** | 阴影增强 | `150ms` |
| **表格行** | 背景变色 | `150ms` |

### 5.2 Active 状态

| 元素 | Active 效果 |
|------|------------|
| **按钮** | 背景 + 边框 + 阴影 |
| **菜单项** | 背景 + 左侧指示条（4px） |
| **Tab** | 背景 + 文字 + 左侧指示条 |

### 5.3 Disabled 状态

| 属性 | 值 |
|------|-----|
| **opacity** | `0.5` |
| **cursor** | `not-allowed` |
| **交互** | 禁止点击 |

### 5.4 Loading 状态

| 场景 | 反馈 |
|------|------|
| **按钮** | 禁用 + spinner |
| **表格** | skeleton shimmer |
| **页面** | skeleton 屏幕 |

---

## 六、无障碍规范

### 6.1 对比度要求

| 类型 | 最小对比度 | Token |
|------|-----------|-------|
| **正常文字** | `4.5:1`（WCAG AA） | `$wolf-text-secondary-v2: #64748B` |
| **大文字** | `3:1` | `$wolf-text-tertiary-v2: #94A3B8` |
| **图标** | `3:1` | 所有 Icon 颜色 |

**暗色模式对比度（独立验证）**：

| 类型 | Token | 对比度 |
|------|-------|--------|
| **主文字** | `$wolf-text-primary-dark-v2: #F8FAFC` | 15:1 on `#0F172A` ✅ |
| **次文字** | `$wolf-text-secondary-dark-v2: #CBD5E1` | 4.5:1 on `#1E293B` ✅ |

### 6.2 Focus 状态（详细规范）

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-focus-ring-width-v2` | `2px` | Focus ring 宽度（WCAG 2.4.7 合规） |
| `$wolf-focus-ring-color-v2` | `rgba(#2563EB, 0.5)` | 主色半透明 |
| `$wolf-focus-ring-offset-v2` | `2px` | 偏移（不覆盖元素边界） |

**Focus Ring 变体**：

| 类型 | Token | 值 | 应用场景 |
|------|-------|-----|---------|
| **强 focus** | `$wolf-focus-ring-width-strong-v2` | `3px` | 主要按钮、关键输入 |
| **弱 focus** | `$wolf-focus-ring-width-subtle-v2` | `1px` | 次要链接 |
| **Focus Shadow** | `$wolf-focus-shadow-v2` | `0 0 0 2px rgba(#2563EB, 0.3)` | Material Design 风格替代 |

**Focus 状态 CSS 示例**：

```scss
.button:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

// Material Design 风格（替代 outline）
.button:focus-visible {
  outline: none;
  box-shadow: $wolf-focus-shadow-v2;
}
```

**关键规则**：
- ✅ Focus ring 必须可见（WCAG 2.4.7 Focus Visible）
- ✅ Focus ring 与背景对比度 ≥ 3:1
- ❌ 禁止 `outline: none`（无替代方案）

### 6.3 Reduced Motion 支持

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-reduced-motion-duration-v2` | `0.01ms` | `prefers-reduced-motion` 时的动画时长 |
| `$wolf-reduced-motion-delay-v2` | `0ms` | Reduced motion 延迟 |

**CSS 示例**：

```scss
.button {
  transition: all 150ms ease;
  
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
```

**关键规则**：
- ✅ 所有动画必须支持 `prefers-reduced-motion`
- ✅ Reduced motion 时保留 `0.01ms` 微动画（非完全禁用）
- ❌ 禁止忽略 `prefers-reduced-motion`

### 6.4 Screen Reader

- ✅ **aria-label**（图标按钮）
- ✅ **aria-live**（动态内容）
- ✅ **语义化标签**（button、label、nav）
- ✅ **Focus 管理**（错误后自动 focus 第一个错误字段）
- ✅ **Tab 顺序正确**（匹配视觉顺序）

### 6.5 Disabled 状态规范（Material Design）

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-disabled-opacity-v2` | `0.38` | Material Design disabled opacity |
| `$wolf-disabled-opacity-light-v2` | `0.5` | 亮色模式（更柔和） |
| `$wolf-disabled-opacity-dark-v2` | `0.38` | 暗色模式 |
| `$wolf-cursor-disabled-v2` | `not-allowed` | Disabled cursor |

**关键规则**：
- ✅ Disabled 元素必须有语义属性（`disabled` 或 `aria-disabled="true"`）
- ✅ Disabled 元素必须有视觉区分（opacity + cursor）
- ❌ 禁止 Disabled 元素可点击（pointer-events: none 或 disabled 属性）

---

## 七、性能规范

### 7.1 动画性能

- ✅ **仅使用 transform/opacity**（避免 animating width/height/top/left）
- ✅ **避免 layout reflow**
- ✅ **requestAnimationFrame**（复杂动画）

### 7.2 响应时间

| 操作 | 最大延迟 |
|------|---------|
| **Tap 反馈** | `100ms` |
| **Hover 反馈** | `150ms` |
| **Loading 显示** | `300ms` |

---

## 八、响应式规范

### 8.1 断点系统

| 断点 | Token | 值 | 设备 | 导航模式 |
|------|-------|-----|------|---------|
| **xs** | `$wolf-breakpoint-xs-v2` | `375px` | 小手机（iPhone SE） | Bottom Nav |
| **sm** | `$wolf-breakpoint-sm-v2` | `768px` | 平板竖屏（iPad Mini） | Sidebar 可折叠 |
| **md** | `$wolf-breakpoint-md-v2` | `1024px` | 平板横屏 / 小桌面 | Sidebar 显示 |
| **lg** | `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面 | Sidebar 固定 |

**断点切换规则**：
- **xs → sm**：Sidebar 从隐藏变为可折叠
- **sm → md**：Sidebar 从折叠变为固定显示，Bottom Nav 消失
- **md → lg**：容器宽度扩展，内容区最大 1200px

### 8.2 间距适配（Mobile-First）

| 断点 | Token | 页面边距 | 卡片间距 | 说明 |
|------|-------|---------|---------|------|
| **xs** | `$wolf-page-padding-mobile-v2` | `16px` | `12px` | 移动端更紧凑 |
| **sm** | - | `24px` | `16px` | 平板适中 |
| **md+** | `$wolf-page-padding-v2` | `24px` | `20px` | 桌面端舒适 |

### 8.3 移动端字体尺寸（iOS Auto-Zoom 防护）

| 场景 | Token | 值 | 说明 |
|------|-------|-----|------|
| **移动端正文** | `$wolf-font-size-body-mobile-v2` | `16px` | UI/UX Pro Max: 避免 iOS Safari auto-zoom |
| **移动端标题** | `$wolf-font-size-title-mobile-v2` | `18px` | 更醒目 |
| **移动端辅助** | `$wolf-font-size-caption-mobile-v2` | `14px` | 辅助信息 |

**关键规则**：
- ✅ 移动端 input/textarea 必须使用 `16px` 字号
- ❌ 禁止移动端使用 `< 16px` 字号（iOS Safari 会自动放大页面）

### 8.4 安全区域（Safe Areas）

| Token | 值 | 用途 |
|-------|-----|------|
| `$wolf-safe-area-top-v2` | `env(safe-area-inset-top, 0px)` | iOS notch / Dynamic Island |
| `$wolf-safe-area-bottom-v2` | `env(safe-area-inset-bottom, 0px)` | iOS Home Indicator / Android 手势区域 |
| `$wolf-safe-area-left-v2` | `env(safe-area-inset-left, 0px)` | 横屏左侧安全区域 |
| `$wolf-safe-area-right-v2` | `env(safe-area-inset-right, 0px)` | 横屏右侧安全区域 |

**应用场景**：
- ✅ TopBar padding-top: `$wolf-safe-area-top-v2`
- ✅ Bottom Nav padding-bottom: `$wolf-safe-area-bottom-v2`
- ❌ 禁止将 Touch Targets 放在安全区域下方

### 8.5 Viewport 单位（iOS Safari 适配）

| 场景 | Token | 值 | 说明 |
|------|-------|-----|------|
| **移动端高度** | `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | UI/UX Pro Max: 解决 iOS Safari 地址栏问题 |
| **桌面端高度** | `$wolf-viewport-height-desktop-v2` | `100vh` | 桌面端固定高度 |

**关键规则**：
- ❌ 禁止移动端使用 `100vh`（地址栏展开时超出可视区域）
- ✅ 使用 `min(100vh, 100dvh)` 或 `100svh`

### 8.6 响应式导航切换

| 断点 | 导航模式 | Sidebar | TopBar | Bottom Nav |
|------|---------|---------|--------|-----------|
| **≥1024px（桌面）** | Sidebar + TopBar | 220px 固定 | 56px，显示标题 | 隐藏 |
| **<1024px（移动）** | TopBar + Bottom Nav | 隐藏 | 56px，显示 hamburger + 标题 | 56px，最多 5 项目 |

**导航切换 CSS 示例**：

```scss
// Sidebar: 桌面端显示，移动端隐藏
.sidebar {
  display: block;  // 默认桌面端显示
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: none;  // <1024px 隐藏
  }
}

// Bottom Nav: 移动端显示，桌面端隐藏
.bottom-nav {
  display: none;  // 默认桌面端隐藏
  
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    display: flex;  // <1024px 显示
  }
}
```

### 8.7 Bottom Navigation 规范

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **高度** | `$wolf-bottom-nav-height-v2` | `56px` | 固定底部栏高度 |
| **最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | §9: `bottom-nav-limit` |
| **必须有** | - | Icon + Text Label | §9: `nav-label-icon` |
| **项目高度** | `$wolf-bottom-nav-item-height-v2` | `44px` | Touch Target 合规 |

**Bottom Nav 项目示例（销售流程）**：

| 项目 | Icon | Label | 说明 |
|------|------|-------|------|
| 1 | calendar | 日历 | 我的日历 |
| 2 | users | 客户 | 客户管理 |
| 3 | opportunities | 商机 | 商机管理 |
| 4 | file-text | 合同 | 合同管理 |
| 5 | more-horizontal | 更多 | 线索/回款/发票/审批/设置 |

**关键规则**：
- ✅ 必须同时显示 Icon 和 Text Label（§9: `nav-label-icon`）
- ✅ 最多 5 个项目，超出放入 "更多" Overflow Menu
- ❌ 禁止 Icon-only Bottom Nav（损害可发现性）

### 8.8 移动端表格适配

| 属性 | Token | 值 | 说明 |
|------|-------|-----|------|
| **最小宽度** | `$wolf-table-min-width-mobile-v2` | `100%` | 允许横向滚动 |
| **单元格 padding** | `$wolf-table-cell-padding-mobile-v2` | `8px 4px` | 更紧凑 |

**移动端表格策略**：
- ✅ 简化列数（仅显示核心信息）
- ✅ 允许表格横向滚动（页面主体禁止）
- ❌ 禁止固定 px 宽表格容器

### 8.9 移动端 Modal/Sheet

| 属性 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **最大高度** | `$wolf-modal-height-mobile-v2` | `90vh` | 不占满屏幕 |
| **顶部圆角** | `$wolf-modal-radius-mobile-v2` | `8px` | 仅顶部圆角 |
| **展开方向** | - | 从底部向上 | §7: `modal-motion` |

**关键规则**：
- ✅ Modal 从底部滑入（§7: `modal-motion`）
- ✅ Sheet 可 swipe-down 关闭（§9: `modal-escape`）
- ✅ 有 unsaved changes 时确认关闭（§8: `sheet-dismiss-confirm`）

### 8.10 横向滚动约束

| Token | 值 | 应用场景 |
|-------|-----|---------|
| `$wolf-overflow-x-mobile-v2` | `hidden` | 页面主体禁止横向滚动 |
| `$wolf-overflow-x-allowed-v2` | `auto` | 表格、图片画廊允许横向滚动 |

**关键规则**：
- ✅ 页面主体 `overflow-x: hidden`
- ✅ 特定组件（表格、图片画廊）`overflow-x: auto`
- ❌ 禁止主要内容区域横向滚动

---

## 九、禁止事项（Anti-Patterns）

### 9.1 通用禁止项

| 禁止项 | 原因 |
|--------|------|
| ❌ Emoji 作为图标 | 跨平台不一致、无法控制 |
| ❌ 硬编码颜色 | 违反 Design Tokens 原则 |
| ❌ 硬编码圆角 | 统一 6px 标准 |
| ❌ 超过 500ms 动画 | 用户感知慢 |
| ❌ 无 Focus 状态 | 无障碍不合规 |
| ❌ 旧圆角值 | 4px / 8px / 12px / 16px |

### 9.2 移动端禁止项（UI/UX Pro Max）

| 禁止项 | 原因 | UI/UX Pro Max 规则 |
|--------|------|-------------------|
| ❌ 固定 px 容器宽度（如 `width: 1200px`） | 导致横向滚动 | §5: `horizontal-scroll` |
| ❌ `user-scalable=no`（禁止缩放） | 违反 Accessibility | §5: `viewport-meta` |
| ❌ `100vh`（移动端） | iOS Safari 地址栏展开时超出可视区域 | §5: `viewport-units` |
| ❌ Touch targets 在 notch/Dynamic Island 下方 | 无法点击 | §2: `safe-area-awareness` |
| ❌ Bottom Nav 超过 5 个项目 | 损害可发现性 | §9: `bottom-nav-limit` |
| ❌ Icon-only Bottom Nav | 损害可发现性 | §9: `nav-label-icon` |
| ❌ 移动端 input 字号 < 16px | iOS Safari auto-zoom | §5: `readable-font-size` |
| ❌ 移动端正文字号 < 16px | iOS Safari auto-zoom | §5: `readable-font-size` |
| ❌ 页面主体横向滚动 | 用户体验差 | §5: `horizontal-scroll` |

### 9.3 Stylelint 强制规则

```javascript
{
  'declaration-property-value-disallowed-list': {
    'color': ['/#[0-9a-fA-F]{3,6}/'],  // 禁止硬编码颜色
    'border-radius': ['/(4|8|12|16)px/']  // 禁止旧圆角
  }
}
```

---

## 十、向后兼容

### 10.1 变量别名（过渡期）

```scss
// 保留旧变量名，指向新变量（向后兼容）
$wolf-primary: $wolf-primary-v2;
$wolf-radius-sm: $wolf-radius-v2;
```

### 10.2 迁移时间表

| 阶段 | 时间 | 操作 |
|------|------|------|
| **Phase 0** | 2-3周 | 建立新组件库 |
| **Phase 1** | 4-6周 | 渐进式迁移 |
| **Phase 2** | 1-2周 | 删除旧变量别名 |

---

## 十一、文档检索规则

### 11.1 层级检索

```
页面特定规则 > MASTER.md 规则
```

**检索流程**：
1. 查看特定页面文档（如 `pages/customer-detail.md`）
2. 如果存在，覆盖 MASTER.md 规则
3. 如果不存在，使用 MASTER.md 规则

### 11.2 页面文档命名

| 页面 | 文档路径 |
|------|---------|
| **客户详情** | `pages/customer-detail.md` |
| **合同详情** | `pages/contract-detail.md` |
| **审批中心** | `pages/approval-center.md` |

---

**版本：V2.1（新增移动端适配规范） | 最后更新：2026-07-08**

---

## 附录：移动端设计 Token 快速索引

| 类别 | Token | 值 | 说明 |
|------|-------|-----|------|
| **断点 xs** | `$wolf-breakpoint-xs-v2` | `375px` | 小手机 |
| **断点 sm** | `$wolf-breakpoint-sm-v2` | `768px` | 平板竖屏 |
| **断点 md** | `$wolf-breakpoint-md-v2` | `1024px` | 平板横屏/小桌面 |
| **断点 lg** | `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面 |
| **移动端正文** | `$wolf-font-size-body-mobile-v2` | `16px` | 避免 iOS auto-zoom |
| **安全区域 top** | `$wolf-safe-area-top-v2` | `env(safe-area-inset-top)` | notch/Dynamic Island |
| **安全区域 bottom** | `$wolf-safe-area-bottom-v2` | `env(safe-area-inset-bottom)` | 手势区域 |
| **Viewport 高度** | `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | iOS Safari 适配 |
| **Bottom Nav 高度** | `$wolf-bottom-nav-height-v2` | `56px` | 底部导航高度 |
| **Bottom Nav 最多项目** | `$wolf-bottom-nav-max-items-v2` | `5` | UI/UX Pro Max |
| **移动端按钮高度** | `$wolf-button-height-mobile-v2` | `44px` | Touch Target 合规 |
| **移动端输入框高度** | `$wolf-input-height-mobile-v2` | `44px` | Touch Target 合规 |
| **移动端页面边距** | `$wolf-page-padding-mobile-v2` | `16px` | 更紧凑 |
| **移动端卡片边距** | `$wolf-card-padding-mobile-v2` | `12px` | 更紧凑 |
| **Disabled opacity** | `$wolf-disabled-opacity-v2` | `0.38` | Material Design |
| **Focus ring width** | `$wolf-focus-ring-width-v2` | `2px` | WCAG 合规 |
| **Reduced motion** | `$wolf-reduced-motion-duration-v2` | `0.01ms` | Accessibility |
| **暗色页面背景** | `$wolf-bg-page-dark-v2` | `#0F172A` | Slate-900 |
| **暗色主文字** | `$wolf-text-primary-dark-v2` | `#F8FAFC` | 15:1 contrast |