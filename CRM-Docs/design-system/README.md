# CRMWolf 设计系统

这是目标状态规范库的唯一根入口。按任务进入领域索引，再进入主题规范。

## 按任务查阅

- [新建或调整页面](patterns/README.md)：组合页面模式与页面例外。
- [调整组件](components/README.md)：查找可复用组件契约。
- [令牌与响应式](foundations/README.md)：查找基础令牌、无障碍与响应式规范。
- [Element Plus 迁移](migration/README.md)：查找遗留实现到目标体系的迁移资料。
- [维护规范](governance/README.md)：查找文档治理与检查方法。

## 规则优先级

页面特有规则 > 交互模式 > 组件规则 > 基础规范。同级主题文件不得定义冲突规则；链接到其唯一事实来源。

## 本地检查

```bash
node CRM-Docs/scripts/check-design-system-docs.js
```

## 领域索引

- [基础规范](foundations/README.md)
- [组件契约](components/README.md)
- [页面模式](patterns/README.md)
- [迁移资料](migration/README.md)
- [文档治理](governance/README.md)
