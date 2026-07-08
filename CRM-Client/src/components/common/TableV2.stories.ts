/**
 * TableV2 Stories（CRMWolf Design System V2）
 *
 * 展示 TableV2 组件的所有状态和变体：
 * - 基础表格
 * - 斑马纹表格
 * - 可排序表格
 * - 可点击行
 * - 空状态
 * - 自定义单元格
 * - 自适应行高
 *
 * 设计规范：MASTER.md §3.3 Table
 * - No vertical divider lines（无竖分割线）
 * - Adaptive row height（自适应行高）
 * - Hover state visible
 * - Focus ring for interactive cells
 *
 * 注：项目当前未安装 Storybook 运行时；本文件遵循 COMPONENTS.md
 * 「共享组件必须配 .stories.ts」约定，作为 props 文档与未来接入
 * Storybook 时的入口。
 */

import TableV2 from './TableV2.vue'
import type { TableColumn, TableRow } from './TableV2.vue'

// ==================== 类型定义 ====================

interface StoryArgs {
  columns: TableColumn[]
  data: TableRow[]
  rowKey?: string
  striped?: boolean
  hoverable?: boolean
  clickable?: boolean
  ariaLabel?: string
}

// ==================== 示例数据 ====================

const basicColumns: TableColumn[] = [
  { key: 'name', title: '客户名称', width: '200px' },
  { key: 'status', title: '状态', width: '100px' },
  { key: 'amount', title: '金额', width: '120px', align: 'right' },
  { key: 'date', title: '创建日期', width: '150px' },
]

const sortableColumns: TableColumn[] = [
  { key: 'name', title: '客户名称', width: '200px', sortable: true },
  { key: 'status', title: '状态', width: '100px' },
  { key: 'amount', title: '金额', width: '120px', align: 'right', sortable: true },
  { key: 'date', title: '创建日期', width: '150px', sortable: true },
]

const basicData: TableRow[] = [
  { id: 1, name: '北京科技有限公司', status: '活跃', amount: '¥ 12,500.00', date: '2024-01-15' },
  { id: 2, name: '上海创新科技', status: '待跟进', amount: '¥ 8,300.00', date: '2024-01-12' },
  { id: 3, name: '广州智能系统', status: '活跃', amount: '¥ 45,000.00', date: '2024-01-10' },
  { id: 4, name: '深圳数据服务', status: '已成交', amount: '¥ 120,000.00', date: '2024-01-08' },
  { id: 5, name: '成都软件开发', status: '活跃', amount: '¥ 23,800.00', date: '2024-01-05' },
]

const longContentData: TableRow[] = [
  {
    id: 1,
    name: '北京科技有限公司这是一家专注于企业数字化转型的高新技术企业主要业务包括软件开发系统集成云计算服务',
    status: '活跃',
    amount: '¥ 12,500.00',
    date: '2024-01-15',
  },
  { id: 2, name: '上海创新科技', status: '待跟进', amount: '¥ 8,300.00', date: '2024-01-12' },
]

// ==================== Stories ====================

/** Basic: 基础表格 */
const basicStory: StoryArgs = {
  columns: basicColumns,
  data: basicData,
  ariaLabel: '客户列表',
}

/** Striped: 斑马纹表格 */
const stripedStory: StoryArgs = {
  columns: basicColumns,
  data: basicData,
  striped: true,
  ariaLabel: '客户列表（斑马纹）',
}

/** Sortable: 可排序表格 */
const sortableStory: StoryArgs = {
  columns: sortableColumns,
  data: basicData,
  ariaLabel: '客户列表（可排序）',
}

/** ClickableRows: 可点击行 */
const clickableRowsStory: StoryArgs = {
  columns: basicColumns,
  data: basicData,
  clickable: true,
  ariaLabel: '客户列表（可点击）',
}

/** Empty: 空状态 */
const emptyStory: StoryArgs = {
  columns: basicColumns,
  data: [],
  ariaLabel: '客户列表（空）',
}

/** AdaptiveHeight: 自适应行高 */
const adaptiveHeightStory: StoryArgs = {
  columns: basicColumns,
  data: longContentData,
  ariaLabel: '客户列表（自适应行高）',
}

/** NoHover: 无 hover 效果 */
const noHoverStory: StoryArgs = {
  columns: basicColumns,
  data: basicData,
  hoverable: false,
  ariaLabel: '客户列表（无 hover）',
}

// ==================== 导出 Stories ====================

export const stories = {
  basic: basicStory,
  striped: stripedStory,
  sortable: sortableStory,
  clickableRows: clickableRowsStory,
  empty: emptyStory,
  adaptiveHeight: adaptiveHeightStory,
  noHover: noHoverStory,
}

// ==================== Props 文档 ====================

/**
 * TableV2 Props
 *
 * @property {TableColumn[]} columns - 列配置数组
 * @property {TableRow[]} data - 表格数据数组
 * @property {string} rowKey - 行唯一键字段（默认: 'id'）
 * @property {boolean} striped - 是否显示斑马纹（默认: false）
 * @property {boolean} hoverable - 是否显示行 hover 效果（默认: true）
 * @property {boolean} clickable - 行是否可点击（默认: false）
 * @property {string} ariaLabel - 无障碍标签（默认: '数据表格'）
 *
 * Events:
 * @event rowClick(row: TableRow, index: number) - 行点击事件
 * @event sortChange(key: string, order: 'asc' | 'desc' | null) - 排序变化事件
 *
 * Slots:
 * @slot cell-{key} - 自定义单元格（props: { row, value, rowIndex }）
 * @slot empty - 自定义空状态
 */

export { TableV2 }
export type { TableColumn, TableRow }