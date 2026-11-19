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
type AgentMessageFormat = "plain" | "markdown"

const props = withDefaults(defineProps<{
  content: string
  format?: AgentMessageFormat
}>(), {
  format: "plain",
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
@use '@/styles/tokens.scss' as *;

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
  margin-top: $space-2;
}

.agent-message-body--markdown :deep(h1),
.agent-message-body--markdown :deep(h2),
.agent-message-body--markdown :deep(h3),
.agent-message-body--markdown :deep(h4) {
  margin-bottom: $space-1;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.agent-message-body--markdown :deep(h1:not(:first-child)),
.agent-message-body--markdown :deep(h2:not(:first-child)),
.agent-message-body--markdown :deep(h3:not(:first-child)),
.agent-message-body--markdown :deep(h4:not(:first-child)) {
  margin-top: $space-3;
}

.agent-message-body--markdown :deep(ul),
.agent-message-body--markdown :deep(ol) {
  display: grid;
  gap: $space-1;
  padding-left: $space-4;
}

.agent-message-body--markdown :deep(ul) {
  list-style: disc;
}

.agent-message-body--markdown :deep(ol) {
  list-style: decimal;
}

.agent-message-body--markdown :deep(li) {
  padding-left: $space-1;
}

.agent-message-body--markdown :deep(strong) {
  color: hsl(var(--foreground));
  font-weight: 600;
}

.agent-message-body--markdown :deep(a) {
  color: hsl(var(--brand));
  text-decoration: underline;
  text-underline-offset: 2px;
}

.agent-message-body--markdown :deep(code) {
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, hsl(var(--foreground)) 8%, transparent);
  padding: 1px 4px;
  color: hsl(var(--foreground));
  font-size: 0.92em;
}

.agent-message-body--markdown :deep(pre) {
  overflow-x: auto;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, hsl(var(--foreground)) 8%, transparent);
  padding: $space-2;
}

.agent-message-body--markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}
</style>
