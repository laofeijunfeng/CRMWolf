<script setup lang="ts">
import { nextTick } from 'vue'

export interface FormErrorSummaryItem {
  field: string
  label: string
  message: string
  targetId?: string
}

interface Props {
  items: FormErrorSummaryItem[]
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '请先修正以下字段：'
})

async function focusField(item: FormErrorSummaryItem): Promise<void> {
  if (item.targetId === undefined || typeof document === 'undefined') return

  await nextTick()
  const target = document.getElementById(item.targetId)
  if (!(target instanceof HTMLElement)) return

  target.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  target.focus({ preventScroll: true })
}
</script>

<template>
  <section
    v-if="props.items.length > 0"
    class="form-error-summary"
    role="alert"
    aria-live="assertive"
    aria-atomic="true"
  >
    <h3 class="form-error-summary__title">{{ props.title }}</h3>
    <ul class="form-error-summary__list">
      <li v-for="item in props.items" :key="item.field" class="form-error-summary__item">
        <button
          v-if="item.targetId"
          type="button"
          class="form-error-summary__link"
          @click="focusField(item)"
        >
          {{ item.label }}：{{ item.message }}
        </button>
        <span v-else>{{ item.label }}：{{ item.message }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped lang="scss">
.form-error-summary {
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgb(220 38 38 / 30%);
  border-radius: 0.375rem;
  background: rgb(220 38 38 / 5%);
  color: hsl(var(--destructive));
  font-size: 0.875rem;
}

.form-error-summary__title {
  margin: 0;
  font-weight: 600;
}

.form-error-summary__list {
  display: grid;
  gap: 0.25rem;
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}

.form-error-summary__link {
  color: inherit;
  text-align: left;
  text-decoration: underline;
  text-underline-offset: 0.15em;
}

.form-error-summary__link:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
</style>
