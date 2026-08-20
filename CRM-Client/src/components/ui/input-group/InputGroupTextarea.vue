<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { useVModel } from "@vueuse/core"
import { cn } from "@/lib/utils"
import { Textarea } from "@/components/ui/textarea"

interface TextareaComponentInstance {
  $el: Element | null
}

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
  defaultValue?: string | number | undefined
  modelValue?: string | number | undefined
  rows?: number
  autoResize?: boolean
  minRows?: number
  maxRows?: number
}>(), {
  autoResize: false,
  minRows: 3,
  maxRows: 10,
})

const emits = defineEmits<(e: "update:modelValue", payload: string | number | undefined) => void>()

const modelValue = useVModel(props, "modelValue", emits, {
  passive: true,
  defaultValue: props.defaultValue,
})
const textareaRef = ref<TextareaComponentInstance | null>(null)

const normalizedMinRows = computed(() => Math.max(1, Math.floor(props.minRows)))
const normalizedMaxRows = computed(() => Math.max(normalizedMinRows.value, Math.floor(props.maxRows)))

const getTextareaElement = (): HTMLTextAreaElement | null => {
  const element = textareaRef.value?.$el
  if (typeof HTMLTextAreaElement === "undefined" || !(element instanceof HTMLTextAreaElement)) return null
  return element
}

const parseCssPixels = (value: string, fallback: number): number => {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const resizeTextarea = async (): Promise<void> => {
  await nextTick()
  const textarea = getTextareaElement()
  if (textarea === null) return

  if (!props.autoResize) {
    textarea.style.height = ""
    textarea.style.overflowY = ""
    return
  }

  const styles = window.getComputedStyle(textarea)
  const lineHeight = parseCssPixels(styles.lineHeight, parseCssPixels(styles.fontSize, 14) * 1.5)
  const paddingHeight = parseCssPixels(styles.paddingTop, 0) + parseCssPixels(styles.paddingBottom, 0)
  const borderHeight = parseCssPixels(styles.borderTopWidth, 0) + parseCssPixels(styles.borderBottomWidth, 0)
  const minHeight = lineHeight * normalizedMinRows.value + paddingHeight + borderHeight
  const maxHeight = lineHeight * normalizedMaxRows.value + paddingHeight + borderHeight

  textarea.style.height = "auto"
  const nextHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight)
  textarea.style.height = `${nextHeight}px`
  textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden"
}

watch(
  [modelValue, (): boolean => props.autoResize, normalizedMinRows, normalizedMaxRows],
  (): void => void resizeTextarea(),
  { flush: "post" },
)
onMounted(() => void resizeTextarea())
</script>

<template>
  <Textarea
    ref="textareaRef"
    data-slot="input-group-control"
    v-model="modelValue"
    :rows="props.autoResize ? normalizedMinRows : props.rows"
    :class="cn(
      'flex-1 resize-none rounded-none border-0 bg-transparent py-3 shadow-none ring-offset-transparent focus-visible:ring-0 focus-visible:ring-transparent focus-visible:ring-offset-0',
      props.class,
    )"
    @input="resizeTextarea"
  />
</template>
