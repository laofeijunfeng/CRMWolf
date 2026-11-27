import { describe, expect, it } from 'vitest'
import { isSafeActivityLink, renderActivityMarkdown } from '../activityMarkdown'

describe('activityMarkdown', () => {
  it('renders structured Markdown headings, bold, lists, and line breaks', () => {
    const html = renderActivityMarkdown('### 沟通要点\n- **预算**：50万\n- 下周安排演示')
    expect(html).toContain('<h3>沟通要点</h3>')
    expect(html).toContain('<strong>预算</strong>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>')
  })

  it('escapes raw HTML and script tags instead of executing them', () => {
    const html = renderActivityMarkdown('<script>alert(1)</script><img src=x onerror=alert(2)>')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('allows only http, https, and mailto links and adds target/rel for external links', () => {
    expect(isSafeActivityLink('https://example.com/doc')).toBe(true)
    expect(isSafeActivityLink('http://example.com')).toBe(true)
    expect(isSafeActivityLink('mailto:sales@example.com')).toBe(true)
    expect(isSafeActivityLink('javascript:alert(1)')).toBe(false)
    expect(isSafeActivityLink('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isSafeActivityLink('vbscript:msgbox(1)')).toBe(false)

    const safeHtml = renderActivityMarkdown('[文档](https://example.com/doc)')
    expect(safeHtml).toContain('href="https://example.com/doc"')
    expect(safeHtml).toContain('target="_blank"')
    expect(safeHtml).toContain('rel="noopener noreferrer"')

    const unsafeHtml = renderActivityMarkdown('[点我](javascript:alert(1))')
    expect(unsafeHtml).not.toContain('href="javascript:')
  })

  it('gracefully renders legacy plain text and malformed Markdown without throwing', () => {
    const plain = renderActivityMarkdown('第一行原文\n第二行原文')
    expect(plain).toContain('第一行原文')
    expect(plain).toContain('<br>')
    expect(plain).toContain('第二行原文')

    const malformed = renderActivityMarkdown('**未闭合粗体 [坏链接](   \n```ts\nconst a = 1')
    expect(malformed).toContain('未闭合粗体')
    expect(malformed).toContain('const a = 1')
  })
})
