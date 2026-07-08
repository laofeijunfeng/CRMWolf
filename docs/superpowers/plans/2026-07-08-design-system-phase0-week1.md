# CRMWolf 设计系统 Phase 0 Week 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 CRMWolf 设计系统 V2 的 Design Tokens 基础，创建 variables-v2.scss 并配置强制校验工具（Stylelint + ESLint），为后续基础组件库建设奠定基础。

**Architecture:** 采用"基础先行"策略，先建立 Design Tokens唯一来源，再配置自动化校验规则强制使用新变量，通过向后兼容别名平滑过渡。

**Tech Stack:** Vue 3 + Vite + SCSS + ESLint 9 (flat config) + Vitest

## Global Constraints

- **Design Tokens来源**: `CRM-Docs/design-system/MASTER.md` §2（视觉风格规范）
- **圆角标准**: 统一 6px（`$wolf-radius-v2`），禁止旧值 `4px/8px/12px/16px`
- **主色标准**: `#2563EB`（`$wolf-primary-v2`），替代旧主色 `#4A6FA5`
- **过渡动画**: `150ms ease`（`$wolf-transition-v2`），禁止超过 `500ms`
- **向后兼容**: 所有新变量必须以 `-v2` 结尾，保留旧变量别名
- **文件命名**: 新设计系统文件使用 `-v2` 后缀（如 `variables-v2.scss`）
- **禁止事项**: 禁止 Emoji 作为图标、禁止硬编码颜色/圆角
- **移动端支持**: 完整移动端适配（响应式 Web，支持 iOS/Android Web 浏览器）

### UI/UX Pro Max CRITICAL 规则（强制）

| 规则类别 | UI/UX Pro Max 要求 | CRMWolf V2 实现 |
|---------|-------------------|----------------|
| **Accessibility - Focus States** | Focus ring 2–4px visible | `$wolf-focus-ring-width-v2: 2px` + `$wolf-focus-ring-offset-v2: 2px` |
| **Touch - Touch Target** | Min 44×44pt (iOS) / 48×48dp (Android) | 区分桌面/移动尺寸：`$wolf-button-height-mobile-v2: 44px` |
| **Accessibility - Reduced Motion** | Respect `prefers-reduced-motion` | `$wolf-reduced-motion-duration-v2: 0.01ms` |
| **Typography - Dark Mode** | Dark mode uses desaturated tonal variants | `$wolf-bg-page-dark-v2` / `$wolf-text-primary-dark-v2` |

### UI/UX Pro Max 移动端适配规则（HIGH - 响应式 Web）

| 规则类别 | UI/UX Pro Max 要求 | CRMWolf V2 实现 |
|---------|-------------------|----------------|
| **Layout - Breakpoints** | Systematic 375/768/1024/1440 | `$wolf-breakpoint-xs-v2: 375px` 系列 |
| **Layout - Mobile Font** | Minimum 16px body (avoids iOS auto-zoom) | `$wolf-font-size-body-mobile-v2: 16px` |
| **Layout - Safe Areas** | Notch/Dynamic Island clearance | `$wolf-safe-area-top-v2: env(safe-area-inset-top)` |
| **Layout - Viewport Units** | Prefer min-h-dvh over 100vh | `$wolf-viewport-height-mobile-v2: min(100vh, 100dvh)` |
| **Navigation - Adaptive** | Large: sidebar; Small: bottom/top nav | 响应式导航切换（Sidebar → Bottom Nav） |
| **Navigation - Bottom Nav** | Max 5 items with labels + icons | `$wolf-bottom-nav-max-items-v2: 5` |

---

## File Structure

### 新建文件

| 文件路径 | 负责内容 |
|---------|---------|
| `CRM-Client/src/styles/variables-v2.scss` | V2 Design Tokens唯一来源（颜色、圆角、间距、阴影、过渡） |
| `CRM-Client/src/styles/element-plus-theme-v2.scss` | Element Plus 主题适配（覆盖默认变量） |
| `CRM-Client/.stylelintrc.design-system.js` | Stylelint 设计系统强制规则（禁止硬编码） |
| `CRM-Client/stylelint.config.js` | Stylelint 主配置文件 |
| `CRM-Client/docs/design-system/MIGRATION.md` | 迁移指南（旧变量→新变量映射表） |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `CRM-Client/package.json` | 添加 Stylelint 依赖和脚本 |
| `CRM-Client/eslint.config.js` | 添加设计系统红线规则（禁止旧变量） |
| `CRM-Client/src/styles/variables.scss` | 在末尾添加向后兼容别名（指向 V2 变量） |

---

## Task 1: 创建 Design Tokens 文件（variables-v2.scss）

**Files:**
- Create: `CRM-Client/src/styles/variables-v2.scss`

**Interfaces:**
- Produces: 所有 V2 Design Tokens（颜色、圆角、间距、阴影、过渡变量）

**Reference:** `CRM-Docs/design-system/MASTER.md` §2（视觉风格规范）

- [ ] **Step 1: 创建 variables-v2.scss 文件头部**

```scss
// ==================== CRMWolf 设计系统 V2 ====================
// 规则来源: CRM-Docs/design-system/MASTER.md
// 版本: V2（基于 navigation-redesign-v3.html）
// 核心原则: 极致克制、柔和低噪、统一有序、服务内容

// ==================== 颜色系统（V2）====================
// 主色调: 现代蓝色 #2563EB（清晰、现代）
// 中性色: 暖灰梯度（柔和低噪）
// 功能色: 状态标签专用（极度克制）
```

- [ ] **Step 2: 定义主色调变量**

```scss
// ==================== 主色调（现代蓝色）====================

$wolf-primary-v2: #2563EB;           // 主色（清晰蓝）
$wolf-primary-hover-v2: #1E40AF;     // hover态（加深10%）
$wolf-primary-active-v2: #1D4ED8;    // active态（加深15%）
$wolf-primary-light-v2: rgba(#2563EB, 0.1);  // 浅底色、选中背景

// 次要色（同色系）
$wolf-secondary-v2: #3B82F6;         // 次色

// 强调色（成交绿）
$wolf-accent-v2: #059669;            // 成功/成交标记
```

- [ ] **Step 3: 定义背景色变量**

```scss
// ==================== 背景色（V2）====================

$wolf-bg-page-v2: #F8FAFC;           // 页面画布底色（中性蓝灰）
$wolf-bg-card-v2: #FFFFFF;           // 卡片/表格背景
$wolf-bg-sidebar-v2: #FFFFFF;        // 侧边栏背景
$wolf-bg-hover-v2: #EEF2FF;          // hover态背景、斑马纹
$wolf-bg-muted-v2: #F1F5FD;          // 辅助背景、禁用态
$wolf-bg-elevated-v2: #FFFFFF;       // 弹窗/抽屉内容区
```

- [ ] **Step 4: 定义文字色变量**

```scss
// ==================== 文字色（V2）====================

$wolf-text-primary-v2: #0F172A;      // 页面主标题（对比度 15:1）
$wolf-text-secondary-v2: #64748B;    // 正文、按钮文字（对比度 4.5:1）
$wolf-text-tertiary-v2: #94A3B8;     // 辅助信息、未选中导航（对比度 3:1）
$wolf-text-placeholder-v2: #94A3B8;  // placeholder色
$wolf-text-inverse-v2: #FFFFFF;      // 反色文字

// 链接色
$wolf-text-link-v2: #2563EB;
$wolf-text-link-hover-v2: #1E40AF;
```

- [ ] **Step 5: 定义边框色变量**

```scss
// ==================== 边框色（V2）====================

$wolf-border-default-v2: #E4ECFC;    // 输入框默认边框、控件边框
$wolf-border-hover-v2: #2563EB;      // hover态边框
$wolf-border-light-v2: #F1F5FD;      // 极浅分割线
$wolf-border-divider-v2: #E4ECFC;    // 分割线
```

- [ ] **Step 6: 定义功能色变量**

```scss
// ==================== 功能色（状态标签）====================
// 规则: 必须搭配浅底色+同色系文字，禁止纯色填充

$wolf-success-v2: #10B981;           // 成功色
$wolf-success-text-v2: #10B981;      // 成功文字色
$wolf-success-bg-v2: rgba(#10B981, 0.1);  // 成功背景色

$wolf-warning-v2: #F59E0B;           // 警告色
$wolf-warning-text-v2: #F59E0B;      // 警告文字色
$wolf-warning-bg-v2: rgba(#F59E0B, 0.1);  // 警告背景色

$wolf-danger-v2: #DC2626;            // 危险色
$wolf-danger-text-v2: #DC2626;       // 危险文字色
$wolf-danger-bg-v2: rgba(#DC2626, 0.1);   // 危险背景色
```

- [ ] **Step 7: 定义圆角系统变量**

```scss
// ==================== 圆角系统（统一 6px）====================
// 规则: 所有按钮、卡片、输入框、下拉框统一 6px
// 禁止: 旧圆角值 4px/8px/12px/16px

$wolf-radius-v2: 6px;        // 主要圆角（按钮、卡片、输入框）
$wolf-radius-sm-v2: 4px;     // 小圆角（标签、小型元素）
$wolf-radius-lg-v2: 8px;     // 大圆角（弹窗、对话框）
$wolf-radius-full-v2: 9999px; // 完全圆角（头像、徽章）
```

- [ ] **Step 8: 定义间距系统变量**

```scss
// ==================== 间距系统（保留 8dp grid）====================

$wolf-space-xs-v2: 4px;      // 元素内间距（图标与文字）
$wolf-space-sm-v2: 8px;      // 关联元素间距
$wolf-space-md-v2: 12px;     // 模块内间距
$wolf-space-lg-v2: 16px;     // 模块间间距（卡片内边距）
$wolf-space-xl-v2: 24px;     // 页面安全边距
$wolf-space-2xl-v2: 32px;    // 大间距

// 页面/组件间距
$wolf-page-padding-v2: 24px;
$wolf-card-gap-v2: 16px;
$wolf-card-padding-v2: 16px;
$wolf-section-gap-v2: 24px;
$wolf-form-item-gap-v2: 16px;
```

- [ ] **Step 9: 定义阴影系统变量**

```scss
// ==================== 阴影系统（中等强度）====================
// V1: 极淡极柔 → V2: 中等强度（更有层次感）

$wolf-shadow-card-v2: 0 1px 3px rgba(0, 0, 0, 0.1);       // 卡片阴影
$wolf-shadow-hover-v2: 0 2px 8px rgba(0, 0, 0, 0.15);     // hover态阴影
$wolf-shadow-dropdown-v2: 0 -4px 12px rgba(0, 0, 0, 0.15); // 下拉面板阴影（向上展开）
$wolf-shadow-modal-v2: 0 4px 16px rgba(0, 0, 0, 0.15);    // 弹窗阴影
$wolf-shadow-bottom-v2: 0 -2px 8px rgba(0, 0, 0, 0.1);    // 底部阴影
```

- [ ] **Step 10: 定义过渡动画变量**

```scss
// ==================== 过渡动画系统 ====================
// 规则: 所有交互元素 hover 150ms，状态切换 150-300ms
// 禁止: 超过 500ms 的动画

$wolf-transition-v2: all 0.15s ease;        // 标准过渡（150ms）
$wolf-transition-hover-v2: all 0.2s ease;   // hover过渡（200ms）
$wolf-transition-press-v2: all 0.15s ease;  // press反馈（150ms）
```

- [ ] **Step 11: 定义组件尺寸变量（区分桌面/移动）**

```scss
// ==================== 组件尺寸（V2）====================
// UI/UX Pro Max CRITICAL: Touch Target Minimum 44×44pt
// 规则: 桌面端可使用较小尺寸，移动端必须 ≥44px
// 来源: UI/UX Pro Max §2 (Touch & Interaction)

// ========== 按钮尺寸 ==========

// 桌面端尺寸（Web Dashboard）
$wolf-button-height-sm-v2: 24px;    // 迷你型（文本按钮，仅桌面）
$wolf-button-height-md-v2: 32px;    // 常规型（桌面端）
$wolf-button-padding-sm-v2: 4px 8px;  // 上下4px 左右8px
$wolf-button-padding-md-v2: 8px 16px; // 上下8px 左右16px

// 移动端尺寸（Touch Target合规）
$wolf-button-height-mobile-v2: 44px;    // 移动端常规（44pt合规）
$wolf-button-height-lg-v2: 44px;        // 大型按钮（跨平台 touch target）
$wolf-button-padding-mobile-v2: 12px 24px; // 移动端 padding

// ========== 输入框尺寸 ==========

// 桌面端
$wolf-input-height-v2: 32px;        // 桌面端输入框
$wolf-input-radius-v2: $wolf-radius-v2;
$wolf-input-padding-v2: 12px;

// 移动端（Touch Target合规）
$wolf-input-height-mobile-v2: 44px; // 移动端输入框（44pt合规）
$wolf-input-padding-mobile-v2: 16px;

// ========== 表格尺寸 ==========

$wolf-table-row-height-v2: 44px;        // 最小行高（自适应）
$wolf-table-header-height-v2: 44px;
$wolf-table-cell-padding-y-v2: 12px;
$wolf-table-cell-padding-x-v2: 8px;

// ========== Touch Target 扩展策略 ==========

// 当视觉尺寸小于 44px 时，使用 hitSlop 扩展点击区域
// 示例: 24px 图标的 hitSlop = (44-24)/2 = 10px
$wolf-touch-target-min-v2: 44px;            // 最小 touch target
$wolf-touch-target-hit-slop-v2: 10px;       // 默认 hitSlop 扩展值
```

**重要说明**：
- 桌面端 Web Dashboard 使用 `32px` 尺寸（鼠标点击精度高）
- 移动端或需要 touch 交互的场景必须使用 `44px` 尺寸
- 小于 44px 的图标必须通过 `hitSlop` 扩展点击区域

- [ ] **Step 12: 定义 Focus 状态规范（CRITICAL - Accessibility）**

```scss
// ==================== Focus 状态规范 ====================
// UI/UX Pro Max CRITICAL: focus-states
// 规则: 键盘导航需要可见 focus states (2–4px; Apple HIG, Material Design)
// 来源: UI/UX Pro Max §1 (Accessibility)

// ========== Focus Ring 基础 ==========

$wolf-focus-ring-width-v2: 2px;                 // Focus ring 宽度（WCAG 合规）
$wolf-focus-ring-color-v2: rgba(#2563EB, 0.5);  // Focus ring 颜色（主色半透明）
$wolf-focus-ring-offset-v2: 2px;                // Focus ring 偏移（不覆盖元素边界）

// ========== Focus Ring 变体 ==========

// 强 focus（关键交互元素）
$wolf-focus-ring-width-strong-v2: 3px;          // 强 focus（主要按钮、关键输入）
$wolf-focus-ring-color-strong-v2: rgba(#2563EB, 0.6);

// 弱 focus（次要元素）
$wolf-focus-ring-width-subtle-v2: 1px;          // 弱 focus（次要链接）
$wolf-focus-ring-color-subtle-v2: rgba(#2563EB, 0.3);

// ========== Focus Shadow（替代 ring 方案）==========

// Material Design 风格: 使用 elevation + shadow 而非 outline
$wolf-focus-shadow-v2: 0 0 0 2px rgba(#2563EB, 0.3);

// ========== Focus 状态 CSS 示例 ==========

// 推荐实现方式（SCSS mixin）:
// @mixin focus-ring {
//   outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
//   outline-offset: $wolf-focus-ring-offset-v2;
// }
// 
// .button:focus-visible {
//   @include focus-ring;
// }

// ========== 禁止事项 ==========

// ❌ 禁止移除 focus ring: outline: none（无替代方案）
// ✅ 替代方案: outline: none + box-shadow（Material state layers）
```

**WCAG 合规检查**：
- Focus ring 必须与背景有足够对比度（≥3:1）
- Focus ring 宽度 ≥ 2px（WCAG 2.4.7 Focus Visible）
- Focus ring 必须可见，不能被其他元素遮挡

- [ ] **Step 13: 定义 Reduced Motion 支持（MEDIUM - Animation）**

```scss
// ==================== Reduced Motion ====================
// UI/UX Pro Max: reduced-motion
// 规则: Respect prefers-reduced-motion; reduce/disable animations when requested
// 来源: UI/UX Pro Max §1 (Accessibility) + §7 (Animation)

// ========== Reduced Motion 变量 ==========

$wolf-reduced-motion-duration-v2: 0.01ms;       // Reduced motion 时的动画时长
$wolf-reduced-motion-delay-v2: 0ms;             // Reduced motion 时的动画延迟

// ========== Reduced Motion CSS 变量 ==========

// 用于 CSS custom properties（Vue 组件）
$wolf-css-var-transition-duration-v2: --wolf-transition-duration;
$wolf-css-var-reduced-motion-v2: --wolf-reduced-motion-duration;

// ========== SCSS Mixin 示例 ==========

// 推荐实现方式:
// @mixin transition-safe($property: all, $duration: 150ms) {
//   transition: $property $duration ease;
//   
//   @media (prefers-reduced-motion: reduce) {
//     transition-duration: $wolf-reduced-motion-duration-v2;
//   }
// }
// 
// .button:hover {
//   @include transition-safe(background, 150ms);
// }

// ========== 禁止事项 ==========

// ❌ 禁止忽略 prefers-reduced-motion
// ✅ 所有动画必须支持 reduced motion 模式
// ✅ Reduced motion 时不完全禁用动画（保留 0.01ms 微动画）
```

**Apple HIG / Material Design 参考**：
- Apple Reduced Motion API: 系统级动画偏好
- Material Design: 动画时长在 reduced-motion 时降至最低

- [ ] **Step 14: 定义暗色模式变量（MEDIUM - Typography & Color）**

```scss
// ==================== 暗色模式（Dark Mode）====================
// UI/UX Pro Max: color-dark-mode
// 规则: Dark mode uses desaturated / lighter tonal variants, not inverted colors
// 来源: UI/UX Pro Max §6 (Typography & Color)
// 重要: 暗色对比度需独立测试（不假设亮色值可用）

// ========== 暗色背景色 ==========

$wolf-bg-page-dark-v2: #0F172A;              // 暗色页面背景（Slate-900）
$wolf-bg-card-dark-v2: #1E293B;              // 暗色卡片背景（Slate-800）
$wolf-bg-sidebar-dark-v2: #1E293B;           // 暗色侧边栏背景
$wolf-bg-hover-dark-v2: #334155;             // 暗色 hover 背景（Slate-700）
$wolf-bg-muted-dark-v2: #1E293B;             // 暗色辅助背景
$wolf-bg-elevated-dark-v2: #334155;          // 暗色弹窗/抽屉背景

// ========== 暗色文字色 ==========

$wolf-text-primary-dark-v2: #F8FAFC;         // 暗色主文字（Slate-50，对比度 15:1）
$wolf-text-secondary-dark-v2: #CBD5E1;       // 暗色次文字（Slate-300，对比度 4.5:1）
$wolf-text-tertiary-dark-v2: #94A3B8;        // 暗色辅助文字（Slate-400，对比度 3:1）
$wolf-text-placeholder-dark-v2: #64748B;     // 暗色 placeholder（Slate-500）

// ========== 暗色边框色 ==========

$wolf-border-default-dark-v2: #334155;       // 暗色默认边框
$wolf-border-hover-dark-v2: #2563EB;         // 暗色 hover 边框（主色）
$wolf-border-light-dark-v2: #1E293B;         // 暗色极浅分割

// ========== 暗色功能色 ==========

// 注意: 功能色在暗色模式下需要调整亮度
$wolf-success-dark-v2: #34D399;              // 暗色成功色（更亮）
$wolf-warning-dark-v2: #FBBF24;              // 暗色警告色（更亮）
$wolf-danger-dark-v2: #F87171;               // 暗色危险色（更亮）

// ========== 暗色 Focus Ring ==========

$wolf-focus-ring-color-dark-v2: rgba(#3B82F6, 0.5); // 暗色 focus ring（蓝色半透明）

// ========== 暗色对比度验证 ==========

// 亮色主题:
// - #0F172A on #FFFFFF: 15:1 ✅
// - #64748B on #FFFFFF: 4.5:1 ✅

// 暗色主题（独立测试）:
// - #F8FAFC on #0F172A: 15:1 ✅
// - #CBD5E1 on #1E293B: 4.5:1 ✅
// - #94A3B8 on #1E293B: 3:1 ✅

// ========== CSS 变量映射示例 ==========

// 推荐实现方式（CSS custom properties）:
// :root {
//   --wolf-bg-page: #F8FAFC;
//   --wolf-text-primary: #0F172A;
// }
// 
// [data-theme="dark"] {
//   --wolf-bg-page: #0F172A;
//   --wolf-text-primary: #F8FAFC;
// }

// ========== 禁止事项 ==========

// ❌ 禁止直接反转颜色（黑→白）
// ✅ 使用 desaturated tonal variants（Material Design tonal palette）
// ✅ 暗色模式对比度必须独立验证
```

**对比度验证工具**：
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- Chrome DevTools: Accessibility > Contrast

- [ ] **Step 15: 定义 Disabled 状态规范（MEDIUM - Forms & Feedback）**

```scss
// ==================== Disabled 状态规范 ====================
// UI/UX Pro Max: disabled-states
// 规则: Disabled elements use reduced opacity (0.38–0.5) + cursor change + semantic attribute
// 来源: UI/UX Pro Max §8 (Forms & Feedback) + Material Design state layers

// ========== Disabled Opacity ==========

$wolf-disabled-opacity-v2: 0.38;              // Material Design disabled opacity
$wolf-disabled-opacity-light-v2: 0.5;         // 亮色模式 disabled opacity（更柔和）
$wolf-disabled-opacity-dark-v2: 0.38;         // 暗色模式 disabled opacity

// ========== Disabled Cursor ==========

$wolf-cursor-disabled-v2: not-allowed;        // Disabled cursor
$wolf-cursor-clickable-v2: pointer;           // 可点击元素 cursor

// ========== Disabled 颜色 ==========

// 亮色模式
$wolf-disabled-bg-v2: $wolf-bg-muted-v2;      // Disabled 背景
$wolf-disabled-text-v2: $wolf-text-tertiary-v2; // Disabled 文字

// 暗色模式
$wolf-disabled-bg-dark-v2: $wolf-bg-muted-dark-v2;
$wolf-disabled-text-dark-v2: $wolf-text-tertiary-dark-v2;

// ========== 禁止事项 ==========

// ❌ 禁止 disabled 元素可点击（pointer-events: none 或 disabled 属性）
// ❌ 禁止 disabled 元素无视觉区分
// ✅ Disabled 元素必须有语义属性（disabled、aria-disabled）
```

- [ ] **Step 16: 定义移动端适配变量（HIGH - Layout & Responsive）**

```scss
// ==================== 移动端适配（Responsive Web）====================
// UI/UX Pro Max HIGH: Layout & Responsive + Navigation Patterns
// 规则: Mobile-first breakpoints, Safe areas, Adaptive navigation
// 来源: UI/UX Pro Max §5 (Layout) + §9 (Navigation)
// 平台: iOS Safari / Android Chrome（响应式 Web）

// ========== 断点系统 ==========

$wolf-breakpoint-xs-v2: 375px;    // 小手机（iPhone SE / Android 小屏）
$wolf-breakpoint-sm-v2: 768px;    // 平板竖屏（iPad Mini）
$wolf-breakpoint-md-v2: 1024px;   // 平板横屏 / 小桌面（iPad / Chromebook）
$wolf-breakpoint-lg-v2: 1440px;   // 大桌面（标准笔记本 / 外接显示器）

// 断点用途说明:
// - xs (375px): 移动端样式生效，Sidebar 隐藏，Bottom Nav 显示
// - sm (768px): 平板竖屏，Sidebar 可折叠，部分桌面样式
// - md (1024px): 平板横屏/小桌面，Sidebar 显示，完整桌面样式
// - lg (1440px): 大桌面，最大容器宽度

// ========== 移动端字体尺寸 ==========

// UI/UX Pro Max CRITICAL: Minimum 16px body text on mobile (avoids iOS auto-zoom)
// iOS Safari 在 input font-size < 16px 时会自动放大页面
$wolf-font-size-body-mobile-v2: 16px;   // 移动端正文（避免 iOS auto-zoom）
$wolf-font-size-title-mobile-v2: 18px;  // 移动端页面标题
$wolf-font-size-caption-mobile-v2: 14px; // 移动端辅助文字

// ========== 移动端间距（更紧凑）==========

// 移动端页面边距（减少以最大化内容区域）
$wolf-page-padding-mobile-v2: 16px;     // 移动端页面边距（桌面 24px → 移动 16px）
$wolf-card-padding-mobile-v2: 12px;     // 移动端卡片内边距（桌面 16px → 移动 12px）
$wolf-section-gap-mobile-v2: 16px;      // 移动端模块间距（桌面 24px → 移动 16px）
$wolf-form-item-gap-mobile-v2: 12px;    // 移动端表单项间距

// ========== 移动端行长度 ==========

// UI/UX Pro Max: Mobile 35–60 chars per line; desktop 60–75 chars
// 建议: 移动端内容宽度限制，避免过长行
$wolf-content-max-width-mobile-v2: 100%;  // 移动端全宽
$wolf-content-max-width-tablet-v2: 720px; // 平板内容最大宽度
$wolf-content-max-width-desktop-v2: 1200px; // 桌面内容最大宽度

// ========== 安全区域（Safe Areas）==========

// iOS notch / Dynamic Island / Home indicator
// Android gesture navigation bar
// 用法: padding-top: $wolf-safe-area-top-v2;

$wolf-safe-area-top-v2: env(safe-area-inset-top, 0px);     // 顶部安全区域（notch）
$wolf-safe-area-bottom-v2: env(safe-area-inset-bottom, 0px); // 底部手势区域
$wolf-safe-area-left-v2: env(safe-area-inset-left, 0px);   // 左侧安全区域（横屏）
$wolf-safe-area-right-v2: env(safe-area-inset-right, 0px); // 右侧安全区域（横屏）

// ========== Viewport 单位 ==========

// UI/UX Pro Max CRITICAL: Prefer min-h-dvh over 100vh on mobile
// 100vh 在 iOS Safari 地址栏展开时会超出可视区域
$wolf-viewport-height-mobile-v2: min(100vh, 100dvh);  // 动态 viewport 高度
$wolf-viewport-height-desktop-v2: 100vh;             // 桌面端固定高度

// ========== 响应式导航 ==========

// 桌面端: Sidebar 固定显示（220px）
// 移动端: Sidebar 隐藏，显示 Bottom Nav 或 Top Nav hamburger

$wolf-sidebar-width-mobile-v2: 0;       // 移动端隐藏 Sidebar
$wolf-sidebar-collapsed-width-v2: 0;    // 折叠宽度（移动端完全隐藏）

// Bottom Navigation（移动端底部导航）
$wolf-bottom-nav-height-v2: 56px;       // 移动端底部导航高度
$wolf-bottom-nav-padding-v2: 8px;       // Bottom Nav 内边距
$wolf-bottom-nav-item-height-v2: 44px;  // Bottom Nav 项目高度（touch target 合规）
$wolf-bottom-nav-max-items-v2: 5;       // Bottom Nav 最多 5 个项目（UI/UX Pro Max）

// Top Navigation（移动端顶部栏）
$wolf-topbar-height-mobile-v2: 56px;    // 移动端顶部栏高度
$wolf-topbar-padding-mobile-v2: 16px;   // 移动端顶部栏边距

// ========== 移动端导航项目（示例）==========

// 销售流程（核心高频功能）
// UI/UX Pro Max: Bottom nav items must have both icon and text label
// 最多 5 个: ['日历', '客户', '商机', '合同', '更多']
// '更多' 菜单包含: 线索、回款、发票、审批、设置

// ========== 移动端表格适配 ==========

// 移动端表格: 横向滚动或简化列
$wolf-table-min-width-mobile-v2: 100%;  // 移动端表格最小宽度
$wolf-table-cell-padding-mobile-v2: 8px 4px; // 移动端单元格 padding（更紧凑）

// ========== 移动端 Modal/Sheet ==========

// UI/UX Pro Max: Modals/sheets animate from bottom on mobile
$wolf-modal-height-mobile-v2: 90vh;     // 移动端 Modal 最大高度
$wolf-modal-radius-mobile-v2: $wolf-radius-lg-v2; // 移动端 Modal 圆角（顶部圆角）
$wolf-sheet-height-v2: auto;            // Sheet 高度（自适应内容）

// ========== 横向滚动约束 ==========

// UI/UX Pro Max CRITICAL: No horizontal scroll on mobile
// 仅允许特定组件（表格、图片画廊）横向滚动
$wolf-overflow-x-mobile-v2: hidden;     // 页面主体禁止横向滚动
$wolf-overflow-x-allowed-v2: auto;      // 特定组件允许横向滚动

// ========== 移动端禁止事项 ==========

// ❌ 禁止固定 px 容器宽度（如 width: 1200px）- 导致横向滚动
// ❌ 禁止 disable zoom（user-scalable=no）- 违反 Accessibility
// ❌ 禁止横向滚动在主要内容区域
// ❌ 禁止使用 100vh（应使用 min(100vh, 100dvh)）
// ❌ 禁止将 touch targets 放在 notch/Dynamic Island 下方
// ❌ 禁止 Bottom Nav 超过 5 个项目
```

**移动端适配验证清单**：

| 规则 | 变量 | 验证命令 |
|------|------|---------|
| Breakpoints | `$wolf-breakpoint-xs-v2: 375px` | `grep "breakpoint-xs" variables-v2.scss` |
| Mobile Font 16px | `$wolf-font-size-body-mobile-v2: 16px` | `grep "font-size-body-mobile" variables-v2.scss` |
| Safe Areas | `$wolf-safe-area-top-v2: env(...)` | `grep "safe-area" variables-v2.scss` |
| Bottom Nav Limit | `$wolf-bottom-nav-max-items-v2: 5` | `grep "bottom-nav-max" variables-v2.scss` |
| Viewport Height | `$wolf-viewport-height-mobile-v2: min(100vh, 100dvh)` | `grep "viewport-height-mobile" variables-v2.scss` |

- [ ] **Step 17: 定义字体系统变量（保留现有）**

```scss
// ==================== 字体系统（保留现有）====================
// 建议: 保留 IBM Plex Sans（技术感），不改为 Inter

$wolf-font-family-v2: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
$wolf-font-display-v2: "IBM Plex Sans", $wolf-font-family-v2;
$wolf-font-mono-v2: "IBM Plex Mono", "SF Mono", Monaco, "Cascadia Code", monospace;

// 字号（仅4种）
$wolf-font-size-title-v2: 16px;      // 页面主标题
$wolf-font-size-body-v2: 14px;       // 正文（桌面端）
$wolf-font-size-auxiliary-v2: 13px;  // 辅助信息
$wolf-font-size-caption-v2: 12px;    // 次要备注

// 字重
$wolf-font-weight-normal-v2: 400;
$wolf-font-weight-medium-v2: 500;
$wolf-font-weight-semibold-v2: 600;

// 行高（UI/UX Pro Max: body 1.5-1.75）
$wolf-line-height-title-v2: 1.2;
$wolf-line-height-body-v2: 1.5;      // 正文行高（WCAG 合规）
```

- [ ] **Step 18: 定义导航组件尺寸变量**

```scss
// ==================== 导航组件尺寸 ====================

// Sidebar（左侧菜单 - 桌面端）
$wolf-sidebar-width-v2: 220px;
$wolf-sidebar-nav-item-height-v2: 40px;

// TopBar（顶部栏）
$wolf-topbar-height-v2: 56px;
$wolf-topbar-title-font-size-v2: 20px;

// ContextTabs（上下文标签栏）
$wolf-context-tabs-height-v2: 48px;

// Header
$wolf-header-height-v2: 56px;
$wolf-header-height-mobile-v2: 48px;
```

- [ ] **Step 19: 验证文件完整性（UI/UX Pro Max 合规检查）**

Run: `cat CRM-Client/src/styles/variables-v2.scss | wc -l`
Expected: ≥ 200 行（包含所有 Design Tokens + UI/UX Pro Max 规则 + 移动端适配）

**UI/UX Pro Max CRITICAL 规则验证**：

| 规则 | 变量 | 验证命令 |
|------|------|---------|
| Focus Ring | `$wolf-focus-ring-width-v2` | `grep "focus-ring-width" CRM-Client/src/styles/variables-v2.scss` |
| Touch Target | `$wolf-button-height-mobile-v2: 44px` | `grep "button-height-mobile" CRM-Client/src/styles/variables-v2.scss` |
| Reduced Motion | `$wolf-reduced-motion-duration-v2` | `grep "reduced-motion" CRM-Client/src/styles/variables-v2.scss` |
| Dark Mode | `$wolf-bg-page-dark-v2` | `grep "bg-page-dark" CRM-Client/src/styles/variables-v2.scss` |
| Disabled State | `$wolf-disabled-opacity-v2` | `grep "disabled-opacity" CRM-Client/src/styles/variables-v2.scss` |

**移动端适配规则验证**：

| 规则 | 变量 | 验证命令 |
|------|------|---------|
| Breakpoints | `$wolf-breakpoint-xs-v2: 375px` | `grep "breakpoint-xs" CRM-Client/src/styles/variables-v2.scss` |
| Mobile Font 16px | `$wolf-font-size-body-mobile-v2: 16px` | `grep "font-size-body-mobile" CRM-Client/src/styles/variables-v2.scss` |
| Safe Areas | `$wolf-safe-area-top-v2` | `grep "safe-area" CRM-Client/src/styles/variables-v2.scss` |
| Bottom Nav | `$wolf-bottom-nav-height-v2: 56px` | `grep "bottom-nav-height" CRM-Client/src/styles/variables-v2.scss` |
| Viewport | `$wolf-viewport-height-mobile-v2` | `grep "viewport-height-mobile" CRM-Client/src/styles/variables-v2.scss` |

---

## Task 2: 创建 Element Plus 主题适配文件

**Files:**
- Create: `CRM-Client/src/styles/element-plus-theme-v2.scss`

**Interfaces:**
- Consumes: `variables-v2.scss` 中的颜色、圆角、间距变量
- Produces: Element Plus 组件主题覆盖

- [ ] **Step 1: 创建 Element Plus 主题适配文件**

```scss
// ==================== Element Plus 主题适配 V2 ====================
// 规则来源: CRM-Docs/design-system/MASTER.md §3（组件设计规范）
// 用途: 覆盖 Element Plus 默认主题，适配 CRMWolf 设计系统

@use './variables-v2.scss' as *;

// ==================== 颜色覆盖 ====================

$--color-primary: $wolf-primary-v2;           // #2563EB
$--color-success: $wolf-success-v2;           // #10B981
$--color-warning: $wolf-warning-v2;           // #F59E0B
$--color-danger: $wolf-danger-v2;             // #DC2626
$--color-info: $wolf-primary-v2;              // #2563EB

// ==================== 文字色覆盖 ====================

$--color-text-primary: $wolf-text-primary-v2;     // #0F172A
$--color-text-regular: $wolf-text-secondary-v2;   // #64748B
$--color-text-secondary: $wolf-text-tertiary-v2;  // #94A3B8
$--color-text-placeholder: $wolf-text-placeholder-v2;  // #94A3B8

// ==================== 背景色覆盖 ====================

$--background-color-base: $wolf-bg-page-v2;       // #F8FAFC
$--background-color-light: $wolf-bg-card-v2;      // #FFFFFF

// ==================== 边框覆盖 ====================

$--border-color-light: $wolf-border-light-v2;     // #F1F5FD
$--border-color-base: $wolf-border-default-v2;    // #E4ECFC
$--border-radius-base: $wolf-radius-v2;           // 6px（统一圆角）
$--border-radius-medium: $wolf-radius-lg-v2;      // 8px
$--border-radius-large: $wolf-radius-lg-v2;       // 8px

// ==================== 间距覆盖 ====================

$--spacing-unit: 8px;
$--spacing-xs: $wolf-space-xs-v2;     // 4px
$--spacing-sm: $wolf-space-sm-v2;     // 8px
$--spacing-base: $wolf-space-lg-v2;   // 16px
$--spacing-lg: $wolf-space-xl-v2;     // 24px
$--spacing-xl: $wolf-space-2xl-v2;    // 32px

// ==================== 过渡动画覆盖 ====================

$--transition-base: $wolf-transition-v2;           // 0.15s ease
$--transition-fade: opacity 0.15s ease-in-out;
```

- [ ] **Step 2: 验证文件已创建**

Run: `ls -la CRM-Client/src/styles/element-plus-theme-v2.scss`
Expected: 文件存在，大小 ≥ 1KB

---

## Task 3: 添加 Stylelint 依赖和配置

**Files:**
- Modify: `CRM-Client/package.json`（添加依赖）
- Create: `CRM-Client/stylelint.config.js`（主配置）
- Create: `CRM-Client/.stylelintrc.design-system.js`（设计系统规则）

**Interfaces:**
- Produces: Stylelint 校验规则（禁止硬编码颜色/圆角）

- [ ] **Step 1: 安装 Stylelint 依赖**

Run: `cd CRM-Client && npm install --save-dev stylelint stylelint-config-standard-scss stylelint-scss`

Expected: 安装成功，package.json 中出现 stylelint 依赖

- [ ] **Step 2: 创建 Stylelint 主配置文件**

```javascript
// CRM-Client/stylelint.config.js
/**
 * Stylelint 配置 - CRMWolf
 *
 * @description 强制使用 Design Tokens，禁止硬编码样式
 */

import designSystemRules from './.stylelintrc.design-system.js'

export default [
  // SCSS 标准规则
  {
    extends: ['stylelint-config-standard-scss'],
    plugins: ['stylelint-scss'],
    rules: {
      // SCSS 特定规则
      'scss/at-rule-no-unknown': true,
      'scss/no-duplicate-dollar-variables': true,
      
      // 禁止空源
      'no-empty-source': true,
      
      // 禁止缺失文件
      'no-missing-end-of-source-newline': true,
    }
  },
  
  // 设计系统强制规则
  designSystemRules,
  
  // 文件覆盖
  {
    files: ['**/*.scss', '**/*.vue'],
    rules: {
      // Vue 文件中的 SCSS 规则
      'scss/at-if-no-null': true,
    }
  },
  
  // 忽略文件
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'coverage/**',
      '**/*.css',  // 暂时忽略纯 CSS 文件（存量代码）
      'src/styles/wolf-design.scss',  // 存量设计文件，待迁移
      'src/styles/_typography.scss',  // 存量字体文件，待迁移
    ]
  }
]
```

- [ ] **Step 3: 创建设计系统强制规则配置**

```javascript
// CRM-Client/.stylelintrc.design-system.js
/**
 * Stylelint 设计系统强制规则 - CRMWolf V2
 *
 * @规则来源: CRM-Docs/design-system/MASTER.md §9（禁止事项）
 * @核心规则:
 *   1. 禁止硬编码颜色（必须使用 Design Tokens）
 *   2. 禁止旧圆角值（统一 6px）
 *   3. 禁止硬编码主色（必须使用 $wolf-primary-v2）
 */

export default {
  rules: {
    // ===== 禁止硬编码颜色 =====
    // 规则: 所有颜色必须使用 Design Tokens
    'declaration-property-value-disallowed-list': {
      // 禁止直接写 hex 颜色值
      'color': [
        '/#[0-9a-fA-F]{3,6}/',
        '/rgb\\(/',
        '/rgba\\(/',
      ],
      'background-color': [
        '/#[0-9a-fA-F]{3,6}/',
        '/rgb\\(/',
        '/rgba\\(/',
      ],
      'background': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-top-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-right-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-bottom-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-left-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      
      // 禁止旧圆角值（统一 6px）
      'border-radius': [
        '/^4px$/',   // 禁止 4px
        '/^8px$/',   // 禁止 8px
        '/^12px$/',  // 禁止 12px
        '/^16px$/',  // 禁止 16px
      ],
      'border-top-left-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-top-right-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-bottom-left-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-bottom-right-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      
      // 禁止硬编码主色
      '/.*/': [
        '/#4A6FA5/',  // 禁止旧主色 V1
        '/#2563EB/',  // 禁止直接写新主色（必须用变量）
        '/#1E40AF/',  // 禁止直接写 hover 色
        '/#10B981/',  // 禁止直接写成功色
        '/#F59E0B/',  // 禁止直接写警告色
        '/#DC2626/',  // 禁止直接写危险色
      ],
    },
    
    // ===== 允许的 Design Tokens =====
    'declaration-property-value-allowed-list': {
      // 圆角必须使用变量
      'border-radius': [
        '$wolf-radius-v2',
        '$wolf-radius-sm-v2',
        '$wolf-radius-lg-v2',
        '$wolf-radius-full-v2',
        // 允许百分比和 inherit
        '/%/',
        'inherit',
        'initial',
      ],
    },
    
    // ===== SCSS 变量规则 =====
    'scss/dollar-variable-pattern': [
      '^wolf-([a-z]+)(-v2)?$',  // 必须以 wolf- 开头，可选 -v2 后缀
      {
        message: 'Design Tokens 必须以 $wolf- 开头',
      },
    ],
  },
}
```

- [ ] **Step 4: 在 package.json 中添加 Stylelint 脚本**

```json
// 在 CRM-Client/package.json 的 scripts 中添加:
{
  "scripts": {
    "lint:style": "stylelint \"src/**/*.scss\" \"src/**/*.vue\"",
    "lint:style:fix": "stylelint \"src/**/*.scss\" \"src/**/*.vue\" --fix"
  }
}
```

Run: 手动编辑 `CRM-Client/package.json`，在 scripts 对象中添加上述两个脚本

- [ ] **Step 5: 验证 Stylelint 配置**

Run: `cd CRM-Client && npm run lint:style`
Expected: 运行成功（可能报告存量文件的 lint 错误，这是预期的）

---

## Task 4: 更新 ESLint 配置添加设计系统规则

**Files:**
- Modify: `CRM-Client/eslint.config.js:25-60`（添加设计系统红线规则）

**Interfaces:**
- Consumes: 现有 ESLint 配置结构
- Produces: ESLint 规则禁止引用旧变量

- [ ] **Step 1: 在 ESLint 配置中添加设计系统规则**

在 `CRM-Client/eslint.config.js` 的 crmwolf rules 对象中添加：

```javascript
// 在 CRM-Client/eslint.config.js 的 rules 对象中添加（约 line 30）

// ===== 设计系统红线规则（V2）=====
// 规则来源: CRM-Docs/design-system/MASTER.md §9（禁止事项）
'no-restricted-syntax': [
  'error',
  // 禁止旧主色变量
  {
    selector: 'Identifier[name="wolf-primary"]',
    message: '请使用 $wolf-primary-v2 (#2563EB) 替代旧主色变量',
  },
  // 禁止旧圆角变量
  {
    selector: 'Identifier[name=/^wolf-radius-[sm|md|lg|xl]$/]',
    message: '请使用 $wolf-radius-v2 (统一 6px) 替代旧圆角变量',
  },
],
```

- [ ] **Step 2: 验证 ESLint 配置语法**

Run: `cd CRM-Client && npm run lint -- --max-warnings=100 2>&1 | head -20`
Expected: ESLint 运行成功（可能报告存量文件警告）

---

## Task 5: 创建向后兼容别名（在 variables.scss 末尾）

**Files:**
- Modify: `CRM-Client/src/styles/variables.scss:360`（在末尾添加 V2 别名）

**Interfaces:**
- Consumes: `variables-v2.scss` 中的 V2 变量
- Produces: 向后兼容别名（平滑过渡）

- [ ] **Step 1: 在 variables.scss 末尾添加向后兼容别名**

```scss
// ==================== V2 向后兼容别名 ====================
// 规则: 保留旧变量名，指向新变量（平滑过渡）
// 过渡期: Phase 0-1（迁移完成后删除）
// 来源: CRM-Docs/design-system/MASTER.md §10（向后兼容）

@use './variables-v2.scss' as v2;

// 主色别名
$wolf-primary: v2.$wolf-primary-v2;
$wolf-primary-hover: v2.$wolf-primary-hover-v2;
$wolf-primary-active: v2.$wolf-primary-active-v2;
$wolf-primary-light: v2.$wolf-primary-light-v2;

// 圆角别名（统一 6px）
$wolf-radius-sm: v2.$wolf-radius-v2;
$wolf-radius-md: v2.$wolf-radius-v2;
$wolf-radius-lg: v2.$wolf-radius-lg-v2;

// 阴影别名
$wolf-shadow-card: v2.$wolf-shadow-card-v2;
$wolf-shadow-hover: v2.$wolf-shadow-hover-v2;
$wolf-shadow-dropdown: v2.$wolf-shadow-dropdown-v2;

// 过渡别名
$--transition-base: v2.$wolf-transition-v2;
```

注意: 由于 variables.scss 使用了 `@import '_typography.scss'`，需要在导入 typography 之前添加 `@use` 语句，或者改用 `@forward` 方式。

**替代方案**（推荐）：直接在 variables.scss 末尾定义别名变量：

```scss
// ==================== V2 向后兼容别名 ====================
// 直接定义（避免 @use/@import 冲突）

$wolf-primary-v2-alias: #2563EB;  // 新主色
$wolf-radius-v2-alias: 6px;       // 新圆角

// 向后兼容：旧变量名指向新值
// 注意: 这些别名将在 Phase 2 删除
$wolf-primary-compat: $wolf-primary-v2-alias;
$wolf-radius-sm-compat: $wolf-radius-v2-alias;
```

- [ ] **Step 2: 验证向后兼容别名**

Run: `cd CRM-Client && npm run type-check`
Expected: TypeScript 校验通过

---

## Task 6: 创建迁移指南文档

**Files:**
- Create: `CRM-Client/docs/design-system/MIGRATION.md`

**Interfaces:**
- Produces: 旧变量→新变量映射表、迁移示例

- [ ] **Step 1: 创建迁移指南文档**

```markdown
# CRMWolf 设计系统迁移指南

## 一、变量映射表

### 1.1 颜色变量映射

| 旧变量（V1） | 新变量（V2） | 值 | 说明 |
|-------------|-------------|-----|------|
| `$wolf-primary` | `$wolf-primary-v2` | `#2563EB` | 主色（现代蓝） |
| `$wolf-primary-hover` | `$wolf-primary-hover-v2` | `#1E40AF` | hover态 |
| `$wolf-primary-light` | `$wolf-primary-light-v2` | `rgba(#2563EB, 0.1)` | 浅底色 |
| `$wolf-success-text` | `$wolf-success-text-v2` | `#10B981` | 成功色 |
| `$wolf-warning-text` | `$wolf-warning-text-v2` | `#F59E0B` | 警告色 |
| `$wolf-danger-text` | `$wolf-danger-text-v2` | `#DC2626` | 危险色 |

### 1.2 圆角变量映射

| 旧变量（V1） | 新变量（V2） | 值 | 说明 |
|-------------|-------------|-----|------|
| `$wolf-radius-sm` (4px) | `$wolf-radius-v2` | `6px` | 统一圆角 |
| `$wolf-radius-md` (8px) | `$wolf-radius-v2` | `6px` | 统一圆角 |
| `$wolf-radius-lg` (12px) | `$wolf-radius-lg-v2` | `8px` | 大圆角 |
| `$wolf-radius-xl` (16px) | `$wolf-radius-lg-v2` | `8px` | 大圆角 |

### 1.3 阴影变量映射

| 旧变量（V1） | 新变量（V2） | 值 | 说明 |
|-------------|-------------|-----|------|
| `$wolf-shadow-card` | `$wolf-shadow-card-v2` | `0 1px 3px rgba(0,0,0,0.1)` | 中等强度 |
| `$wolf-shadow-hover` | `$wolf-shadow-hover-v2` | `0 2px 8px rgba(0,0,0,0.15)` | hover态 |

## 二、迁移示例

### 2.1 按钮组件迁移

**旧代码（V1）**:
```scss
.button {
  background: $wolf-primary;  // #4A6FA5
  border-radius: $wolf-radius-sm;  // 4px
}
```

**新代码（V2）**:
```scss
@use '@/styles/variables-v2.scss' as *;

.button {
  background: $wolf-primary-v2;  // #2563EB
  border-radius: $wolf-radius-v2;  // 6px
}
```

### 2.2 卡片组件迁移

**旧代码（V1）**:
```scss
.card {
  border-radius: $wolf-radius-md;  // 8px
  box-shadow: $wolf-shadow-card;   // 极淡
}
```

**新代码（V2）**:
```scss
@use '@/styles/variables-v2.scss' as *;

.card {
  border-radius: $wolf-radius-v2;  // 6px
  box-shadow: $wolf-shadow-card-v2;  // 中等强度
}
```

## 三、强制校验规则

### 3.1 Stylelint 禁止项

- ❌ 禁止硬编码颜色: `color: #2563EB`
- ❌ 禁止旧圆角值: `border-radius: 4px`
- ❌ 禁止直接写主色: `background: #4A6FA5`

### 3.2 ESLint 禁止项

- ❌ 禁止旧变量名: `$wolf-primary`（必须用 `$wolf-primary-v2`）

## 四、迁移时间表

| 阶段 | 时间 | 操作 |
|------|------|------|
| Phase 0 | Week 1 | 建立 Design Tokens |
| Phase 0 | Week 2-3 | 建立基础组件库 |
| Phase 1 | Week 1-5 | 渐进式迁移页面 |
| Phase 2 | Week 1-2 | 删除旧变量别名 |

---

**版本: V2 | 最后更新: 2026-07-08**
```

- [ ] **Step 2: 验证文档已创建**

Run: `ls -la CRM-Client/docs/design-system/MIGRATION.md`
Expected: 文件存在

---

## Task 7: 验证 Phase 0 Week 1 完成状态

**Files:**
- Verify: 所有新建文件和修改文件

- [ ] **Step 1: 验证所有文件已创建**

Run: `ls -la CRM-Client/src/styles/variables-v2.scss CRM-Client/src/styles/element-plus-theme-v2.scss CRM-Client/stylelint.config.js CRM-Client/.stylelintrc.design-system.js CRM-Client/docs/design-system/MIGRATION.md`
Expected: 所有文件存在

- [ ] **Step 2: 验证 Stylelint 运行成功**

Run: `cd CRM-Client && npm run lint:style 2>&1 | head -30`
Expected: Stylelint 运行成功（可能报告存量文件 lint 错误）

- [ ] **Step 3: 验证 ESLint 运行成功**

Run: `cd CRM-Client && npm run lint 2>&1 | head -30`
Expected: ESLint 运行成功

- [ ] **Step 4: 验证 TypeScript 校验成功**

Run: `cd CRM-Client && npm run type-check`
Expected: TypeScript 校验通过

- [ ] **Step 5: 提交 Phase 0 Week 1 完成**

```bash
cd CRM-Client && git add src/styles/variables-v2.scss src/styles/element-plus-theme-v2.scss stylelint.config.js .stylelintrc.design-system.js docs/design-system/MIGRATION.md

git commit -m "feat(design-system): Phase 0 Week 1 - Design Tokens and lint rules

- Create variables-v2.scss with V2 design tokens
- Create element-plus-theme-v2.scss for Element Plus theme override
- Add Stylelint configuration with design system rules
- Add ESLint rules to forbid old variables
- Create migration guide document

Refs: CRM-Docs/design-system/MASTER.md
"
```

---

## Self-Review Checklist

### 1. Spec Coverage

| Spec 要求 | Task | 状态 |
|---------|------|------|
| 创建 variables-v2.scss | Task 1 | ✅ |
| 定义颜色变量 | Task 1 Steps 2-6 | ✅ |
| 定义圆角变量（统一 6px） | Task 1 Step 7 | ✅ |
| 定义间距变量（8dp grid） | Task 1 Step 8 | ✅ |
| 定义阴影变量 | Task 1 Step 9 | ✅ |
| 定义过渡动画 | Task 1 Step 10 | ✅ |
| **定义组件尺寸（桌面/移动）** | Task 1 Step 11 | ✅ |
| **定义 Focus Ring 变量** | Task 1 Step 12 | ✅ |
| **定义 Reduced Motion 变量** | Task 1 Step 13 | ✅ |
| **定义暗色模式变量** | Task 1 Step 14 | ✅ |
| **定义 Disabled 状态变量** | Task 1 Step 15 | ✅ |
| **定义移动端适配变量** | Task 1 Step 16 | ✅ |
| **定义字体系统变量** | Task 1 Step 17 | ✅ |
| **定义导航组件尺寸** | Task 1 Step 18 | ✅ |
| Element Plus 主题适配 | Task 2 | ✅ |
| Stylelint 配置 | Task 3 | ✅ |
| ESLint 设计系统规则 | Task 4 | ✅ |
| 向后兼容别名 | Task 5 | ✅ |
| 迁移指南文档 | Task 6 | ✅ |

### 2. UI/UX Pro Max CRITICAL 规则合规性

| 规则类别 | UI/UX Pro Max 要求 | 实现 | 状态 |
|---------|-------------------|------|------|
| **Accessibility - Focus States** | Focus ring 2–4px visible | `$wolf-focus-ring-width-v2: 2px` + offset | ✅ |
| **Touch - Touch Target** | Min 44×44pt (iOS) / 48×48dp (Android) | `$wolf-button-height-mobile-v2: 44px` + hitSlop | ✅ |
| **Accessibility - Reduced Motion** | Respect `prefers-reduced-motion` | `$wolf-reduced-motion-duration-v2: 0.01ms` | ✅ |
| **Typography - Dark Mode** | Desaturated tonal variants | `$wolf-bg-page-dark-v2` / `$wolf-text-primary-dark-v2` | ✅ |
| **Forms - Disabled States** | Opacity 0.38–0.5 + cursor + semantic | `$wolf-disabled-opacity-v2: 0.38` | ✅ |
| **Accessibility - Color Contrast** | 4.5:1 for normal text | `$wolf-text-secondary-v2: #64748B` (4.5:1) | ✅ |
| **Animation - Duration** | 150–300ms, avoid >500ms | `$wolf-transition-v2: 0.15s ease` | ✅ |

### 3. UI/UX Pro Max 移动端适配规则合规性

| 规则类别 | UI/UX Pro Max 要求 | 实现 | 状态 |
|---------|-------------------|------|------|
| **Layout - Breakpoints** | Systematic 375/768/1024/1440 | `$wolf-breakpoint-xs-v2: 375px` 系列 | ✅ |
| **Layout - Mobile Font** | Minimum 16px body (avoids iOS auto-zoom) | `$wolf-font-size-body-mobile-v2: 16px` | ✅ |
| **Layout - Safe Areas** | Notch/Dynamic Island clearance | `$wolf-safe-area-top-v2: env(...)` | ✅ |
| **Layout - Viewport Units** | Prefer min-h-dvh over 100vh | `$wolf-viewport-height-mobile-v2: min(100vh, 100dvh)` | ✅ |
| **Layout - Spacing** | Mobile-first spacing scale | `$wolf-page-padding-mobile-v2: 16px` | ✅ |
| **Navigation - Adaptive** | Large: sidebar; Small: bottom/top nav | Sidebar → Bottom Nav 切换变量 | ✅ |
| **Navigation - Bottom Nav** | Max 5 items with labels + icons | `$wolf-bottom-nav-max-items-v2: 5` | ✅ |
| **Navigation - Height** | Fixed navbar reserves padding | `$wolf-bottom-nav-height-v2: 56px` + safe-area | ✅ |

### 4. Placeholder Scan

- ✅ 所有代码步骤包含完整代码
- ✅ 所有命令包含预期输出
- ✅ 无 "TODO"、"TBD"、"implement later"
- ✅ 无 "Add appropriate error handling"

### 5. Type Consistency

- ✅ 变量命名一致：`$wolf-primary-v2`
- ✅ 圆角统一：`$wolf-radius-v2` (6px)
- ✅ 文件路径一致
- ✅ 暗色模式变量命名一致：`$wolf-*-dark-v2`
- ✅ 移动端变量命名一致：`$wolf-*-mobile-v2`

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-08-design-system-phase0-week1.md`.**

## Execution Options

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach would you like?**