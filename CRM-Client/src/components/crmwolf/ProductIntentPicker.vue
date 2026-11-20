<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'
import { Label } from '@/components/ui/label'
import { usePermissionStore } from '@/stores/permissions'
import {
  EMPTY_CATALOG_MESSAGE,
  PRODUCT_VIEW_FORBIDDEN_MESSAGE,
  useProductCatalog,
  type UseProductCatalogReturn,
} from '@/composables/useProductCatalog'

interface Props {
  modelValue: string
  disabled?: boolean | undefined
  invalid?: boolean | undefined
  idPrefix?: string | undefined
  /** 由宿主持有并加载的产品目录；传入后本组件不再自行加载 */
  catalog?: UseProductCatalogReturn | undefined
  /** 当前值由业务事实决定，不可修改 */
  locked?: boolean | undefined
  /** 无产品查看权限时展示的当前产品名称 */
  fallbackName?: string | null | undefined
  hint?: string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  invalid: false,
  idPrefix: 'product-intent',
  catalog: undefined,
  locked: false,
  fallbackName: null,
  hint: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const permissionStore = usePermissionStore()
const { loading, forbidden, empty, load, optionsFor } = props.catalog ?? useProductCatalog()
const canCreate = computed(() => permissionStore.hasPermission('product:create'))
const labelId = computed(() => `${props.idPrefix}-label`)
const errorId = computed(() => `${props.idPrefix}-error`)
const hintId = computed(() => `${props.idPrefix}-hint`)
const fallbackLabel = computed(() => props.fallbackName?.trim() ?? '')
const options = computed(() =>
  optionsFor(props.modelValue).map(product => ({
    value: product.public_id,
    label: product.name,
  })),
)

onMounted(() => {
  if (props.catalog === undefined) void load()
})

function handleChange(value: string): void {
  if (props.disabled || props.locked || value === props.modelValue) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="grid gap-1">
    <Label :id="labelId" class="text-caption font-medium text-foreground">
      产品 <span class="text-danger" aria-hidden="true">*</span>
    </Label>
    <p v-if="loading" class="text-sm text-muted-foreground">加载产品中...</p>
    <template v-else-if="forbidden">
      <p
        v-if="fallbackLabel !== ''"
        class="text-sm text-foreground"
        :aria-labelledby="labelId"
        data-testid="product-intent-readonly"
      >
        {{ fallbackLabel }}
      </p>
      <p v-else-if="props.catalog !== undefined" :id="errorId" class="text-sm text-danger" role="alert">
        {{ PRODUCT_VIEW_FORBIDDEN_MESSAGE }}
      </p>
    </template>
    <template v-else-if="empty && !(props.locked && options.length > 0)">
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
      :disabled="props.disabled || props.locked"
      :labelled-by="labelId"
      :id-prefix="props.idPrefix"
      :invalid="props.invalid"
      :described-by="props.hint !== '' ? `${errorId} ${hintId}` : errorId"
      :style="{ '--segmented-choice-columns': String(Math.min(Math.max(options.length, 1), 3)) }"
      @update:model-value="handleChange"
    />
    <p v-if="props.hint !== '' && !loading" :id="hintId" class="text-caption text-muted-foreground">
      {{ props.hint }}
    </p>
  </div>
</template>
