<script setup lang="ts">
import { ref, computed } from 'vue'

interface ParamValue {
  value: string
  isEntity?: boolean
}

interface Props {
  round?: number
  title: string
  params: Record<string, ParamValue>
  riskLevel?: 'low' | 'medium' | 'high'
  status?: 'waiting' | 'confirmed' | 'cancelled'
}

const props = withDefaults(defineProps<Props>(), {
  riskLevel: 'medium',
  status: 'waiting'
})

const emit = defineEmits<{
  confirm: []
  cancel: []
  entityClick: [value: ParamValue]
}>()

const expanded = ref(false)

const toggleExpand = () => {
  expanded.value = !expanded.value
}

const riskLevelClass = computed(() => {
  return props.riskLevel === 'low' ? 'low-risk' :
         props.riskLevel === 'high' ? 'high-risk' : ''
})

const statusClass = computed(() => props.status)

const statusLabel = computed(() => {
  return props.status === 'confirmed' ? '已确认' :
         props.status === 'cancelled' ? '已取消' : '待确认'
})

const inlineParams = computed(() => {
  // 摘要参数：最多 3 个
  const keys = Object.keys(props.params).slice(0, 3)
  return keys.map(k => `${k}: ${props.params[k].value}`).join(' · ')
})

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('cancel')
}

const handleEntityClick = (value: ParamValue) => {
  if (value.isEntity) {
    emit('entityClick', value)
  }
}
</script>

<template>
  <!-- 摘要状态 -->
  <div
    class="confirmation-summary"
    :class="[riskLevelClass, statusClass, { expanded: expanded }]"
    @click="toggleExpand"
  >
    <span v-if="round" class="round-badge current">R{{ round }}</span>
    <span class="status-icon warning">⚠</span>
    <span class="confirm-label" :class="statusClass">{{ statusLabel }}</span>
    <span class="params-inline">{{ title }} · {{ inlineParams }}</span>
    <span class="expand-hint">{{ expanded ? '↑ 收起' : '[点击展开详情]' }}</span>
  </div>

  <!-- 展开状态 -->
  <div v-if="expanded" class="confirmation-expanded">
    <div class="expanded-params">
      <div v-for="(value, key) in params" :key="key" class="expanded-param-row">
        <span class="expanded-param-name">{{ key }}：</span>
        <span
          class="expanded-param-value"
          :class="{ entity: value.isEntity }"
          @click.stop="handleEntityClick(value)"
        >
          {{ value.value }}
        </span>
      </div>
    </div>
    <div class="action-buttons">
      <button class="btn-sm btn-confirm" @click="handleConfirm">确认执行</button>
      <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.confirmation-summary {
  padding: 6px 16px;
  background: #FFF6E8;
  border-left: 3px solid #7A4F1E;
  border-radius: 4px;
  margin: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 14px;
}

.confirmation-summary:hover {
  filter: brightness(0.98);
}

.confirmation-summary.high-risk {
  border-left-width: 4px;
  border-left-color: #7A2828;
  background: #FDECEC;
}

.confirmation-summary.low-risk {
  border-left-width: 2px;
  border-left-color: #2B633C;
  background: #EDF7EF;
}

.confirmation-summary.confirmed {
  background: #EDF7EF;
  border-left-color: #2B633C;
}

.confirmation-summary.cancelled {
  background: #F5F5F5;
  border-left-color: #9A9A9A;
}

.confirm-label {
  font-size: 12px;
  color: #7A4F1E;
  font-weight: 500;
  background: rgba(122, 79, 30, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.confirm-label.confirmed {
  color: #2B633C;
  background: rgba(43, 99, 60, 0.1);
}

.confirm-label.cancelled {
  color: #9A9A9A;
  background: rgba(154, 154, 154, 0.1);
}

.params-inline {
  flex: 1;
  color: #1C1C1C;
}

.expand-hint {
  font-size: 12px;
  color: #636363;
}

.confirmation-expanded {
  padding: 8px 16px;
  background: #FFF6E8;
  border-left: 3px solid #7A4F1E;
  border-radius: 4px;
  margin: 4px 16px;
}

.confirmation-summary.high-risk + .confirmation-expanded {
  background: #FDECEC;
  border-left-color: #7A2828;
}

.confirmation-summary.low-risk + .confirmation-expanded {
  background: #EDF7EF;
  border-left-color: #2B633C;
}

.expanded-params {
  font-size: 12px;
  background: white;
  padding: 8px;
  border-radius: 4px;
}

.expanded-param-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.expanded-param-name {
  color: #636363;
  font-weight: 500;
}

.expanded-param-value {
  color: #1C1C1C;
}

.expanded-param-value.entity {
  color: #4A6FA5;
  cursor: pointer;
  text-decoration: underline;
}

.expanded-param-value.entity:hover {
  color: #4065A0;
}

.action-buttons {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn-sm {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  border: none;
  transition: background 0.15s;
}

.btn-confirm {
  background: #4A6FA5;
  color: white;
}

.btn-confirm:hover {
  background: #4065A0;
}

.btn-cancel {
  background: #F5F5F5;
  color: #3A3A3A;
  border: 1px solid #E5E5E5;
}

.btn-cancel:hover {
  background: #EBEBEB;
}

.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: #FFF6E8;
  border-radius: 4px;
  font-size: 11px;
  color: #7A4F1E;
  font-weight: 500;
  margin-right: 6px;
}

.round-badge.current {
  background: #FFF6E8;
  color: #7A4F1E;
}

.status-icon {
  font-size: 14px;
  flex-shrink: 0;
}

// 无障碍：减少动画
@media (prefers-reduced-motion: reduce) {
  .confirmation-summary,
  .btn-sm,
  .expanded-param-value.entity {
    transition: none;
  }
}
</style>