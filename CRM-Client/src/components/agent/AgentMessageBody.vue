<template>
  <div
    v-if="format === 'markdown'"
    class="agent-message-body agent-message-body--markdown"
    v-html="renderedMarkdown"
  />
  <div v-else class="agent-message-body agent-message-body--text">
    {{ content }}
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import MarkdownIt from "markdown-it"
import type { AgentContentFormat } from "@/api/agent"

const props = withDefaults(defineProps<{
  content: string
  format?: AgentContentFormat
}>(), {
  format: "text",
})

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const renderedMarkdown = computed(() => markdown.render(normalizeMarkdownForDisplay(props.content)))

const normalizeMarkdownForDisplay = (content: string): string => {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/([^\n])\s+(#{1,6}\s+\d+[.、]\s+)/g, "$1\n\n$2")
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-message-body {
  min-width: 0;
  overflow-wrap: anywhere;
}

.agent-message-body--text {
  white-space: pre-wrap;
}

.agent-message-body--markdown {
  white-space: normal;
}

.agent-message-body--markdown :deep(*) {
  margin: 0;
}

.agent-message-body--markdown :deep(p + p),
.agent-message-body--markdown :deep(p + ul),
.agent-message-body--markdown :deep(p + ol),
.agent-message-body--markdown :deep(ul + p),
.agent-message-body--markdown :deep(ol + p),
.agent-message-body--markdown :deep(ul + ul),
.agent-message-body--markdown :deep(ol + ol) {
  margin-top: $wolf-space-sm-v2;
}

.agent-message-body--markdown :deep(h1),
.agent-message-body--markdown :deep(h2),
.agent-message-body--markdown :deep(h3),
.agent-message-body--markdown :deep(h4) {
  margin-bottom: $wolf-space-xs-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-body-v2;
}

.agent-message-body--markdown :deep(h1:not(:first-child)),
.agent-message-body--markdown :deep(h2:not(:first-child)),
.agent-message-body--markdown :deep(h3:not(:first-child)),
.agent-message-body--markdown :deep(h4:not(:first-child)) {
  margin-top: $wolf-space-md-v2;
}

.agent-message-body--markdown :deep(ul),
.agent-message-body--markdown :deep(ol) {
  display: grid;
  gap: $wolf-space-xs-v2;
  padding-left: $wolf-space-lg-v2;
}

.agent-message-body--markdown :deep(li) {
  padding-left: $wolf-space-xs-v2;
}

.agent-message-body--markdown :deep(strong) {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.agent-message-body--markdown :deep(a) {
  color: $wolf-primary-v2;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.agent-message-body--markdown :deep(code) {
  border-radius: $wolf-radius-sm-v2;
  background: rgba($wolf-text-primary-v2, 0.08);
  padding: 1px 4px;
  color: $wolf-text-primary-v2;
  font-size: 0.92em;
}

.agent-message-body--markdown :deep(pre) {
  overflow-x: auto;
  border-radius: $wolf-radius-v2;
  background: rgba($wolf-text-primary-v2, 0.08);
  padding: $wolf-space-sm-v2;
}

.agent-message-body--markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}
</style>
