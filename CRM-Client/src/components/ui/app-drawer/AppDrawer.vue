<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer"
import { X } from "lucide-vue-next"
import { Button } from "@/components/ui/button"

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  description?: string
  showOverlay?: boolean
  overlayClass?: string
  contentClass?: string
  portal?: boolean
  modal?: boolean
}>(), {
  description: "",
  showOverlay: true,
  overlayClass: "",
  contentClass: "",
  portal: true,
  modal: true,
})

const emit = defineEmits<{
  "update:open": [open: boolean]
  "height-change": [height: number]
}>()

const contentRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null

const drawerElement = (): HTMLElement | null => contentRef.value?.parentElement ?? null

const updateHeight = (): void => {
  const drawer = drawerElement()
  const content = contentRef.value
  emit("height-change", drawer?.getBoundingClientRect().height ?? content?.getBoundingClientRect().height ?? 0)
}

const observeContent = (): void => {
  resizeObserver?.disconnect()
  resizeObserver = null

  if (!contentRef.value) {
    updateHeight()
    return
  }

  resizeObserver = new ResizeObserver(updateHeight)
  resizeObserver.observe(contentRef.value)
  const drawer = drawerElement()
  if (drawer !== null) resizeObserver.observe(drawer)
  updateHeight()
  requestAnimationFrame(updateHeight)
}

watch(() => props.open, async (open) => {
  if (!open) {
    resizeObserver?.disconnect()
    resizeObserver = null
    emit("height-change", 0)
    return
  }

  await nextTick()
  observeContent()
}, { immediate: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})
</script>

<template>
  <Drawer
    :open="props.open"
    :modal="props.modal"
    :should-scale-background="false"
    @update:open="emit('update:open', $event)"
  >
    <DrawerContent
      :show-overlay="props.showOverlay"
      :overlay-class="props.overlayClass"
      :portal="props.portal"
      :class="['app-drawer', props.contentClass]"
    >
      <div ref="contentRef" class="app-drawer__content">
        <DrawerHeader class="app-drawer__header">
          <div class="app-drawer__title-row">
            <DrawerTitle class="app-drawer__title">{{ props.title }}</DrawerTitle>
            <DrawerClose as-child>
              <Button type="button" variant="ghost" size="icon" class="app-drawer__close" aria-label="关闭抽屉">
                <X class="h-4 w-4" aria-hidden="true" />
              </Button>
            </DrawerClose>
          </div>
          <DrawerDescription v-if="props.description" class="app-drawer__description">
            {{ props.description }}
          </DrawerDescription>
        </DrawerHeader>
        <div class="app-drawer__body">
          <slot />
        </div>
      </div>
    </DrawerContent>
  </Drawer>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.app-drawer {
  max-height: min(80svh, 720px);
  overflow: hidden;
  border-color: hsl(var(--border));
  border-top-left-radius: var(--radius-xl);
  border-top-right-radius: var(--radius-xl);
  background: hsl(var(--card));
  box-shadow: var(--shadow-3);
}

.app-drawer__content {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(100%, 720px);
  max-height: inherit;
  min-height: 0;
  margin: 0 auto;
  padding: 0 var(--page-padding) $space-4;
}

.app-drawer__header {
  padding: $space-3 0 $space-2;
  text-align: left;
}

.app-drawer__title-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: $space-3;
}

.app-drawer__title {
  min-width: 0;
  color: hsl(var(--foreground));
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.app-drawer__close {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
}

.app-drawer__description {
  color: hsl(var(--muted-foreground));
  font-size: 14px;
  line-height: 20px;
}

.app-drawer__body {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

@media (max-width: 767px) {
  .app-drawer__content {
    padding-right: var(--page-padding);
    padding-bottom: calc($space-3 + var(--safe-bottom));
    padding-left: var(--page-padding);
  }
}
</style>
