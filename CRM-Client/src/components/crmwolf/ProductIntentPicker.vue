<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'
import { usePermissionStore } from '@/stores/permissions'
import {
  EMPTY_CATALOG_MESSAGE,
  useProductCatalog,
} from '@/composables/useProductCatalog'

interface Props {
  modelValue: string
  disabled?: boolean
  invalid?: boolean
  idPrefix?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  invalid: false,
  idPrefix: 'product-intent',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const permissionStore = usePermissionStore()
const { loading, forbidden, empty, load, optionsFor } = useProductCatalog()
const canCreate = computed(() => permissionStore.hasPermission('product:create'))
const labelId = computed(() => `${props.idPrefix}-label`)
const errorId = computed(() => `${props.idPrefix}-error`)
const options = computed(() =>
  optionsFor(props.modelValue).map(product => ({
    value: product.public_id,
    label: product.name,
  })),
)

onMounted(() => {
  void load()
})

function handleChange(value: string): void {
  if (props.disabled || value === props.modelValue) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="space-y-2">
    <p :id="labelId" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
      产品 <span class="text-wolf-danger" aria-hidden="true">*</span>
    </p>
    <p v-if="loading" class="text-sm text-wolf-text-secondary">加载产品中...</p>
    <template v-else-if="forbidden" />
    <template v-else-if="empty">
      <p class="text-sm text-wolf-text-secondary">{{ EMPTY_CATALOG_MESSAGE }}</p>
      <RouterLink
        v-if="canCreate"
        to="/settings/products?action=create"
        class="text-sm text-wolf-text-link"
      >
        去创建产品
      </RouterLink>
    </template>
    <SegmentedChoiceControl
      v-else
      :model-value="modelValue"
      :options="options"
      :disabled="disabled"
      :labelled-by="labelId"
      :id-prefix="idPrefix"
      :invalid="invalid"
      :described-by="errorId"
      :style="{ '--segmented-choice-columns': String(Math.min(Math.max(options.length, 1), 4)) }"
      @update:model-value="handleChange"
    />
  </div>
</template>
