# Element Plus 到 shadcn-vue 组件映射

> 迁移现有 Element Plus 实现时，参考本映射表。

---

## 一、组件映射

| Element Plus | shadcn-vue / V2 | 优先级 |
|--------------|-----------------|--------|
| `el-button` | `Button` | P0 |
| `el-input` | `Input` | P0 |
| `el-table` / `el-table-column` | `Table` / `TableCell` / `TableRow` | P0 |
| `el-dialog` | `Dialog` | P0 |
| `el-form` | `Form` + VeeValidate | P0 |
| `el-select` | `Select` / `Combobox` | P0 |
| `ElMessage` | `toast()` (vue-sonner) | P1 |
| `ElMessageBox` | `AlertDialog` | P1 |
| `el-tooltip` | `Tooltip` | P2 |
| `el-pagination` | `Pagination` | P2 |
| `el-dropdown` | `DropdownMenu` | P2 |
| `el-tabs` | `Tabs` | P2 |

---

## 二、图标映射

| Element Plus Icon | Lucide Icon |
|-------------------|-------------|
| `el-icon-edit` | `Pencil` |
| `el-icon-delete` | `Trash2` |
| `el-icon-plus` | `Plus` |
| `el-icon-search` | `Search` |
| `el-icon-loading` | `Loader2` (animate-spin) |

---

## 三、代码示例

### 3.1 表格迁移

**旧代码**：
```vue
<el-table :data="list">
  <el-table-column prop="name" label="名称" />
  <el-table-column prop="status" label="状态" />
</el-table>
```

**新代码**：
```vue
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>名称</TableHead>
      <TableHead>状态</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow v-for="row in list" :key="row.id">
      <TableCell>{{ row.name }}</TableCell>
      <TableCell><StatusBadge :status="row.status" /></TableCell>
    </TableRow>
  </TableBody>
</Table>
```

### 3.2 对话框迁移

**旧代码**：
```vue
<el-dialog v-model="show" title="标题">
  <p>内容</p>
</el-dialog>
```

**新代码**：
```vue
<Dialog v-model:open="show">
  <DialogContent>
    <DialogHeader>
      <DialogTitle>标题</DialogTitle>
    </DialogHeader>
    <p>内容</p>
  </DialogContent>
</Dialog>
```

---

**最后更新**：2026-07-14