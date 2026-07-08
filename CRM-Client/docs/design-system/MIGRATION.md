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