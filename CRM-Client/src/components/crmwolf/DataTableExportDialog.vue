<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import TableToolbarButton from './TableToolbarButton.vue'
import type { DataTableExportField } from './listFieldCatalog'

export interface DataTableExportDialogField extends DataTableExportField {
  visible: boolean
}

const props = defineProps<{
  fields: DataTableExportDialogField[]
  total: number
  title: string
  exportHandler: (fieldKeys: string[]) => Promise<void>
}>()

const open = ref(false)
const submitting = ref(false)
const selected = ref<Set<string>>(new Set())

const visibleFields = computed(() => props.fields.filter((field) => field.visible))
const optionalFields = computed(() => props.fields.filter((field) => !field.visible))
const canSubmit = computed(() => props.total > 0 && selected.value.size > 0 && !submitting.value)

function resetSelection(): void {
  selected.value = new Set(props.fields.filter((field) => field.visible).map((field) => field.key))
}

function toggleField(key: string, checked: boolean): void {
  const next = new Set(selected.value)
  if (checked) {
    next.add(key)
  } else {
    next.delete(key)
  }
  selected.value = next
}

/** Export-only identifiers (业务 ID) always lead the workbook when selected. */
function orderedSelectedKeys(): string[] {
  const exportOnly = props.fields.filter((field) => field.source === 'export-only')
  const ordered = [...exportOnly.map((field) => field.key), ...props.fields.map((field) => field.key)]
  return [...new Set(ordered)].filter((key) => selected.value.has(key))
}

async function handleSubmit(): Promise<void> {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    await props.exportHandler(orderedSelectedKeys())
    open.value = false
  } catch {
    // 保留弹窗与已选字段，允许用户直接重试；错误反馈由共享导出 composable 负责。
  } finally {
    submitting.value = false
  }
}

function handleOpenChange(next: boolean): void {
  if (submitting.value) return
  open.value = next
}

watch(open, (isOpen) => {
  if (isOpen) resetSelection()
})
</script>

<template>
  <Dialog :open="open" @update:open="handleOpenChange">
    <TableToolbarButton
      :aria-label="`导出 ${title}`"
      @click="open = true"
    >
      <Download class="h-4 w-4" aria-hidden="true" />
      <span>导出</span>
    </TableToolbarButton>
    <DialogContent class="data-table-export-dialog">
      <DialogHeader>
        <DialogTitle>导出 Excel</DialogTitle>
        <DialogDescription>将导出当前筛选结果，共 {{ total }} 条。</DialogDescription>
      </DialogHeader>

      <div class="data-table-export-body">
        <section aria-label="当前显示字段">
          <h4 class="data-table-export-group-title">当前显示字段</h4>
          <ul class="data-table-export-list">
            <li
              v-for="field in visibleFields"
              :key="field.key"
              class="data-table-export-field"
              :data-field-key="field.key"
            >
              <Checkbox
                :checked="selected.has(field.key)"
                :aria-label="`导出字段 ${field.label}`"
                @update:checked="toggleField(field.key, $event)"
              />
              <span>{{ field.label }}</span>
            </li>
          </ul>
        </section>
        <section v-if="optionalFields.length > 0" aria-label="其他可选字段">
          <h4 class="data-table-export-group-title">其他可选字段</h4>
          <ul class="data-table-export-list">
            <li
              v-for="field in optionalFields"
              :key="field.key"
              class="data-table-export-field"
              :data-field-key="field.key"
            >
              <Checkbox
                :checked="selected.has(field.key)"
                :aria-label="`导出字段 ${field.label}`"
                @update:checked="toggleField(field.key, $event)"
              />
              <span>{{ field.label }}</span>
            </li>
          </ul>
        </section>
      </div>

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          data-testid="data-table-export-cancel"
          :disabled="submitting"
          @click="open = false"
        >
          取消
        </Button>
        <Button
          type="button"
          data-testid="data-table-export-submit"
          :disabled="!canSubmit"
          @click="handleSubmit"
        >
          {{ submitting ? '正在导出' : '导出' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.data-table-export-body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  max-height: 320px;
  overflow-y: auto;
}

.data-table-export-group-title {
  margin: 0 0 $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: 500;
}

.data-table-export-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  margin: 0;
  padding: 0;
  list-style: none;
}

.data-table-export-field {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}
</style>
