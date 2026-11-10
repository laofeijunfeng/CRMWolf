<script setup lang="ts">
/**
 * 审批下钻主体详情顶部：返回审批详情入口 + 来源审批只读提示。
 * 关闭按钮由 SheetContent 自带的右上角关闭提供。
 */
import { ArrowLeft } from 'lucide-vue-next'
import { Alert, AlertDescription } from '@/components/ui/alert'
import type { ApprovalSourceContext } from '@/types/approvalSource'

defineProps<{
  source: ApprovalSourceContext
  /** 当前主体详情名称，如「回款详情」 */
  subjectLabel: string
}>()

const emit = defineEmits<{
  back: []
}>()
</script>

<template>
  <div class="approval-source-header">
    <nav class="approval-source-header__nav" aria-label="审批下钻路径">
      <button
        type="button"
        class="approval-source-header__back"
        aria-label="返回审批详情"
        data-testid="approval-source-back-top"
        @click="emit('back')"
      >
        <ArrowLeft class="h-4 w-4" aria-hidden="true" />
      </button>
      <div class="approval-source-header__breadcrumb">
        <button
          type="button"
          class="approval-source-header__breadcrumb-back"
          data-testid="approval-source-back-breadcrumb"
          @click="emit('back')"
        >
          审批详情
        </button>
        <span class="approval-source-header__sep" aria-hidden="true">/</span>
        <span class="approval-source-header__current" aria-current="page">{{ subjectLabel }}</span>
      </div>
    </nav>
    <Alert variant="info" class="approval-source-header__banner" data-testid="approval-source-banner">
      <AlertDescription>
        来自{{ source.approvalLabel }} {{ source.applicationNumber }} · <span class="whitespace-nowrap">只读查看</span>
      </AlertDescription>
    </Alert>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-source-header {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-lg-v2 $wolf-space-xl-v2 0;
  padding-right: calc(#{$wolf-space-xl-v2} + 32px);
  min-width: 0;
}

.approval-source-header__nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-width: 0;
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-secondary-v2;
}

.approval-source-header__back,
.approval-source-header__breadcrumb-back {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  flex-shrink: 0;
  min-height: 32px;
  border: 0;
  background: transparent;
  padding: 0;
  color: $wolf-primary-v2;
  font-weight: 500;
  cursor: pointer;

  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
    outline-offset: 2px;
    border-radius: $wolf-radius-sm-v2;
  }
}

.approval-source-header__current {
  overflow-wrap: anywhere;
  min-width: 0;
}

.approval-source-header__back {
  justify-content: center;
  width: 32px;
}

.approval-source-header__breadcrumb {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-width: 0;
}

.approval-source-header__banner {
  overflow-wrap: anywhere;
}
</style>
