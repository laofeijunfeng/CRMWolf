<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cancelRenameDialog, confirmRenameDialog, useRenameDialogState } from '@/utils/renameDialog'

const state = useRenameDialogState()
const draftName = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

const normalizedName = computed(() => draftName.value.trim())
const errorMessage = computed(() => {
  if (!state.value.visible) return ''
  if (normalizedName.value.length === 0) return '名称不能为空'
  if (normalizedName.value.length > state.value.options.maxLength) {
    return `名称不能超过 ${state.value.options.maxLength} 个字符`
  }
  return ''
})
const canSubmit = computed(() => errorMessage.value === '')

function handleOpenChange(open: boolean): void {
  if (!open) {
    cancelRenameDialog()
  }
}

function handleSubmit(): void {
  if (!canSubmit.value) return
  confirmRenameDialog(normalizedName.value)
}

watch(
  () => state.value.visible,
  async (visible) => {
    if (!visible) return
    draftName.value = state.value.options.initialName
    await nextTick()
    inputRef.value?.focus()
    inputRef.value?.select()
  }
)
</script>

<template>
  <Dialog :open="state.visible" @update:open="handleOpenChange">
    <DialogContent size="sm" class="rename-dialog">
      <DialogHeader>
        <DialogTitle>{{ state.options.title }}</DialogTitle>
        <DialogDescription v-if="state.options.description">
          {{ state.options.description }}
        </DialogDescription>
      </DialogHeader>

      <form class="rename-dialog__form" @submit.prevent="handleSubmit">
        <div class="rename-dialog__field">
          <Input
            ref="inputRef"
            v-model="draftName"
            :maxlength="state.options.maxLength"
            aria-label="视图名称"
            :aria-invalid="errorMessage.length > 0"
            placeholder="请输入视图名称"
          />
          <p v-if="errorMessage" class="rename-dialog__error">{{ errorMessage }}</p>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" @click="cancelRenameDialog">
            {{ state.options.cancelText }}
          </Button>
          <Button type="submit" :disabled="!canSubmit">
            {{ state.options.confirmText }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">

.rename-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rename-dialog__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rename-dialog__error {
  font-size: var(--font-size-caption);
  line-height: 18px;
  color: hsl(var(--status-danger));
}
</style>
