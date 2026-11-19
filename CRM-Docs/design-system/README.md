# CRMWolf 设计系统

这是目标状态规范库的唯一根入口。按任务进入领域索引，再进入主题规范。

## 按任务查阅

- [新建或调整页面](patterns/README.md)：组合页面模式与页面例外。
- [调整组件](components/README.md)：查找可复用组件契约。
- [组件选型](components/registry.md)：查组件状态、替代关系与受限原件。
- [令牌与响应式](foundations/README.md)：查找基础令牌、无障碍与响应式规范。
- [维护规范](governance/README.md)：查找文档治理与检查方法。
- [组件生命周期](governance/component-lifecycle.md)：查组件分层、状态流转与组件门禁。

## 规则优先级

页面特有规则 > 交互模式 > 组件规则 > 基础规范。同级主题文件不得定义冲突规则；链接到其唯一事实来源。设计数值不适用该优先级：[令牌数值](foundations/token-values.md)是数值的唯一事实来源，任何层级都不得覆盖或另写数值。

## 全局令牌约定

系统只有亮色主题。设计数值只在 `CRM-Client/src/styles/base.css` 的 `:root` 定义一次，文档镜像为[令牌数值](foundations/token-values.md)；Tailwind 只映射 `var(--x)`。主操作使用中性深色 `--primary`，品牌蓝 `--brand` 用于链接、选中与焦点，中性色为 slate；不使用 Tailwind 色阶类。使用规则见[颜色令牌](foundations/color-tokens.md)。

## 本地检查

```bash
node CRM-Docs/scripts/check-design-system-docs.js
```

## 领域索引

- [基础规范](foundations/README.md)
- [组件契约](components/README.md)
- [页面模式](patterns/README.md)
- [文档治理](governance/README.md)
