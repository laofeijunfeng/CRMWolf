# 质量检查

- **用途：**说明本地文档质量门禁、代码治理门禁及修复流程。
- **适用范围：**设计系统目录中的全部 Markdown 文档；`CRM-Client` 的设计系统治理检查。
- **权威性：**本文件拥有检查流程、治理命令与度量基线说明；组件门禁规则见[组件生命周期](component-lifecycle.md)。
- **相关规范：**[写作规范](authoring.md) · [组件生命周期](component-lifecycle.md) · [根入口](../README.md)

## 运行检查

```bash
node CRM-Docs/scripts/check-design-system-docs.js
```

## 四类失败

1. **行数超限：**单个 Markdown 超过 100 行。
2. **链接无效：**相对文件目标不存在，或链接锚点没有对应标题。
3. **不可达：**文档无法从根入口沿 Markdown 链接访问。
4. **散落数值：**除 `foundations/token-values.md` 外出现 hex 色值或 px 数值（`forbiddenPatterns`）；改为引用 Token 名。

## 修复步骤

1. 阅读检查输出中的文件和行号。
2. 将过长内容拆分到拥有该主题的新文件，并从索引链接。
3. 修正相对路径或标题锚点。
4. 从根入口补齐到领域索引和主题文件的链接。
5. 把散落数值改为 Token 名后，重新运行命令直至通过。

## 治理数据与命令

在 `CRM-Client` 下运行：

| 命令 | 范围 |
| --- | --- |
| `npm run lint:design-system` | 暂存区新增行。 |
| `npm run lint:design-system -- --worktree` | 工作区新增行。 |
| `npm run lint:design-system:all` | 全量扫描，CI 阻断。 |

三种命令运行同一组逐行规则：`raw-color`、`dark-mode`、`palette-color` 与组件门禁 GATE-01～06、10、11；仓库级规则 GATE-07～09 每次运行都检查全仓。

- [inventory.json](inventory.json)（[schema](inventory.schema.json)）只登记存量违规，不豁免。
- [exceptions.json](exceptions.json)（[schema](exceptions.schema.json)）是唯一豁免来源，每条必须带 `reviewDate`。
- 各类别对应的组件门禁见[组件生命周期](component-lifecycle.md#组件门禁)。

## 度量基线

| 指标 | 基线 | 阶段 1 | 阶段 3 |
| --- | --- | --- | --- |
| live 中原生 `confirm()` | 1 | 0 | 0 |
| 页面 `.status-*` 文件 / 手写映射函数 | 5 / 8 | 0 / 0 | 0 / 0 |
| 「放弃更改」文案变体 | 6 | 1 | 1 |
| crmwolf 以外的 `ui/alert-dialog` 消费方 | 23 | 6 | 0 |
| 桶文件转出原件组数 | 约 30 | 约 30 | 0 |
| 反向依赖 | 3 | 3 | 0 |
| 孤儿代码行数 | 约 5,443 | 约 5,443 | 0 |
| 手拼表单的 views | 20 | 20 | 0 或已登记 |
| 详情浮层轨数 | 4 | — | 1（detail-sheet） |
| 弹窗宽度不同取值 | 约 20 | 5（sm·md·lg·xl·full） | ≤ 5 |
| views 私有 CSS 行数 | 3,118 | — | 下降 ≥ 50% |
| 任意 px 字号 | 26 | — | 0 或已登记 |
| 有契约文档的 crmwolf 组件 | 0 / 51 | 6 | 全部 stable 件 |
| design-system 外的平行规范 | 2 | 0 | 0 |
| 过期迁移文档 | 4 | 0 | 0 |
| `lint:design-system:all` | 未启用 | 增量通过 | 返回 0 |

每次阶段验收另记三项：任意值类名数量、裸 px 字号数量、正文使用 `--font-size-control-sm` 的数量。
