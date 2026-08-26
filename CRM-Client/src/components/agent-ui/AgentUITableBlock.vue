<script setup lang="ts">
import { computed } from 'vue'

import { formatAgentUIValue } from './agentUIFormatting'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type TableBlock = Extract<AgentUIBlock, { type: 'table' }>

type TableCell = TableBlock['rows'][number]['cells'][number]

const props = defineProps<{ block: TableBlock }>()

const cellsByRow = computed(() => new Map(
  props.block.rows.map(row => [row.id, new Map(row.cells.map(cell => [cell.column_key, cell]))])
))

const cellFor = (rowId: string, columnKey: string): TableCell | undefined => {
  return cellsByRow.value.get(rowId)?.get(columnKey)
}

const formattedCell = (rowId: string, columnKey: string): string => {
  const cell = cellFor(rowId, columnKey)
  return cell === undefined ? '-' : formatAgentUIValue(cell.value)
}
</script>

<template>
  <div class="agent-ui-table-wrap max-w-full overflow-x-auto rounded-md border border-border bg-card">
    <table class="agent-ui-table w-full min-w-[480px] border-collapse">
      <caption v-if="block.caption" class="p-3 text-left font-semibold text-card-foreground">
        {{ block.caption }}
      </caption>
      <thead>
        <tr>
          <th
            v-for="column in block.columns"
            :key="column.key"
            scope="col"
            :class="[
              'h-11 border-b border-border bg-muted px-2 py-3 align-top text-xs font-medium text-muted-foreground whitespace-nowrap',
              `agent-ui-table__cell--${column.align}`,
            ]"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in block.rows" :key="row.id">
          <td
            v-for="column in block.columns"
            :key="column.key"
            :class="[
              'h-11 border-b border-border px-2 py-3 align-top text-foreground whitespace-nowrap',
              `agent-ui-table__cell--${column.align}`,
            ]"
          >
            {{ formattedCell(row.id, column.key) }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="block.rows.length === 0" class="m-0 p-4 text-center text-muted-foreground">
      没有可展示的数据。
    </p>
  </div>
</template>

<style scoped>
.agent-ui-table tbody tr:last-child td {
  border-bottom: 0;
}

.agent-ui-table__cell--center { text-align: center; }
.agent-ui-table__cell--right { text-align: right; }
</style>
