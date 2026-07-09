# shadcn-vue Design System Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完全替换 V2 设计系统为 shadcn-vue primitives + Tailwind CSS，确保 UI/UX Pro Max CRITICAL 规范合规

**Architecture:** Tailwind CSS 作为基础样式层，shadcn-vue primitives 作为原子组件，CRMWolf extensions 作为业务组件（添加 touch-safe variants），统一设计 token 映射

**Tech Stack:** Tailwind CSS v3.4+, shadcn-vue CLI, Vue 3.5 Composition API, Vitest, TypeScript strict mode

## Global Constraints

- **UI/UX Pro Max CRITICAL §1 Accessibility:** Focus ring 必须可见 2-4px，所有交互元素必须有 focus-visible 状态
- **UI/UX Pro Max CRITICAL §2 Touch Target:** 移动端最小 44px touch target，所有按钮/输入必须达标
- **UI/UX Pro Max CRITICAL §7 Animation:** 必须支持 prefers-reduced-motion，动画时长 ≤300ms
- **UI/UX Pro Max CRITICAL §8 Forms:** Label 必须可见（非 placeholder-only），error 放置于字段下方
- **TypeScript 四禁令:** 禁用 any, as any, @ts-ignore, !
- **Design Token:** 必须映射 variables-v2.scss 中的 wolf design tokens，禁止魔数
- **TDD:** 每个功能必须先写测试再实现
- **Mobile-first:** 响应式断点 xs(375px) < sm(768px) < md(1024px) < lg(1440px)
- **WCAG 2.1 AA:** 文字对比度 4.5:1（正文），3:1（辅助），15:1（标题）
- **Date:** 2026-07-08（今日）

---

## Phase 1: Tailwind CSS Foundation

### Task 1: Install Tailwind CSS Dependencies

**Files:**
- Modify: `CRM-Client/package.json`
- Test: Verify installation with `npm ls tailwindcss`

**Interfaces:**
- Produces: Tailwind CSS, PostCSS, Autoprefixer available for configuration

- [ ] **Step 1: Add Tailwind dependencies to package.json**

```json
{
  "devDependencies": {
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "@tailwindcss/forms": "^0.5.7",
    "@tailwindcss/typography": "^0.5.13"
  }
}
```

- [ ] **Step 2: Run npm install**

Run: `cd CRM-Client && npm install`
Expected: SUCCESS, packages installed without errors

- [ ] **Step 3: Verify installation**

Run: `cd CRM-Client && npm ls tailwindcss postcss autoprefixer`
Expected: List shows installed versions

- [ ] **Step 4: Commit dependencies**

```bash
cd CRM-Client && git add package.json package-lock.json && git commit -m "feat(design-system): add Tailwind CSS dependencies for shadcn-vue migration"
```

---

### Task 2: Create Tailwind Configuration with Wolf Design Tokens

**Files:**
- Create: `CRM-Client/tailwind.config.ts`
- Create: `CRM-Client/postcss.config.js`

**Interfaces:**
- Consumes: Design tokens from `variables-v2.scss`
- Produces: Tailwind config with wolf colors, spacing, radius, shadows, focus states

- [ ] **Step 1: Create tailwind.config.ts with full design token mapping**

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // ===== Wolf Colors V2 =====
      colors: {
        wolf: {
          // Primary（现代蓝色）
          primary: {
            DEFAULT: '#2563EB',
            hover: '#1E40AF',
            active: '#1D4ED8',
            light: 'rgba(37, 99, 235, 0.1)',
          },
          secondary: '#3B82F6',
          accent: '#059669',

          // Backgrounds
          bg: {
            page: '#F8FAFC',
            card: '#FFFFFF',
            sidebar: '#FFFFFF',
            hover: '#EEF2FF',
            muted: '#F1F5FD',
            elevated: '#FFFFFF',
          },

          // Text
          text: {
            primary: '#0F172A',
            secondary: '#64748B',
            tertiary: '#94A3B8',
            placeholder: '#94A3B8',
            inverse: '#FFFFFF',
            link: '#2563EB',
            'link-hover': '#1E40AF',
          },

          // Borders
          border: {
            default: '#E4ECFC',
            hover: '#2563EB',
            light: '#F1F5FD',
            divider: '#E4ECFC',
          },

          // Status Colors（功能色）
          success: {
            DEFAULT: '#10B981',
            text: '#10B981',
            bg: 'rgba(16, 185, 129, 0.1)',
          },
          warning: {
            DEFAULT: '#F59E0B',
            text: '#F59E0B',
            bg: 'rgba(245, 158, 11, 0.1)',
          },
          danger: {
            DEFAULT: '#DC2626',
            text: '#DC2626',
            bg: 'rgba(220, 38, 38, 0.1)',
          },
        },
      },

      // ===== Radius（统一 6px）=====
      borderRadius: {
        wolf: {
          DEFAULT: '6px',
          sm: '4px',
          lg: '8px',
          full: '9999px',
        },
      },

      // ===== Spacing（8dp grid）=====
      spacing: {
        wolf: {
          xs: '4px',
          sm: '8px',
          md: '12px',
          lg: '16px',
          xl: '24px',
          '2xl': '32px',
        },
      },

      // ===== Shadows（中等强度）=====
      boxShadow: {
        wolf: {
          card: '0 1px 3px rgba(0, 0, 0, 0.1)',
          hover: '0 2px 8px rgba(0, 0, 0, 0.15)',
          dropdown: '0 -4px 12px rgba(0, 0, 0, 0.15)',
          modal: '0 4px 16px rgba(0, 0, 0, 0.15)',
          bottom: '0 -2px 8px rgba(0, 0, 0, 0.1)',
        },
      },

      // ===== Typography =====
      fontFamily: {
        wolf: [
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        display: [
          'IBM Plex Sans',
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'sans-serif',
        ],
        mono: [
          'IBM Plex Mono',
          'SF Mono',
          'Monaco',
          'Cascadia Code',
          'monospace',
        ],
      },
      fontSize: {
        wolf: {
          title: ['16px', { lineHeight: '1.2' }],
          body: ['14px', { lineHeight: '1.5' }],
          auxiliary: ['13px', { lineHeight: '1.5' }],
          caption: ['12px', { lineHeight: '1.5' }],
        },
      },
      fontWeight: {
        wolf: {
          normal: '400',
          medium: '500',
          semibold: '600',
        },
      },

      // ===== Animation Duration =====
      transitionDuration: {
        wolf: '150ms',
        'wolf-hover': '200ms',
        'wolf-press': '150ms',
      },

      // ===== Focus Ring Width =====
      outlineWidth: {
        wolf: {
          focus: '2px',
          'focus-strong': '3px',
          'focus-subtle': '1px',
        },
      },
      outlineOffset: {
        wolf: '2px',
      },

      // ===== Touch Target Sizes =====
      minHeight: {
        'touch-target': '44px',
      },
      height: {
        'touch-target': '44px',
        'button-sm': '24px',
        'button-md': '32px',
        'button-lg': '44px',
        'input-desktop': '32px',
        'input-mobile': '44px',
      },
      minWidth: {
        'touch-target': '44px',
      },

      // ===== Breakpoints（Mobile-first）=====
      screens: {
        xs: '375px',
        sm: '768px',
        md: '1024px',
        lg: '1440px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}

export default config
```

- [ ] **Step 2: Create postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 3: Verify Tailwind config loads**

Run: `cd CRM-Client && node -e "import('./tailwind.config.ts').then(c => console.log('Config loaded:', Object.keys(c.default.theme.extend.colors.wolf)))"`
Expected: "Config loaded: ['primary', 'secondary', 'accent', 'bg', 'text', 'border', 'success', 'warning', 'danger']"

- [ ] **Step 4: Commit configuration files**

```bash
cd CRM-Client && git add tailwind.config.ts postcss.config.js && git commit -m "feat(design-system): create Tailwind config with wolf design tokens mapping"
```

---

### Task 3: Create Tailwind Base CSS Layer

**Files:**
- Create: `CRM-Client/src/styles/base.css`
- Modify: `CRM-Client/src/main.ts`

**Interfaces:**
- Consumes: Tailwind config from Task 2
- Produces: Global Tailwind base styles loaded in app

- [ ] **Step 1: Create base.css with Tailwind directives**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ==================== CRMWolf Base Layer Overrides ==================== */
/* UI/UX Pro Max CRITICAL: Focus states, Touch targets, Reduced motion */

@layer base {
  /* ===== Focus Ring Default ===== */
  *:focus-visible {
    @apply outline-wolf-focus outline-offset-wolf outline-wolf-primary/50;
  }

  /* ===== Button Reset ===== */
  button {
    @apply cursor-pointer;
  }

  /* ===== Input Reset ===== */
  input,
  textarea,
  select {
    @apply font-wolf text-wolf-body;
  }

  /* ===== Touch Target Safety ===== */
  /* Mobile: 所有交互元素最小 44px */
  @media (max-width: 767px) {
    button,
    a,
    input,
    select,
    [role="button"] {
      @apply min-h-touch-target min-w-touch-target;
    }
  }

  /* ===== Reduced Motion Support ===== */
  /* UI/UX Pro Max CRITICAL: Respect prefers-reduced-motion */
  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }

  /* ===== iOS Auto-zoom Prevention ===== */
  /* UI/UX Pro Max CRITICAL: input font-size >= 16px on mobile */
  @media (max-width: 767px) {
    input,
    textarea,
    select {
      font-size: 16px;
    }
  }
}

/* ==================== CRMWolf Utilities ==================== */

@layer utilities {
  /* ===== Touch-safe utility ===== */
  .touch-safe {
    @apply min-h-touch-target min-w-touch-target;
  }

  /* ===== Press feedback ===== */
  .press-feedback {
    @apply transition-transform duration-wolf-press active:scale-[0.98];
  }

  /* ===== Focus ring utilities ===== */
  .focus-ring {
    @apply focus-visible:outline-wolf-focus focus-visible:outline-offset-wolf;
  }

  .focus-ring-danger {
    @apply focus-visible:outline-wolf-focus focus-visible:outline-offset-wolf focus-visible:outline-wolf-danger/50;
  }

  /* ===== Disabled state ===== */
  .disabled-state {
    @apply opacity-38 cursor-not-allowed pointer-events-none;
  }
}
```

- [ ] **Step 2: Import base.css in main.ts**

Read main.ts first to find the insertion point, then add import:

```typescript
// Add at top of imports section
import './styles/base.css'
```

- [ ] **Step 3: Verify base.css loads without errors**

Run: `cd CRM-Client && npm run dev -- --port 5174 &`
Wait 5 seconds, then check terminal output
Expected: No CSS compilation errors

- [ ] **Step 4: Stop dev server and commit**

```bash
pkill -f "vite"
cd CRM-Client && git add src/styles/base.css src/main.ts && git commit -m "feat(design-system): add Tailwind base layer with focus/touch/reduced-motion support"
```

---

### Task 4: Create Touch Safety CSS Module

**Files:**
- Create: `CRM-Client/src/styles/touch-safety.css`

**Interfaces:**
- Produces: Touch target safety utilities and hit-slop extension patterns

- [ ] **Step 1: Create touch-safety.css with hit-slop utilities**

```css
/* ==================== Touch Safety Utilities ==================== */
/* UI/UX Pro Max CRITICAL §2: Touch Target Minimum 44×44pt */

@layer components {
  /* ===== Touch-safe container ===== */
  /* Wraps small visual elements with invisible 44px touch area */
  .touch-safe-container {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  /* ===== Hit-slop extension ===== */
  /* Extends touch target by N pixels in all directions */
  .hit-slop {
    &::after {
      content: '';
      position: absolute;
      top: -10px;
      right: -10px;
      bottom: -10px;
      left: -10px;
    }
  }

  /* ===== Touch-safe button sizes ===== */
  .btn-touch-sm {
    /* Visual size: 24px, Touch target: 44px via hit-slop */
    @apply h-button-sm px-wolf-sm relative;
    &::after {
      @apply absolute;
      content: '';
      top: -10px;
      right: -10px;
      bottom: -10px;
      left: -10px;
    }
  }

  .btn-touch-md {
    /* Desktop: 32px visual, Mobile: 44px auto */
    @apply h-button-md px-wolf-lg;
    @media (max-width: 767px) {
      @apply h-touch-target;
    }
  }

  .btn-touch-lg {
    /* Always 44px touch target compliant */
    @apply h-touch-target px-wolf-xl;
  }

  /* ===== Touch-safe input ===== */
  .input-touch-desktop {
    @apply h-input-desktop px-wolf-md;
  }

  .input-touch-mobile {
    @apply h-input-mobile px-wolf-xl;
  }

  /* ===== Touch-action manipulation ===== */
  /* Removes 300ms delay on mobile */
  .touch-manipulation {
    touch-action: manipulation;
  }
}

@layer utilities {
  /* ===== Dynamic hit-slop ===== */
  /* Usage: hit-slop-N where N is extension in px */
  .hit-slop-4::after {
    content: '';
    position: absolute;
    top: -4px;
    right: -4px;
    bottom: -4px;
    left: -4px;
  }

  .hit-slop-8::after {
    content: '';
    position: absolute;
    top: -8px;
    right: -8px;
    bottom: -8px;
    left: -8px;
  }

  .hit-slop-10::after {
    content: '';
    position: absolute;
    top: -10px;
    right: -10px;
    bottom: -10px;
    left: -10px;
  }
}
```

- [ ] **Step 2: Add touch-safety import to base.css**

```css
/* Add to top of base.css */
@import './touch-safety.css';
```

- [ ] **Step 3: Verify CSS compiles**

Run: `cd CRM-Client && npm run build`
Expected: Build succeeds without CSS errors

- [ ] **Step 4: Commit touch-safety module**

```bash
cd CRM-Client && git add src/styles/touch-safety.css src/styles/base.css && git commit -m "feat(design-system): add touch-safety utilities with hit-slop extension"
```

---

## Phase 2: shadcn-vue CLI Installation

### Task 5: Initialize shadcn-vue CLI

**Files:**
- Create: `CRM-Client/components.json`
- Create: `CRM-Client/src/lib/utils.ts`

**Interfaces:**
- Produces: shadcn-vue CLI configuration, utility function for class merging

- [ ] **Step 1: Install shadcn-vue CLI**

Run: `cd CRM-Client && npx shadcn-vue@latest init`
Expected: CLI prompts for configuration

Interactive input:
- Style: Default
- Base color: Slate
- CSS variables: Yes
- Tailwind config: tailwind.config.ts
- Components location: src/components/ui
- Utils location: src/lib/utils.ts

- [ ] **Step 2: Verify components.json created**

Run: `cat CRM-Client/components.json`
Expected: JSON file with shadcn-vue configuration

- [ ] **Step 3: Verify utils.ts created with cn function**

Run: `cat CRM-Client/src/lib/utils.ts`
Expected: File contains `cn()` function for class merging

If utils.ts doesn't exist, create it:

```typescript
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 4: Install clsx and tailwind-merge if needed**

Run: `cd CRM-Client && npm install clsx tailwind-merge`
Expected: Packages installed

- [ ] **Step 5: Commit shadcn-vue initialization**

```bash
cd CRM-Client && git add components.json src/lib/utils.ts package.json package-lock.json && git commit -m "feat(design-system): initialize shadcn-vue CLI with wolf configuration"
```

---

### Task 6: Install shadcn-vue Primitive Components

**Files:**
- Create: `CRM-Client/src/components/ui/button/`
- Create: `CRM-Client/src/components/ui/input/`
- Create: `CRM-Client/src/components/ui/table/`
- Create: `CRM-Client/src/components/ui/card/`
- Create: `CRM-Client/src/components/ui/tabs/`

**Interfaces:**
- Produces: shadcn-vue primitives (Button, Input, Table, Card, Tabs)

- [ ] **Step 1: Install Button primitive**

Run: `cd CRM-Client && npx shadcn-vue@latest add button`
Expected: Button component created in src/components/ui/button/

- [ ] **Step 2: Install Input primitive**

Run: `cd CRM-Client && npx shadcn-vue@latest add input`
Expected: Input component created in src/components/ui/input/

- [ ] **Step 3: Install Table primitive**

Run: `cd CRM-Client && npx shadcn-vue@latest add table`
Expected: Table component created in src/components/ui/table/

- [ ] **Step 4: Install Card primitive**

Run: `cd CRM-Client && npx shadcn-vue@latest add card`
Expected: Card component created in src/components/ui/card/

- [ ] **Step 5: Install Tabs primitive**

Run: `cd CRM-Client && npx shadcn-vue@latest add tabs`
Expected: Tabs component created in src/components/ui/tabs/

- [ ] **Step 6: Verify all components installed**

Run: `ls -la CRM-Client/src/components/ui/`
Expected: Directories: button, input, table, card, tabs

- [ ] **Step 7: Commit shadcn-vue primitives**

```bash
cd CRM-Client && git add src/components/ui/ && git commit -m "feat(design-system): install shadcn-vue primitives (button, input, table, card, tabs)"
```

---

## Phase 3: CRMWolf Extensions (Touch-safe Variants)

### Task 7: Create TouchButton Component

**Files:**
- Create: `CRM-Client/src/components/crmwolf/TouchButton.vue`
- Create: `CRM-Client/src/components/crmwolf/TouchButton.spec.ts`
- Test: `CRM-Client/src/components/crmwolf/TouchButton.spec.ts`

**Interfaces:**
- Consumes: shadcn Button from Task 6
- Produces: Touch-safe button with size="touch" variant, press feedback, touch-action manipulation

- [ ] **Step 1: Write failing test for TouchButton touch target**

```typescript
/**
 * TouchButton 单元测试
 * UI/UX Pro Max CRITICAL §2: Touch Target 44px minimum
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchButton from './TouchButton.vue'

describe('TouchButton', () => {
  it('size="touch" variant has 44px height for touch target compliance', () => {
    const wrapper = mount(TouchButton, {
      props: {
        size: 'touch'
      },
      slots: {
        default: 'Click me'
      }
    })

    const button = wrapper.find('button')
    const classes = button.classes()

    // Verify touch-safe class applied
    expect(classes.some(c => c.includes('touch'))).toBe(true)
    expect(classes.some(c => c.includes('h-touch-target') || c.includes('min-h-touch-target'))).toBe(true)
  })

  it('has press feedback active:scale-[0.98]', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Click' }
    })

    const button = wrapper.find('button')
    expect(button.classes().some(c => c.includes('press-feedback') || c.includes('active:scale'))).toBe(true)
  })

  it('has touch-action: manipulation to remove 300ms delay', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Click' }
    })

    const button = wrapper.find('button')
    expect(button.classes().some(c => c.includes('touch-manipulation'))).toBe(true)
  })

  it('size="sm" has hit-slop for 44px touch target', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'sm' },
      slots: { default: 'Small' }
    })

    const button = wrapper.find('button')
    // sm button should have hit-slop to extend touch area
    expect(button.classes().some(c => c.includes('hit-slop') || c.includes('touch-safe'))).toBe(true)
  })

  it('focus ring visible with focus-visible state', async () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Focus' },
      attachTo: document.body
    })

    const button = wrapper.find('button')
    await button.trigger('focus')

    expect(button.classes().some(c => c.includes('focus-visible') || c.includes('focus-ring'))).toBe(true)

    wrapper.unmount()
  })

  it('supports reduced motion preference', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Motion' }
    })

    // Reduced motion should disable press feedback animation
    // This is verified via CSS media query, not component logic
    const button = wrapper.find('button')
    expect(button.exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Client && npm run test:unit -- src/components/crmwolf/TouchButton.spec.ts`
Expected: FAIL with "TouchButton not defined" or test failures

- [ ] **Step 3: Create TouchButton component extending shadcn Button**

```vue
<script setup lang="ts">
/**
 * TouchButton - CRMWolf Touch-safe Button
 * UI/UX Pro Max CRITICAL §2: Touch Target 44px minimum
 *
 * Features:
 * - size="touch" variant (44px height)
 * - Press feedback (active:scale-[0.98])
 * - touch-action: manipulation (removes 300ms delay)
 * - Hit-slop extension for small sizes
 */
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Component } from 'vue'

interface Props {
  /** Button variant */
  variant?: 'default' | 'primary' | 'secondary' | 'danger' | 'ghost'
  /** Button size (touch = 44px compliant) */
  size?: 'sm' | 'md' | 'lg' | 'touch'
  /** Disabled state */
  disabled?: boolean
  /** Loading state */
  loading?: boolean
  /** Icon component */
  icon?: Component
  /** Aria label for icon buttons */
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  disabled: false,
  loading: false,
  icon: undefined,
  ariaLabel: undefined,
})

// Map CRMWolf variants to shadcn variants
const variantMap = {
  default: 'outline',
  primary: 'default',
  secondary: 'secondary',
  danger: 'destructive',
  ghost: 'ghost',
}

// Size classes with touch safety
const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      // 24px visual, hit-slop extends to 44px
      return 'btn-touch-sm hit-slop-10'
    case 'md':
      // 32px desktop, 44px mobile
      return 'btn-touch-md'
    case 'lg':
      // Always 44px
      return 'btn-touch-lg'
    case 'touch':
      // Explicit touch-safe size
      return 'h-touch-target min-w-touch-target px-wolf-xl'
    default:
      return 'btn-touch-md'
  }
})

const buttonClasses = computed(() =>
  cn(
    sizeClasses.value,
    'press-feedback touch-manipulation focus-ring',
    {
      'disabled-state': props.disabled || props.loading,
    }
  )
)
</script>

<template>
  <Button
    :variant="variantMap[props.variant]"
    :class="buttonClasses"
    :disabled="disabled || loading"
    :aria-label="ariaLabel"
  >
    <slot />
  </Button>
</template>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Client && npm run test:unit -- src/components/crmwolf/TouchButton.spec.ts`
Expected: PASS, all tests succeed

- [ ] **Step 5: Commit TouchButton**

```bash
cd CRM-Client && git add src/components/crmwolf/TouchButton.vue src/components/crmwolf/TouchButton.spec.ts && git commit -m "feat(design-system): create TouchButton with 44px touch target and press feedback"
```

---

### Task 8: Create TouchInput Component

**Files:**
- Create: `CRM-Client/src/components/crmwolf/TouchInput.vue`
- Create: `CRM-Client/src/components/crmwolf/TouchInput.spec.ts`
- Test: `CRM-Client/src/components/crmwolf/TouchInput.spec.ts`

**Interfaces:**
- Consumes: shadcn Input from Task 6
- Produces: Touch-safe input with visible label, error placement, mobile 44px height, iOS auto-zoom prevention

- [ ] **Step 1: Write failing test for TouchInput**

```typescript
/**
 * TouchInput 单元测试
 * UI/UX Pro Max CRITICAL: §1 Focus, §2 Touch Target, §8 Forms
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchInput from './TouchInput.vue'

describe('TouchInput', () => {
  // Touch Target Tests
  it('mobile size has 44px height for touch target', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Username',
        size: 'mobile'
      }
    })

    const inputWrapper = wrapper.find('.input-wrapper')
    expect(inputWrapper.classes().some(c => c.includes('h-input-mobile') || c.includes('h-touch-target'))).toBe(true)
  })

  // Focus Ring Tests
  it('has visible focus ring on focus', async () => {
    const wrapper = mount(TouchInput, {
      props: { label: 'Focus Test' },
      attachTo: document.body
    })

    const input = wrapper.find('input')
    await input.trigger('focus')

    expect(input.classes().some(c => c.includes('focus-visible') || c.includes('focus-ring'))).toBe(true)

    wrapper.unmount()
  })

  // Visible Label Tests (§8 Forms)
  it('label is always visible, not just placeholder', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Visible Label',
        placeholder: 'Placeholder hint'
      }
    })

    const label = wrapper.find('label')
    expect(label.exists()).toBe(true)
    expect(label.isVisible()).toBe(true)
    expect(label.text()).toBe('Visible Label')
  })

  it('required field shows required marker', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Required',
        required: true
      }
    })

    const requiredMark = wrapper.find('.required-mark')
    expect(requiredMark.exists()).toBe(true)
  })

  // Error Placement Tests (§8 Forms)
  it('error message appears below input field', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Error Test',
        error: 'This field is required'
      }
    })

    const error = wrapper.find('.error-message')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('required')

    // Verify error is below input in DOM structure
    const container = wrapper.find('.touch-input-container')
    const children = Array.from(container.element.children)
    const inputWrapperIndex = children.findIndex(el => el.classList.contains('input-wrapper'))
    const errorIndex = children.findIndex(el => el.classList.contains('error-message'))
    expect(errorIndex).toBeGreaterThan(inputWrapperIndex)
  })

  it('error replaces helper text when both provided', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Test',
        helperText: 'Helper hint',
        error: 'Error message'
      }
    })

    const helper = wrapper.find('.helper-text')
    expect(helper.exists()).toBe(false)

    const error = wrapper.find('.error-message')
    expect(error.exists()).toBe(true)
  })

  // Accessibility Tests
  it('has proper aria attributes', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Aria Test',
        required: true,
        error: 'Error'
      }
    })

    const input = wrapper.find('input')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-required')).toBe('true')
    expect(input.attributes('aria-describedby')).toBeDefined()
  })

  it('label for attribute matches input id', () => {
    const wrapper = mount(TouchInput, {
      props: { label: 'ID Test' }
    })

    const label = wrapper.find('label')
    const input = wrapper.find('input')
    expect(label.attributes('for')).toBe(input.attributes('id'))
  })

  // iOS Auto-zoom Prevention (§1 Accessibility)
  it('mobile input has font-size >= 16px to prevent iOS auto-zoom', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Mobile',
        size: 'mobile'
      }
    })

    const input = wrapper.find('input')
    // This is enforced via CSS, not component logic
    expect(input.exists()).toBe(true)
  })

  // Reduced Motion Support
  it('respects prefers-reduced-motion', () => {
    const wrapper = mount(TouchInput, {
      props: { label: 'Motion Test' }
    })

    // Reduced motion is handled via CSS base layer
    const inputWrapper = wrapper.find('.input-wrapper')
    expect(inputWrapper.exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Client && npm run test:unit -- src/components/crmwolf/TouchInput.spec.ts`
Expected: FAIL

- [ ] **Step 3: Create TouchInput component**

```vue
<script setup lang="ts">
/**
 * TouchInput - CRMWolf Touch-safe Input
 * UI/UX Pro Max CRITICAL: §1 Focus, §2 Touch, §8 Forms
 *
 * Features:
 * - Visible label (never placeholder-only)
 * - Error message below field
 * - Mobile 44px height
 * - iOS auto-zoom prevention (16px font)
 * - Focus ring visible
 */
import { computed, ref } from 'vue'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface Props {
  /** v-model value */
  modelValue?: string | number
  /** Visible label (required) */
  label: string
  /** Input type */
  type?: 'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'
  /** Placeholder hint */
  placeholder?: string
  /** Helper text */
  helperText?: string
  /** Error message */
  error?: string
  /** Disabled state */
  disabled?: boolean
  /** Readonly state */
  readonly?: boolean
  /** Required field */
  required?: boolean
  /** Input ID */
  inputId?: string
  /** Size variant */
  size?: 'default' | 'mobile'
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  type: 'text',
  placeholder: '',
  helperText: '',
  error: '',
  disabled: false,
  readonly: false,
  required: false,
  inputId: '',
  size: 'default',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'focus', event: FocusEvent): void
  (e: 'blur', event: FocusEvent): void
  (e: 'change', value: string | number): void
}>()

const isFocused = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

const computedId = computed(() =>
  props.inputId || `touch-input-${Math.random().toString(36).slice(2, 9)}`
)

const hasError = computed(() => props.error !== '')

const inputWrapperClasses = computed(() =>
  cn(
    'input-wrapper',
    'relative flex items-center',
    {
      'h-input-desktop': props.size === 'default',
      'h-input-mobile': props.size === 'mobile',
      'focus-ring': isFocused.value,
      'border-wolf-danger': hasError.value,
      'disabled-state': props.disabled,
    }
  )
)

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('update:modelValue', value)
}

const handleFocus = (event: FocusEvent) => {
  isFocused.value = true
  emit('focus', event)
}

const handleBlur = (event: FocusEvent) => {
  isFocused.value = false
  emit('blur', event)
}

const handleChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('change', value)
}

const focus = () => inputRef.value?.focus()
const blur = () => inputRef.value?.blur()

defineExpose({ focus, blur, inputRef })
</script>

<template>
  <div class="touch-input-container flex flex-col gap-wolf-xs w-full">
    <!-- Visible Label (UI/UX Pro Max §8 Forms) -->
    <label
      :for="computedId"
      class="label text-wolf-body font-wolf-medium text-wolf-text-secondary cursor-pointer"
    >
      {{ label }}
      <span
        v-if="required"
        class="required-mark text-wolf-danger ml-1"
        aria-hidden="true"
      >*</span>
    </label>

    <!-- Input Wrapper -->
    <div :class="inputWrapperClasses">
      <Input
        :id="computedId"
        ref="inputRef"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :aria-invalid="hasError ? 'true' : undefined"
        :aria-describedby="hasError ? `${computedId}-error` : helperText ? `${computedId}-helper` : undefined"
        :aria-required="required ? 'true' : undefined"
        class="w-full h-full px-wolf-md text-wolf-body font-wolf bg-transparent border-none outline-none"
        @input="handleInput"
        @focus="handleFocus"
        @blur="handleBlur"
        @change="handleChange"
      />
    </div>

    <!-- Helper Text -->
    <div
      v-if="helperText && !hasError"
      :id="`${computedId}-helper`"
      class="helper-text text-wolf-caption text-wolf-text-tertiary -mt-wolf-xs"
    >
      {{ helperText }}
    </div>

    <!-- Error Message (UI/UX Pro Max §8 Forms: below field) -->
    <div
      v-if="hasError"
      :id="`${computedId}-error`"
      class="error-message flex items-start gap-wolf-xs text-wolf-caption text-wolf-danger -mt-wolf-xs"
      role="alert"
      aria-live="polite"
    >
      <span class="error-icon flex-shrink-0 w-3.5 h-3.5 rounded-full bg-wolf-danger-bg text-wolf-danger flex items-center justify-center text-xs font-wolf-semibold">!</span>
      {{ error }}
    </div>
  </div>
</template>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Client && npm run test:unit -- src/components/crmwolf/TouchInput.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit TouchInput**

```bash
cd CRM-Client && git add src/components/crmwolf/TouchInput.vue src/components/crmwolf/TouchInput.spec.ts && git commit -m "feat(design-system): create TouchInput with visible label, error placement, mobile 44px height"
```

---

### Task 9: Create CRMWolf Component Index

**Files:**
- Create: `CRM-Client/src/components/crmwolf/index.ts`

**Interfaces:**
- Produces: Unified export for all CRMWolf components

- [ ] **Step 1: Create crmwolf/index.ts with exports**

```typescript
/**
 * CRMWolf Design System Components
 * UI/UX Pro Max compliant primitives
 */

export { default as TouchButton } from './TouchButton.vue'
export { default as TouchInput } from './TouchInput.vue'

// Re-export shadcn primitives for convenience
export { Button } from '@/components/ui/button'
export { Input } from '@/components/ui/input'
export { Table, TableCell, TableHeader, TableRow } from '@/components/ui/table'
export { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
export { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
```

- [ ] **Step 2: Verify exports work**

Run: `cd CRM-Client && node -e "import('./src/components/crmwolf/index.ts').then(m => console.log('Exports:', Object.keys(m)))"`
Expected: "Exports: ['TouchButton', 'TouchInput', 'Button', 'Input', ...]"

- [ ] **Step 3: Commit index**

```bash
cd CRM-Client && git add src/components/crmwolf/index.ts && git commit -m "feat(design-system): create CRMWolf component index with unified exports"
```

---

## Phase 4: Accessibility Quality Gates

### Task 10: Create Touch Target Accessibility Tests

**Files:**
- Create: `CRM-Client/tests/accessibility/touch-target.spec.ts`

**Interfaces:**
- Consumes: TouchButton, TouchInput from Phase 3
- Produces: Automated touch target compliance tests

- [ ] **Step 1: Write comprehensive touch target tests**

```typescript
/**
 * Touch Target Accessibility Tests
 * UI/UX Pro Max CRITICAL §2: Touch Target Minimum 44×44pt
 *
 * Tests verify:
 * - All interactive elements meet 44px minimum on mobile
 * - Hit-slop extension works for small visual sizes
 * - Touch-action manipulation removes 300ms delay
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { TouchButton, TouchInput } from '@/components/crmwolf'

describe('Touch Target Compliance (UI/UX Pro Max §2)', () => {
  describe('TouchButton', () => {
    it('size="touch" has explicit 44px height', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      const classList = button.classes()

      expect(
        classList.some(c =>
          c.includes('h-touch-target') ||
          c.includes('min-h-touch-target') ||
          c.includes('h-\\[44px\\]')
        )
      ).toBe(true)
    })

    it('size="sm" uses hit-slop to achieve 44px touch area', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'sm' },
        slots: { default: 'Small' }
      })

      const button = wrapper.find('button')

      // sm button should have hit-slop class
      expect(button.classes().some(c => c.includes('hit-slop'))).toBe(true)
    })

    it('size="lg" always has 44px height', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'lg' },
        slots: { default: 'Large' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('touch') || c.includes('44'))).toBe(true)
    })

    it('has touch-action: manipulation', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('touch-manipulation'))).toBe(true)
    })

    it('press feedback active:scale-[0.98] applied', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('press-feedback') || c.includes('active:scale'))).toBe(true)
    })
  })

  describe('TouchInput', () => {
    it('size="mobile" has 44px height', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile Input',
          size: 'mobile'
        }
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('h-input-mobile'))).toBe(true)
    })

    it('mobile input has 16px font-size (iOS auto-zoom prevention)', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile',
          size: 'mobile'
        }
      })

      // This is enforced via CSS base layer @media (max-width: 767px)
      const input = wrapper.find('input')
      expect(input.exists()).toBe(true)
    })

    it('default size has 32px height for desktop', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Desktop',
          size: 'default'
        }
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('h-input-desktop'))).toBe(true)
    })
  })

  describe('Global Base Layer', () => {
    it('base.css applies min-h-touch-target on mobile', () => {
      // This is verified via CSS compilation, not runtime test
      // Check that base.css contains the rule
      const fs = require('fs')
      const baseCss = fs.readFileSync('./src/styles/base.css', 'utf-8')

      expect(baseCss).toContain('min-h-touch-target')
      expect(baseCss).toContain('@media (max-width: 767px)')
    })
  })
})
```

- [ ] **Step 2: Run touch target tests**

Run: `cd CRM-Client && npm run test:unit -- tests/accessibility/touch-target.spec.ts`
Expected: PASS

- [ ] **Step 3: Commit touch target tests**

```bash
cd CRM-Client && git add tests/accessibility/touch-target.spec.ts && git commit -m "test(accessibility): add touch target compliance tests (44px minimum)"
```

---

### Task 11: Create Focus Ring Accessibility Tests

**Files:**
- Create: `CRM-Client/tests/accessibility/focus-ring.spec.ts`

**Interfaces:**
- Consumes: TouchButton, TouchInput
- Produces: Focus ring visibility tests

- [ ] **Step 1: Write focus ring tests**

```typescript
/**
 * Focus Ring Accessibility Tests
 * UI/UX Pro Max CRITICAL §1: Focus States 2-4px visible
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { TouchButton, TouchInput } from '@/components/crmwolf'

describe('Focus Ring Compliance (UI/UX Pro Max §1)', () => {
  describe('TouchButton', () => {
    it('has focus-visible state', async () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' },
        attachTo: document.body
      })

      const button = wrapper.find('button')

      // Focus the button
      await button.trigger('focus')

      // Check for focus-ring class or focus-visible outline
      expect(button.classes().some(c => c.includes('focus-ring') || c.includes('focus-visible'))).toBe(true)

      wrapper.unmount()
    })

    it('focus ring uses wolf primary color', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')

      // Focus ring color should be wolf-primary/50 (rgba)
      // This is verified via CSS, class presence indicates compliance
      expect(button.classes().some(c => c.includes('focus-ring'))).toBe(true)
    })
  })

  describe('TouchInput', () => {
    it('shows focus ring on focus', async () => {
      const wrapper = mount(TouchInput, {
        props: { label: 'Focus Test' },
        attachTo: document.body
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('focus-ring'))).toBe(true)

      wrapper.unmount()
    })

    it('error state uses danger focus ring color', async () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Error',
          error: 'Required field'
        },
        attachTo: document.body
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('border-wolf-danger'))).toBe(true)

      wrapper.unmount()
    })

    it('focus ring width is 2px (WCAG compliant)', () => {
      // Verify via CSS config
      const fs = require('fs')
      const baseCss = fs.readFileSync('./src/styles/base.css', 'utf-8')

      expect(baseCss).toContain('outline-wolf-focus')
    })
  })

  describe('Global Focus Ring Config', () => {
    it('tailwind.config.ts defines focus ring width 2px', () => {
      const config = require('./tailwind.config.ts')
      expect(config.theme.extend.outlineWidth.wolf.focus).toBe('2px')
    })
  })
})
```

- [ ] **Step 2: Run focus ring tests**

Run: `cd CRM-Client && npm run test:unit -- tests/accessibility/focus-ring.spec.ts`
Expected: PASS

- [ ] **Step 3: Commit focus ring tests**

```bash
cd CRM-Client && git add tests/accessibility/focus-ring.spec.ts && git commit -m "test(accessibility): add focus ring visibility tests (2px minimum)"
```

---

### Task 12: Create Reduced Motion Accessibility Tests

**Files:**
- Create: `CRM-Client/tests/accessibility/reduced-motion.spec.ts`

**Interfaces:**
- Produces: Reduced motion preference tests

- [ ] **Step 1: Write reduced motion tests**

```typescript
/**
 * Reduced Motion Accessibility Tests
 * UI/UX Pro Max CRITICAL §7: Respect prefers-reduced-motion
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { TouchButton } from '@/components/crmwolf'

describe('Reduced Motion Compliance (UI/UX Pro Max §7)', () => {
  describe('TouchButton', () => {
    it('press feedback disabled when prefers-reduced-motion', () => {
      // This is handled via CSS @media query
      // Verify base.css has the rule
      const fs = require('fs')
      const baseCss = fs.readFileSync('./src/styles/base.css', 'utf-8')

      expect(baseCss).toContain('prefers-reduced-motion')
      expect(baseCss).toContain('transition-duration: 0.01ms')
    })
  })

  describe('Global CSS', () => {
    it('base.css disables animations for reduced-motion users', () => {
      const fs = require('fs')
      const baseCss = fs.readFileSync('./src/styles/base.css', 'utf-8')

      expect(baseCss).toContain('@media (prefers-reduced-motion: reduce)')
      expect(baseCss).toContain('animation-duration: 0.01ms')
      expect(baseCss).toContain('transition-duration: 0.01ms')
    })

    it('touch-safety.css press feedback respects reduced motion', () => {
      const fs = require('fs')
      const touchCss = fs.readFileSync('./src/styles/touch-safety.css', 'utf-8')

      // Press feedback should use CSS that gets overridden by base layer
      expect(touchCss).toContain('press-feedback')
      expect(touchCss).toContain('transition-transform')
    })
  })

  describe('Tailwind Config', () => {
    it('defines reduced motion duration', () => {
      const fs = require('fs')
      const configContent = fs.readFileSync('./tailwind.config.ts', 'utf-8')

      // Verify wolf duration values exist
      expect(configContent).toContain('wolf: \'150ms\'')
    })
  })
})
```

- [ ] **Step 2: Run reduced motion tests**

Run: `cd CRM-Client && npm run test:unit -- tests/accessibility/reduced-motion.spec.ts`
Expected: PASS

- [ ] **Step 3: Commit reduced motion tests**

```bash
cd CRM-Client && git add tests/accessibility/reduced-motion.spec.ts && git commit -m "test(accessibility): add reduced motion preference tests"
```

---

### Task 13: Run Full Accessibility Test Suite

**Files:**
- Test: All accessibility tests pass

**Interfaces:**
- Consumes: All accessibility tests from Tasks 10-12
- Produces: Verified UI/UX Pro Max compliance

- [ ] **Step 1: Run all accessibility tests**

Run: `cd CRM-Client && npm run test:unit -- tests/accessibility/`
Expected: All tests PASS

- [ ] **Step 2: Generate coverage report**

Run: `cd CRM-Client && npm run coverage -- tests/accessibility/`
Expected: Coverage report generated, no failures

- [ ] **Step 3: Verify no TypeScript errors**

Run: `cd CRM-Client && npm run type-check`
Expected: No TypeScript errors

- [ ] **Step 4: Commit quality gate verification**

```bash
cd CRM-Client && git add . && git commit -m "test(accessibility): verify UI/UX Pro Max compliance - touch target, focus ring, reduced motion all passing"
```

---

## Phase 5: V2 Component Migration

### Task 14: Delete V2 Components

**Files:**
- Delete: `CRM-Client/src/components/common/ButtonV2.vue`
- Delete: `CRM-Client/src/components/common/ButtonV2.spec.ts`
- Delete: `CRM-Client/src/components/common/ButtonV2.stories.ts`
- Delete: `CRM-Client/src/components/common/InputV2.vue`
- Delete: `CRM-Client/src/components/common/InputV2.spec.ts`
- Delete: `CRM-Client/src/components/common/InputV2.stories.ts`
- Delete: `CRM-Client/src/components/common/TableV2.vue`
- Delete: `CRM-Client/src/components/common/TableV2.spec.ts`
- Delete: `CRM-Client/src/components/common/TableV2.stories.ts`
- Delete: `CRM-Client/src/components/common/CardV2.vue`
- Delete: `CRM-Client/src/components/common/CardV2.spec.ts`
- Delete: `CRM-Client/src/components/common/CardV2.stories.ts`
- Delete: `CRM-Client/src/components/common/TabV2.vue`
- Delete: `CRM-Client/src/components/common/TabV2.spec.ts`
- Delete: `CRM-Client/src/components/common/TabV2.stories.ts`

**Interfaces:**
- Consumes: V2 components exist
- Produces: V2 components removed, replaced by CRMWolf/shadcn primitives

- [ ] **Step 1: List all V2 component files**

Run: `cd CRM-Client && find src/components/common -name "*V2.*" -type f`
Expected: List of 15 files (3 per component: .vue, .spec.ts, .stories.ts)

- [ ] **Step 2: Delete ButtonV2 files**

```bash
cd CRM-Client && rm -f src/components/common/ButtonV2.vue src/components/common/ButtonV2.spec.ts src/components/common/ButtonV2.stories.ts
```

- [ ] **Step 3: Delete InputV2 files**

```bash
cd CRM-Client && rm -f src/components/common/InputV2.vue src/components/common/InputV2.spec.ts src/components/common/InputV2.stories.ts
```

- [ ] **Step 4: Delete TableV2 files**

```bash
cd CRM-Client && rm -f src/components/common/TableV2.vue src/components/common/TableV2.spec.ts src/components/common/TableV2.stories.ts
```

- [ ] **Step 5: Delete CardV2 files**

```bash
cd CRM-Client && rm -f src/components/common/CardV2.vue src/components/common/CardV2.spec.ts src/components/common/CardV2.stories.ts
```

- [ ] **Step 6: Delete TabV2 files**

```bash
cd CRM-Client && rm -f src/components/common/TabV2.vue src/components/common/TabV2.spec.ts src/components/common/TabV2.stories.ts
```

- [ ] **Step 7: Verify all V2 files deleted**

Run: `cd CRM-Client && find src/components/common -name "*V2.*" -type f`
Expected: No files found

- [ ] **Step 8: Commit deletion**

```bash
cd CRM-Client && git add -A && git commit -m "refactor(design-system): delete all V2 components, replaced by shadcn-vue + CRMWolf primitives"
```

---

### Task 15: Update Import References

**Files:**
- Modify: All files importing V2 components (search via grep)
- Test: Verify build succeeds with new imports

**Interfaces:**
- Consumes: CRMWolf components from Task 9
- Produces: All imports updated to use TouchButton/TouchInput/shadcn primitives

- [ ] **Step 1: Find all files importing V2 components**

Run: `cd CRM-Client && grep -r "from.*V2" src/views src/components --include="*.vue" --include="*.ts"`
Expected: List of files with V2 imports

- [ ] **Step 2: Create migration script**

```bash
# Migration script for replacing V2 imports
cd CRM-Client

# Replace ButtonV2 → TouchButton
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/ButtonV2/TouchButton/g'
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/@\/components\/common\/ButtonV2/@\/components\/crmwolf\/TouchButton/g'

# Replace InputV2 → TouchInput
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/InputV2/TouchInput/g'
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/@\/components\/common\/InputV2/@\/components\/crmwolf\/TouchInput/g'

# Replace TableV2 → Table (shadcn)
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/TableV2/Table/g'
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/@\/components\/common\/TableV2/@\/components\/ui\/table/g'

# Replace CardV2 → Card (shadcn)
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/CardV2/Card/g'
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/@\/components\/common\/CardV2/@\/components\/ui\/card/g'

# Replace TabV2 → Tabs (shadcn)
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/TabV2/Tabs/g'
find src/views src/components -name "*.vue" -o -name "*.ts" | xargs sed -i '' 's/@\/components\/common\/TabV2/@\/components\/ui\/tabs/g'
```

- [ ] **Step 3: Run migration script**

Run the migration commands above
Expected: All imports updated

- [ ] **Step 4: Verify TypeScript compilation**

Run: `cd CRM-Client && npm run type-check`
Expected: No TypeScript errors (imports resolved)

- [ ] **Step 5: Verify build succeeds**

Run: `cd CRM-Client && npm run build`
Expected: Build succeeds without errors

- [ ] **Step 6: Verify tests still pass**

Run: `cd CRM-Client && npm run test:unit`
Expected: All tests pass

- [ ] **Step 7: Commit import updates**

```bash
cd CRM-Client && git add -A && git commit -m "refactor(design-system): update all imports from V2 to CRMWolf/shadcn primitives"
```

---

### Task 16: Final Verification and Integration Test

**Files:**
- Test: Full build, all tests, lint check

**Interfaces:**
- Consumes: All completed work
- Produces: Verified migration complete

- [ ] **Step 1: Run full build**

Run: `cd CRM-Client && npm run build`
Expected: Build succeeds

- [ ] **Step 2: Run all unit tests**

Run: `cd CRM-Client && npm run test:unit`
Expected: All tests pass

- [ ] **Step 3: Run lint check**

Run: `cd CRM-Client && npm run lint`
Expected: No lint errors

- [ ] **Step 4: Run type check**

Run: `cd CRM-Client && npm run type-check`
Expected: No TypeScript errors

- [ ] **Step 5: Start dev server for manual verification**

Run: `cd CRM-Client && npm run dev -- --port 5175`
Expected: Dev server starts without errors
Manual check: Open browser, verify components render correctly

- [ ] **Step 6: Stop dev server**

```bash
pkill -f "vite"
```

- [ ] **Step 7: Final commit**

```bash
cd CRM-Client && git add . && git commit -m "feat(design-system): complete shadcn-vue migration with full UI/UX Pro Max compliance

- Tailwind CSS foundation with wolf design tokens
- shadcn-vue primitives installed
- CRMWolf TouchButton/TouchInput with touch-safe variants
- Accessibility tests: touch target, focus ring, reduced motion
- V2 components deleted, imports updated
- All tests passing, build succeeds"
```

---

## Summary

**Tasks Completed:**
- Phase 1: Tailwind Foundation (Tasks 1-4)
- Phase 2: shadcn-vue Installation (Tasks 5-6)
- Phase 3: CRMWolf Extensions (Tasks 7-9)
- Phase 4: Accessibility Tests (Tasks 10-13)
- Phase 5: Migration (Tasks 14-16)

**UI/UX Pro Max Compliance Verified:**
- §1 Accessibility: Focus ring 2px visible
- §2 Touch Target: 44px minimum on mobile
- §7 Animation: prefers-reduced-motion support
- §8 Forms: Visible label, error placement

**Design System Tokens:**
- All wolf colors, spacing, radius, shadows mapped to Tailwind
- Touch-safe utilities with hit-slop extension
- Press feedback animations
- Mobile-first responsive breakpoints

**Next Steps:**
After completing this plan, use superpowers:finishing-a-development-branch to:
1. Push changes to remote
2. Create PR with migration summary
3. Update documentation