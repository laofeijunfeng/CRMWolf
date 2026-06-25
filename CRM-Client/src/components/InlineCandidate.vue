<script setup lang="ts">
interface EntityCandidate {
  id: number
  name: string
  entity_info_inline?: string
  entity_info_detail?: Record<string, string>
}

interface Props {
  candidate: EntityCandidate
  selected?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: false
})

const emit = defineEmits<{
  select: [id: number]
  cancel: []
}>()

const handleSelect = () => {
  emit('select', props.candidate.id)
}

const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
    case ' ':  // Space key
      handleSelect()
      event.preventDefault()
      break
    case 'Escape':
      emit('cancel')
      event.preventDefault()
      break
  }
}
</script>

<template>
  <div
    class="candidate-inline"
    :class="{ selected: selected }"
    @click="handleSelect"
    @keydown="handleKeydown"
    tabindex="0"
    role="radio"
    :aria-checked="selected"
  >
    <!-- Radio (14px) -->
    <span class="candidate-radio" :class="{ selected: selected }">
      <span v-if="selected" class="radio-dot"></span>
    </span>

    <!-- 实体名称 -->
    <span class="candidate-name">{{ candidate.name }}</span>

    <!-- Entity Info Inline (括号由 CSS 生成) -->
    <span class="entity-info-inline">{{ candidate.entity_info_inline }}</span>
  </div>
</template>

<style scoped lang="scss">
.candidate-inline {
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: all 0.15s;
  font-size: 14px;
}

.candidate-inline:hover {
  background: #F5F5F5;
  border-color: #F2F3F5;
}

.candidate-inline:focus-visible {
  outline: 2px solid #4A6FA5;
  outline-offset: 1px;
  box-shadow: 0 0 0 4px rgba(74, 111, 165, 0.15);
}

.candidate-inline.selected {
  background: rgba(74, 111, 165, 0.1);
  border-color: #4A6FA5;
}

.candidate-radio {
  width: 14px;
  height: 14px;
  border: 1.5px solid #E5E5E5;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.candidate-radio.selected {
  border-color: #4A6FA5;
  background: #4A6FA5;
}

.radio-dot {
  width: 4px;
  height: 4px;
  background: white;
  border-radius: 50%;
}

.candidate-name {
  font-weight: 500;
  color: #1C1C1C;
}

.entity-info-inline {
  font-size: 12px;
  color: #636363;
  margin-left: 4px;

  &::before { content: '('; }
  &::after { content: ')'; }
}

// 无障碍：减少动画
@media (prefers-reduced-motion: reduce) {
  .candidate-inline,
  .candidate-radio {
    transition: none;
  }
}
</style>