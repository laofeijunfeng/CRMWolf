# 详情抽屉

- **用途：**规定页面级详情、编辑抽屉的唯一承载组件与组合方式。
- **适用范围：**components 领域；`CRM-Client/src/components/ui/detail-sheet` 及所有页面级右侧抽屉。
- **权威性：**本主题是 DetailSheet 的实现契约；任务边界与焦点规则由[模态框与抽屉](modal-sheet.md)拥有，外壳分档由[浮层表面](overlay.md)拥有。
- **相关规范：**[组件索引](README.md) · [组件选型](registry.md) · [模态框与抽屉](modal-sheet.md) · [浮层表面](overlay.md) · [详情页](../patterns/detail-page.md) · [响应式与移动端](../foundations/responsive-mobile.md)

## 导出

`ui/detail-sheet` 导出 DetailSheet、DetailSheetContent、DetailSheetSurface、DetailSheetHeader、DetailSheetTitle、DetailSheetDescription、DetailSheetFooter。页面可直接引用；`ui/sheet` 为受限原件，页面不得直接导入，见[受限原件](registry.md#受限原件)。

## 组件

- **DetailSheetSurface：**推荐入口。`open` + `update:open` 受控；`embedded` 为真时不渲染抽屉，直接在当前容器内铺满内容（用于详情页内嵌同一份内容）；`elevated` 用于叠在其他浮层之上。默认插槽承载内容。
- **DetailSheetContent：**固定右侧弹出，宽度为视口四分之三并设上限，窄视口全屏并使用动态视口高度、避开安全区域；内边距为 0，由内容自行排布。`elevated` 同上。
- **Header / Title / Description / Footer：**与 Sheet 同构；标题字号见[令牌数值](../foundations/token-values.md#控件与版式)的浮层标题。

## 使用约束

- 页面不得覆盖抽屉宽度、圆角、阴影或层级；不使用 Dialog 的 `size` 档位。
- 内容区内部滚动，页面背景不得横向滚动。
- 抽屉内的编辑在关闭前有未保存内容时调用 `confirmDiscardChanges('close')`，见[确认对话框](confirm-dialog.md)。
- 同一对象的详情只走一条抽屉轨道，不叠第二层详情抽屉。

[返回组件契约](README.md)
