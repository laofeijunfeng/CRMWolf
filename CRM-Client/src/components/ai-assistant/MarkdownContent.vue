/**
 * AI 助手 - Markdown 渲染组件
 *
 * 设计原则：
 * - 克制性渲染：只解析真正有用的元素
 * - 不渲染标题：聊天界面不需要标题层级
 * - 品牌色列表标记：签名元素
 */
<template>
  <div
    class="markdown-content"
    v-html="renderedHtml"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

// ========== Props ==========

const props = defineProps({
  /** Markdown 内容 */
  content: {
    type: String,
    required: true
  }
})

// ========== Markdown 配置 ==========

const md = new MarkdownIt({
  html: false,        // 禁止 HTML
  linkify: true,      // 自动链接化
  typographer: true   // 优化排版
})

// 禁用标题渲染（聊天界面不需要）
md.disable(['heading', 'code', 'fence', 'image', 'table', 'blockquote'])

// ========== Computed ==========

/** 渲染后的 HTML */
const renderedHtml = computed(() => {
  if (!props.content) return ''
  return md.render(props.content)
})
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.markdown-content {
  // 段落
  p {
    margin: 0 0 $wolf-space-sm 0;
    line-height: $wolf-line-height-body;

    &:last-child {
      margin-bottom: 0;
    }
  }

  // 强调 - 使用品牌主色而非默认加粗
  strong {
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-primary;
  }

  // 斜体强调
  em {
    font-style: italic;
    color: $wolf-text-secondary;
  }

  // 链接 - 品牌色 + 下划线
  a {
    color: $wolf-primary;
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;

    &:hover {
      color: $wolf-primary-hover;
    }
  }

  // 列表 - 签名元素：品牌色标记
  ul {
    margin: $wolf-space-sm 0;
    padding-left: 0;
    list-style: none; // 去掉默认黑点

    li {
      position: relative;
      padding-left: $wolf-space-md;
      margin-bottom: $wolf-space-xs;
      line-height: $wolf-line-height-body;

      // 品牌色小圆点 - 签名元素
      &:before {
        content: '•';
        position: absolute;
        left: 0;
        color: $wolf-primary;
        font-weight: $wolf-font-weight-semibold;
      }
    }
  }
}
</style>