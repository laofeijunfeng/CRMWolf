# CRM-Docs Scripts

当前只保留和现有文档结构直接相关的脚本：

| 脚本 | 用途 |
| --- | --- |
| `check-doc-location.sh` | 检查 `CRM-Docs` 根目录是否出现散落 Markdown 文档。 |
| `check-design-system-docs.js` | 校验 `CRM-Docs/design-system` 下的 V2 设计规范文档结构。 |
| `tests/check-design-system-docs.test.js` | `check-design-system-docs.js` 的基础测试。 |

## 使用方式

```bash
bash CRM-Docs/scripts/check-doc-location.sh
node CRM-Docs/scripts/check-design-system-docs.js
node CRM-Docs/scripts/tests/check-design-system-docs.test.js
```

已废弃的需求、计划、归档类文档生命周期脚本不再保留。后续文档入口保持收敛：

- `CRM-Docs/design-system/`
- `CRM-Docs/deployment/`
