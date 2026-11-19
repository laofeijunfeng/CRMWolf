# 组件生命周期

- **用途：**规定组件分层、状态流转、契约要求与组件门禁。
- **适用范围：**`CRM-Client/src/components` 与 `views` 中的组件及其导入关系。
- **权威性：**本文件拥有组件分层与生命周期规则；组件状态登记见[组件选型](../components/registry.md)。
- **相关规范：**[写作规范](authoring.md) · [质量检查](quality-checks.md) · [根入口](../README.md)

## 分层

自下而上：`components/ui`（原件）→ `components/crmwolf`（设计系统组件）→ 业务组件 → `views`。只允许上层引用下层：

- `ui/**` 不引用 crmwolf、业务组件或 views。
- `crmwolf/**` 不引用 `ui` 以外的 `components/*`，不引用 views。
- `components/**` 不引用 `views/**`。
- 页面经 crmwolf 组件或 `ui/detail-sheet` 使用受限原件，见[受限原件](../components/registry.md#受限原件)。

## 状态流转

`candidate` → `stable` → `deprecated` → `remove` → `removed`；`restricted` 用于只允许在 `ui/**`、`crmwolf/**` 内使用的原件。状态定义见[组件选型](../components/registry.md#状态)。

- **新增：**先在 `registry.md` 登记层、状态、用途；无契约时标 `candidate`、契约列写「待补」。
- **转 stable：**`components/` 下的契约文档满足下文契约要求、从 registry 链接并经评审后，改为 `stable`。
- **废弃：**标 `deprecated` 并填替代组件；不再新增引用。
- **删除：**确认无引用、无动态导入与全局注册后删除，状态改为 `removed`。

## 契约要求

- **几何：**高度、内边距、圆角只用 `--control-h-*`、`--control-px-*`、`--radius-*`，取值见[控件与版式](../foundations/token-values.md#控件与版式)与[圆角与阴影](../foundations/token-values.md#圆角与阴影)。
- **尺寸：**`size` 只取 xs / sm / md / lg，对应 `--control-h-*`、`--control-px-*`、`--icon-*` 同档；默认 md。
- **同排同档：**同一行并列的控件使用同一档位。
- **loading 不改宽：**处理中状态不改变控件宽度。
- 契约文档遵循[写作规范](authoring.md)，不复述数值。

## 组件门禁

由 `CRM-Client/scripts/check-design-system-governance.mjs` 执行。以下规则只检查增量；阶段 3 前 `--all` 跳过。

| 规则 | 编号 | 禁止 |
| --- | --- | --- |
| `layer-direction` | GATE-01 | 违反上文分层方向的导入。 |
| `barrel-reexport` | GATE-02 | `crmwolf/index.ts` 转导出 `@/components/ui/*`。 |
| `restricted-primitive` | GATE-03 | `ui` 与 `crmwolf` 之外导入 `ui/alert-dialog`、`ui/sheet`、`ui/table`、`ui/form`。 |
| `native-dialog` | GATE-04 | 调用原生 `confirm`、`alert`、`prompt`；跳过测试文件。 |
| `page-status-style` | GATE-05 | `.vue` 中的 `.status-*` 状态类与手写 `get*Status(Class/Color/Tone/Variant)` 映射；状态统一用 StatusBadge。 |

「同排同档」「loading 不改宽」暂无脚本，由代码评审检查。

## 存量与例外

- **存量登记：**现有违规登记在 [`inventory.json`](inventory.json)（结构见 [`inventory.schema.json`](inventory.schema.json)）。登记不等于豁免，存量须按阶段清零。
- **例外豁免：**确需保留的违规写入 [`exceptions.json`](exceptions.json)（结构见 [`exceptions.schema.json`](exceptions.schema.json)），必须填写 `reviewDate`，到期复审。
- 运行命令见[质量检查](quality-checks.md#治理数据与命令)。
