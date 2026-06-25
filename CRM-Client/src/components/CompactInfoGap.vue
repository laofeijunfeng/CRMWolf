<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  round?: number
  title: string
  filledParams?: Record<string, string>
  missingField?: string
  fieldOptions?: string[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  submit: [value: string]
  cancel: []
}>()

const inputValue = ref('')

const inlineFilledParams = computed(() => {
  if (!props.filledParams) return ''
  const keys = Object.keys(props.filledParams).slice(0, 3)
  return keys.map(k => `${k}: ${props.filledParams![k]}`).join(' · ')
})

const handleSubmit = () => {
  if (inputValue.value.trim()) {
    emit('submit', inputValue.value.trim())
  }
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <!-- 缺失字段摘要 -->
  <div class="info-gap-summary">
    <span v-if="round" class="round-badge current">R{{ round }}</span>
    <span class="status-icon error">✗</span>
    <span class="gap-label">缺失</span>
    <span class="params-inline">{{ title }} · {{ inlineFilledParams }}</span>
    <span class="missing-field">[需补: {{ missingField }}]</span>
  </div>

  <!-- Inline Input Form -->
  <div class="inline-input-row">
    <span class="inline-input-label">{{ missingField }}:</span>
    <input
      v-model="inputValue"
      class="inline-input-box"
      :placeholder="`请输入${missingField}`"
      @keyup.enter="handleSubmit"
    />
    <button class="inline-search-btn" @click="handleSubmit">提交</button>
  </div>

  <div class="action-buttons">
    <button class="btn-sm btn-confirm" @click="handleSubmit">重新提交</button>
    <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
  </div>
</template>

<style scoped lang="scss">
.info-gap-summary {
  padding: 6px 16px;
  background: #FDECEC;
  border-left: 3px solid #7A2828;
  border-radius: 4px;
  margin: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.gap-label {
  font-size: 12px;
  color: #7A2828;
  font-weight: 500;
  background: rgba(122, 28, 28, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.missing-field {
  color: #7A2828;
  font-weight: 500;
  flex-shrink: 0;
}

.params-inline {
  flex: 1;
  color: #1C1C1C;
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
  flex-shrink: 0;
}

.status-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.inline-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 16px;
  background: white;
  border: 1px solid #E5E5E5;
  border-radius: 4px;
  margin: 4px 16px;
}

.inline-input-label {
  font-size: 14px;
  color: #636363;
  font-weight: 500;
  flex-shrink: 0;
}

.inline-input-box {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid #E5E5E5;
  border-radius: 4px;
  font-size: 14px;
  min-width: 120px;
}

.inline-input-box:focus {
  outline: 2px solid #4A6FA5;
  border-color: #4A6FA5;
}

.inline-search-btn {
  padding: 4px 12px;
  background: #4A6FA5;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}

.inline-search-btn:hover {
  background: #4065A0;
}

.action-buttons {
  display: flex;
  gap: 8px;
  padding: 4px 16px;
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

// Reduced Motion
@media (prefers-reduced-motion: reduce) {
  .btn-sm,
  .inline-search-btn {
    transition: none;
  }
}
</style>