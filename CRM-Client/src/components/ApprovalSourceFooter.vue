<script setup lang="ts">
/**
 * 审批下钻主体详情底部：只读说明 + 返回审批详情按钮。
 */
import { ArrowLeft } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

const emit = defineEmits<{
  back: []
}>()
</script>

<template>
  <div class="approval-source-footer">
    <p class="approval-source-footer__note" data-testid="approval-source-readonly-note">
      此处仅查看主体资料。审批操作仍在原审批详情中完成，查看主体不会改变审批状态。
    </p>
    <div class="approval-source-footer__actions">
      <Button
        type="button"
        variant="outline"
        data-testid="approval-source-back-bottom"
        @click="emit('back')"
      >
        <ArrowLeft class="mr-2 h-4 w-4" aria-hidden="true" />
        返回审批详情
      </Button>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.approval-source-footer {
  display: flex;
  flex-direction: column;
  gap: $space-3;
  padding: $space-4 $space-6;
  padding-bottom: calc(#{$space-4} + #{var(--safe-bottom)});
  border-top: 1px solid hsl(var(--border));
  min-width: 0;
}

.approval-source-footer__note {
  margin: 0;
  padding: $space-2 $space-3;
  border-radius: var(--radius-md);
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  line-height: 1.6;
}

.approval-source-footer__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
