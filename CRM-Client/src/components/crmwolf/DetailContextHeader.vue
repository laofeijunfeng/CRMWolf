<script setup lang="ts">
import { ArrowLeft, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator
} from '@/components/ui/breadcrumb'
import type { DetailContextNode } from '@/types/detailContext'

interface Props {
  nodes: readonly DetailContextNode[]
  canGoBack: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  back: []
  close: []
  navigate: [index: number]
}>()

const objectTypeLabels: Record<DetailContextNode['type'], string> = {
  customer: '客户',
  opportunity: '商机',
  contract: '合同',
  'payment-plan': '回款计划',
  'payment-record': '回款记录'
}

const getNodeLabel = (node: DetailContextNode): string => {
  const label = node.label.trim()
  return label.length > 0 ? label : objectTypeLabels[node.type]
}
</script>

<template>
  <header class="detail-context-header" data-testid="detail-context-header">
    <div class="detail-context-header__navigation">
      <Button
        v-if="props.canGoBack"
        type="button"
        variant="ghost"
        size="icon"
        class="detail-context-header__back"
        aria-label="返回上一级详情"
        data-testid="detail-context-back"
        @click="emit('back')"
      >
        <ArrowLeft class="h-4 w-4" aria-hidden="true" />
      </Button>

      <Breadcrumb>
        <BreadcrumbList>
          <template v-for="(node, index) in props.nodes" :key="`${node.type}-${node.id}`">
            <BreadcrumbSeparator v-if="index > 0" />
            <BreadcrumbItem>
              <BreadcrumbPage v-if="index === props.nodes.length - 1">
                {{ getNodeLabel(node) }}
              </BreadcrumbPage>
              <BreadcrumbLink v-else as-child>
                <button
                  type="button"
                  class="detail-context-header__crumb"
                  :aria-label="`返回${getNodeLabel(node)}`"
                  @click="emit('navigate', index)"
                >
                  {{ getNodeLabel(node) }}
                </button>
              </BreadcrumbLink>
            </BreadcrumbItem>
          </template>
        </BreadcrumbList>
      </Breadcrumb>
    </div>

    <Button
      type="button"
      variant="ghost"
      size="icon"
      class="detail-context-header__close"
      aria-label="关闭详情"
      data-testid="detail-context-close"
      @click="emit('close')"
    >
      <X class="h-4 w-4" aria-hidden="true" />
    </Button>
  </header>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.detail-context-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  min-height: $wolf-touch-target-min-v2;
  padding: $wolf-space-sm-v2 $wolf-space-xl-v2;
  border-bottom: $wolf-focus-ring-width-subtle-v2 solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}

.detail-context-header__navigation {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: $wolf-space-xs-v2;
}

.detail-context-header__crumb {
  max-width: 220px;
  overflow: hidden;
  color: inherit;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-context-header__crumb:hover {
  color: $wolf-primary-v2;
}
</style>
