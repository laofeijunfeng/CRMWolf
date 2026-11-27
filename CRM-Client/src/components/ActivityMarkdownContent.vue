<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import { renderActivityMarkdown } from '@/utils/activityMarkdown'

interface Props {
  content: string
  collapsible?: boolean
  maxHeight?: number
}

const props = withDefaults(defineProps<Props>(), {
  collapsible: false,
  maxHeight: 168,
})

const bodyRef = ref<HTMLElement | null>(null)
const expanded = ref(false)
const isOverflowing = ref(false)
let resizeObserver: ResizeObserver | null = null

const renderedHtml = computed(() => renderActivityMarkdown(props.content))

const shouldClamp = computed(() => props.collapsible && isOverflowing.value && !expanded.value)

const bodyStyle = computed(() => {
  if (!shouldClamp.value) return undefined
  return { maxHeight: `${props.maxHeight}px` }
})

const measureOverflow = (): void => {
  if (!props.collapsible || !bodyRef.value) {
    isOverflowing.value = false
    return
  }
  const el = bodyRef.value
  isOverflowing.value = el.scrollHeight > props.maxHeight + 4
}

const toggleExpanded = (): void => {
  expanded.value = !expanded.value
}

onMounted(() => {
  void nextTick(measureOverflow)
  if (typeof ResizeObserver !== 'undefined' && bodyRef.value) {
    resizeObserver = new ResizeObserver(() => {
      measureOverflow()
    })
    resizeObserver.observe(bodyRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

watch(
  () => [props.content, props.collapsible, props.maxHeight],
  () => {
    expanded.value = false
    void nextTick(measureOverflow)
  },
)
</script>

<template>
  <div class="activity-markdown-root min-w-0" data-activity-markdown>
    <div class="relative min-w-0">
      <div
        ref="bodyRef"
        class="activity-markdown-body min-w-0 text-body text-foreground [overflow-wrap:anywhere]"
        :class="{ 'overflow-hidden': shouldClamp }"
        :style="bodyStyle"
        v-html="renderedHtml"
      />
      <div
        v-if="shouldClamp"
        class="activity-markdown-fade pointer-events-none absolute inset-x-0 bottom-0 h-10"
        aria-hidden="true"
      />
    </div>
    <button
      v-if="collapsible && isOverflowing"
      type="button"
      class="mt-1.5 inline-flex items-center gap-1 text-caption font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      data-activity-markdown-toggle
      @click="toggleExpanded"
    >
      <span>{{ expanded ? '收起' : '展开全文' }}</span>
      <ChevronUp v-if="expanded" class="h-3.5 w-3.5" />
      <ChevronDown v-else class="h-3.5 w-3.5" />
    </button>
  </div>
</template>

<style scoped>
.activity-markdown-fade {
  background: linear-gradient(
    to bottom,
    transparent 0%,
    hsl(var(--background) / 0.85) 65%,
    hsl(var(--background)) 100%
  );
}

.activity-markdown-body {
  line-height: 1.6;
}

.activity-markdown-body :deep(*:first-child) {
  margin-top: 0;
}

.activity-markdown-body :deep(*:last-child) {
  margin-bottom: 0;
}

.activity-markdown-body :deep(p) {
  margin: 0.375rem 0;
}

.activity-markdown-body :deep(h1),
.activity-markdown-body :deep(h2),
.activity-markdown-body :deep(h3),
.activity-markdown-body :deep(h4) {
  margin: 0.625rem 0 0.25rem;
  font-size: var(--font-size-body, 0.875rem);
  font-weight: 600;
  line-height: 1.45;
  color: hsl(var(--foreground));
}

.activity-markdown-body :deep(ul),
.activity-markdown-body :deep(ol) {
  margin: 0.375rem 0;
  padding-left: 1.25rem;
}

.activity-markdown-body :deep(ul) {
  list-style-type: disc;
}

.activity-markdown-body :deep(ol) {
  list-style-type: decimal;
}

.activity-markdown-body :deep(li) {
  margin: 0.1875rem 0;
}

.activity-markdown-body :deep(strong) {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.activity-markdown-body :deep(blockquote) {
  margin: 0.5rem 0;
  border-left: 2px solid hsl(var(--border));
  padding-left: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.activity-markdown-body :deep(a) {
  color: hsl(var(--primary));
  text-decoration: underline;
  text-underline-offset: 2px;
}

.activity-markdown-body :deep(code) {
  border-radius: var(--radius-sm, 0.25rem);
  background: hsl(var(--muted));
  padding: 0.0625rem 0.25rem;
  font-size: 0.875em;
  color: hsl(var(--foreground));
}

.activity-markdown-body :deep(pre) {
  margin: 0.5rem 0;
  overflow-x: auto;
  border-radius: var(--radius-sm, 0.375rem);
  background: hsl(var(--muted));
  padding: 0.625rem 0.75rem;
}

.activity-markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

.activity-markdown-body :deep(hr) {
  margin: 0.625rem 0;
  border: 0;
  border-top: 1px solid hsl(var(--border));
}

.activity-markdown-body :deep(table) {
  margin: 0.5rem 0;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.activity-markdown-body :deep(th),
.activity-markdown-body :deep(td) {
  border: 1px solid hsl(var(--border));
  padding: 0.25rem 0.5rem;
  text-align: left;
}

.activity-markdown-body :deep(th) {
  background: hsl(var(--muted) / 0.5);
  font-weight: 600;
}
</style>
