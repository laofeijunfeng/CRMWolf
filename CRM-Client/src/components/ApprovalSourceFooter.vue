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
@use '@/styles/variables-v2.scss' as *;

.approval-source-footer {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-lg-v2 $wolf-space-xl-v2;
  padding-bottom: calc(#{$wolf-space-lg-v2} + #{$wolf-safe-area-bottom-v2});
  border-top: 1px solid $wolf-border-default-v2;
  min-width: 0;
}

.approval-source-footer__note {
  margin: 0;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border-radius: $wolf-radius-control-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  line-height: 1.6;
}

.approval-source-footer__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
