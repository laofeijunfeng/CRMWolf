<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'
import { Label } from '@/components/ui/label'
import { usePermissionStore } from '@/stores/permissions'
import {
  EMPTY_CATALOG_MESSAGE,
  useProductCatalog,
} from '@/composables/useProductCatalog'

interface Props {
  modelValue: string
  disabled?: boolean | undefined
  invalid?: boolean | undefined
  idPrefix?: string | undefined
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
  <div class="grid gap-1">
    <Label :id="labelId" class="text-caption font-medium text-foreground">
      产品 <span class="text-danger" aria-hidden="true">*</span>
    </Label>
    <p v-if="loading" class="text-sm text-muted-foreground">加载产品中...</p>
    <template v-else-if="forbidden" />
    <template v-else-if="empty">
      <p class="text-sm text-muted-foreground">{{ EMPTY_CATALOG_MESSAGE }}</p>
      <RouterLink
        v-if="canCreate"
        to="/settings/products?action=create"
        class="text-sm text-brand"
      >
        去创建产品
      </RouterLink>
    </template>
    <SegmentedChoiceControl
      v-else
      :model-value="modelValue"
      :options="options"
      :disabled="props.disabled"
      :labelled-by="labelId"
      :id-prefix="props.idPrefix"
      :invalid="props.invalid"
      :described-by="errorId"
      :style="{ '--segmented-choice-columns': String(Math.min(Math.max(options.length, 1), 3)) }"
      @update:model-value="handleChange"
    />
  </div>
</template>
