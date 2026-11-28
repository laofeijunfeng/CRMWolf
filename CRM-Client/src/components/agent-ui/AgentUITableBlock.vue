<script setup lang="ts">
import { computed } from 'vue'

import DataTable from '@/components/crmwolf/DataTable.vue'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'

import { formatAgentUIValue } from './agentUIFormatting'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type TableBlock = Extract<AgentUIBlock, { type: 'table' }>

type AgentUITableRow = Record<string, string>

const props = defineProps<{ block: TableBlock }>()

// 只读嵌入：列直接来自表格块。首列是识别列，按列表页的主列样式呈现；其余列不参与筛排与字段配置。
const fields = computed<ListFieldDefinition[]>(() => props.block.columns.map((column, index) => (
  index === 0
    ? {
        key: column.key,
        label: column.label,
        column: { align: column.align },
        filter: false,
        filterDisabledReason: '助手表格只读嵌入，不提供筛选',
        sort: false,
        sortDisabledReason: '助手表格只读嵌入，不提供排序',
      }
    : {
        key: column.key,
        label: column.label,
        role: 'decoration' as const,
        column: { align: column.align },
      }
)))
const rows = computed<AgentUITableRow[]>(() => props.block.rows.map((row) => Object.fromEntries(
  row.cells.map((cell) => [cell.column_key, formatAgentUIValue(cell.value)])
)))
const pageSize = computed(() => Math.max(props.block.rows.length, 1))
</script>

<template>
  <div class="grid min-w-0 gap-space-2">
    <p v-if="block.caption" class="m-0 text-body font-medium text-foreground">{{ block.caption }}</p>
    <div v-if="rows.length > 0" class="w-full max-w-full overflow-x-auto">
      <DataTable
        embedded
        :fields="fields"
        :data="rows"
        :total="rows.length"
        :page="1"
        :page-size="pageSize"
        height-strategy="auto"
      >
        <template
          v-for="column in block.columns"
          :key="column.key"
          #[`cell-${column.key}`]="{ value }"
        >
          <span class="whitespace-nowrap">{{ value ?? '-' }}</span>
        </template>
      </DataTable>
    </div>
    <p v-else class="m-0 text-caption text-muted-foreground">没有可展示的数据。</p>
  </div>
</template>
