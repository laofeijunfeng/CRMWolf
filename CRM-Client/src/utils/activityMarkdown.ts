import MarkdownIt from 'markdown-it'

const ALLOWED_PROTOCOLS: Record<string, true> = {
  'http:': true,
  'https:': true,
  'mailto:': true,
}

export function isSafeActivityLink(rawUrl: string): boolean {
  const trimmed = rawUrl.trim()
  if (trimmed.length === 0) return false
  // Reject control characters before or within scheme
  for (let idx = 0; idx < trimmed.length; idx += 1) {
    const code = trimmed.charCodeAt(idx)
    if (code <= 0x1f || code === 0x7f) return false
  }
  try {
    const parsed = new URL(trimmed)
    return ALLOWED_PROTOCOLS[parsed.protocol.toLowerCase()] === true
  } catch {
    return false
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function createActivityMarkdownRenderer(): MarkdownIt {
  const md = new MarkdownIt({
    html: false,
    breaks: true,
    linkify: true,
  })

  md.validateLink = (url: string): boolean => isSafeActivityLink(url)

  const defaultLinkOpen =
    md.renderer.rules['link_open'] ??
    ((tokens, idx, options, _env, self): string => self.renderToken(tokens, idx, options))

  md.renderer.rules['link_open'] = (tokens, idx, options, env, self): string => {
    const token = tokens[idx]
    if (token !== undefined) {
      const href = token.attrGet('href') ?? ''
      if (/^https?:/i.test(href.trim())) {
        token.attrSet('target', '_blank')
        token.attrSet('rel', 'noopener noreferrer')
      }
    }
    return defaultLinkOpen(tokens, idx, options, env, self)
  }
  return md
}

const activityMarkdown = createActivityMarkdownRenderer()

export function renderActivityMarkdown(raw: string | null | undefined): string {
  if (raw === null || raw === undefined || raw.length === 0) return ''
  const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  if (normalized.length === 0) return ''
  try {
    return activityMarkdown.render(normalized)
  } catch {
    return `<p>${escapeHtml(normalized).replace(/\n/g, '<br>')}</p>`
  }
}
