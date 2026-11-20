/**
 * CRMWolf Design System Components
 * UI/UX Pro Max compliant primitives
 */

// Field components
export { default as InputField } from './InputField.vue'
export { default as SelectField } from './SelectField.vue'
export { default as TextareaField } from './TextareaField.vue'
export { default as DateField } from './DateField.vue'
export { default as SegmentedChoiceControl } from './SegmentedChoiceControl.vue'
export { default as ProductIntentPicker } from './ProductIntentPicker.vue'
export { default as SelectionSummary } from './SelectionSummary.vue'
export { default as SearchableSelectField } from './SearchableSelectField.vue'
export { default as IndustryHierarchySelectField } from './IndustryHierarchySelectField.vue'

// Navigation components (§9 HIGH Priority)
export { default as BottomNav } from './BottomNav.vue'
export { default as BottomNavItem } from './BottomNavItem.vue'
export { default as BottomNavOverflow } from './BottomNavOverflow.vue'
export { default as ContextTabs } from './ContextTabs.vue'
export { default as DetailContextHeader } from './DetailContextHeader.vue'
export { default as DetailContextHost } from './DetailContextHost.vue'
export { default as TopBarTabs } from './TopBarTabs.vue'

// Data display components
export { default as DataTable } from './DataTable.vue'
export { default as DataTableSearch } from './DataTableSearch.vue'
export { default as AmountText } from './AmountText.vue'
export { default as CopyableText } from './CopyableText.vue'
export { default as FileAttachment } from './FileAttachment.vue'
export { default as FilePreviewDialog } from './FilePreviewDialog.vue'
export { default as ListCard } from './ListCard.vue'
export { default as MetricCard } from './MetricCard.vue'
export { default as AreaTrendChart } from './AreaTrendChart.vue'
export { default as ListFilterPopover } from './ListFilterPopover.vue'
export { default as ListSortPopover } from './ListSortPopover.vue'
export { default as ColumnConfigPopover } from './ColumnConfigPopover.vue'
export { default as MultiSelect } from './MultiSelect.vue'
export { default as TableToolbarButton } from './TableToolbarButton.vue'
export { default as TableToolbarBuilderPanel } from './TableToolbarBuilderPanel.vue'
export { default as TableRowActions } from './TableRowActions.vue'
export { default as DesktopTableRowActions } from './DesktopTableRowActions.vue'
export { default as HoverInfo } from './HoverInfo.vue'
export { default as FieldHelpTip } from './FieldHelpTip.vue'
export { default as StatusBadge } from './StatusBadge.vue'
export { default as ApprovalStatusBadge } from './ApprovalStatusBadge.vue'
export { default as DataTableExportDialog } from './DataTableExportDialog.vue'
export type { DataTableExportDialogField } from './DataTableExportDialog.vue'

// Export types
export type { ActionConfig } from './tableRowActionTypes'
export type { DesktopTableRowActionProjection, MobileTableRowActionProjection, TableRowActionSet, TableRowActionGroup } from './tableRowActionGroups'
export {
  groupTableRowActions,
  hasVisibleTableRowActions,
  shouldShowTableRowActionGroupLabels,
  getDesktopTableRowActions,
  getDesktopTableRowActionsWidth,
  getMobileTableRowActions,
  getTableRowActionLabel,
  isDestructiveTableRowAction,
  isDetailTableRowAction
} from './tableRowActionGroups'
export type { ColumnConfigOption } from './columnConfigTypes'
export type { ListFieldExportConfig, DataTableExportField } from './listFieldCatalog'
export { isUnsafeExportKey } from './listFieldCatalog'
export { defineListFields, projectListFieldCatalog } from './listFieldCatalog'
export type { ListFilterCondition, ListFilterField } from './listFilterTypes'
export type { ListSortCondition, ListSortField } from './listSortTypes'

// Feedback components (§8 MEDIUM Priority)
export { default as LoadingSkeleton } from './LoadingSkeleton.vue'
export { default as DataViewStatePanel } from './DataViewStatePanel.vue'
export { default as ErrorState } from './ErrorState.vue'
export type { DataViewState } from './DataViewStatePanel.vue'
export { default as LiveRegion } from './LiveRegion.vue'
export { default as ConfirmDialog } from './ConfirmDialog.vue'
export { default as ActionOptionCard } from './ActionOptionCard.vue'
export { default as RenameDialog } from './RenameDialog.vue'
export { default as FormErrorSummary } from './FormErrorSummary.vue'
