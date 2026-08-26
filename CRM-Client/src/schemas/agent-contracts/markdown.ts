const RAW_HTML_PATTERN = /<(?:[A-Za-z][^>]*|\/[A-Za-z][^>]*|![^>]*|\?[^>]*)>/

const DISALLOWED_BLOCK_PATTERNS: readonly (readonly [RegExp, string])[] = [
  [/^[ \t]{0,3}#{1,6}(?:[ \t]+|$)/m, 'headings'],
  [/^[ \t]{0,3}>/m, 'blockquotes'],
  [/^[ \t]{0,3}(?:`{3,}|~{3,})/m, 'fenced code blocks'],
  [/^[ \t]{0,3}(?:[-+*]|\d+[.)])[ \t]+\[[ xX]\](?:[ \t]+|$)/m, 'task lists'],
  [/^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$/m, 'thematic breaks'],
  [/^[ \t]{0,3}={2,}[ \t]*$/m, 'setext headings'],
  [/^(?: {4,}|\t)\S/m, 'indented code blocks'],
  [/^[ \t]{0,3}\[[^\]\n]+\]:/m, 'reference-style links'],
  [/^[ \t]*\|?[^\n|]+\|[^\n]*\n[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$/m, 'tables']
]

const IMAGE_PATTERN = /!\[/g
const STRIKETHROUGH_PATTERN = /~~/g
const REFERENCE_LINK_PATTERN = /\[[^\]\n]+\]\[[^\]\n]*\]/g
const INLINE_LINK_PATTERN = /\[[^\]\n]+\]\(([^)\n]*)\)/g
const LINK_OPEN_PATTERN = /\]\(/g
const HTTP_LINK_PATTERN = /^https?:\/\/[^()]+$/i

export function restrictedMarkdownError(text: string): string | null {
  if (RAW_HTML_PATTERN.test(text)) return 'text blocks must not contain raw HTML'

  for (const [pattern, syntaxName] of DISALLOWED_BLOCK_PATTERNS) {
    if (pattern.test(text)) return `markdown syntax is not allowed: ${syntaxName}`
  }

  const visibleText = maskInlineCode(text)
  if (hasUnescapedMatch(IMAGE_PATTERN, visibleText)) return 'markdown syntax is not allowed: images'
  if (hasUnescapedMatch(STRIKETHROUGH_PATTERN, visibleText)) return 'markdown syntax is not allowed: strikethrough'
  if (hasUnescapedMatch(REFERENCE_LINK_PATTERN, visibleText)) return 'markdown syntax is not allowed: reference-style links'

  const withoutValidLinks = visibleText.split('')
  INLINE_LINK_PATTERN.lastIndex = 0
  for (const match of visibleText.matchAll(INLINE_LINK_PATTERN)) {
    const start = match.index ?? 0
    if (isEscaped(visibleText, start)) continue
    const destination = trimAsciiWhitespace(match[1] ?? '')
    if (!HTTP_LINK_PATTERN.test(destination) || containsForbiddenLinkWhitespace(destination)) {
      return 'markdown links must use an absolute HTTP(S) URL'
    }
    withoutValidLinks.splice(start, match[0].length, ...Array.from({ length: match[0].length }, () => ' '))
  }

  if (hasUnescapedMatch(LINK_OPEN_PATTERN, withoutValidLinks.join(''))) {
    return 'markdown links must use the supported inline HTTP(S) form'
  }
  return null
}

export function containsRawHtml(text: string): boolean {
  return RAW_HTML_PATTERN.test(text)
}


function trimAsciiWhitespace(value: string): string {
  let start = 0
  let end = value.length
  while (start < end && isAsciiWhitespace(value.charCodeAt(start))) start += 1
  while (end > start && isAsciiWhitespace(value.charCodeAt(end - 1))) end -= 1
  return value.slice(start, end)
}

function isAsciiWhitespace(codePoint: number): boolean {
  return (codePoint >= 0x0009 && codePoint <= 0x000d) || codePoint === 0x0020
}

function containsForbiddenLinkWhitespace(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? -1
    if (
      (codePoint >= 0x0009 && codePoint <= 0x000d) ||
      (codePoint >= 0x001c && codePoint <= 0x0020) ||
      codePoint === 0x0085 ||
      codePoint === 0x00a0 ||
      codePoint === 0x1680 ||
      (codePoint >= 0x2000 && codePoint <= 0x200a) ||
      codePoint === 0x2028 ||
      codePoint === 0x2029 ||
      codePoint === 0x202f ||
      codePoint === 0x205f ||
      codePoint === 0x3000 ||
      codePoint === 0xfeff
    ) return true
  }
  return false
}

function hasUnescapedMatch(pattern: RegExp, text: string): boolean {
  pattern.lastIndex = 0
  for (const match of text.matchAll(pattern)) {
    if (!isEscaped(text, match.index ?? 0)) return true
  }
  return false
}

function maskInlineCode(text: string): string {
  const masked = text.split('')
  let index = 0
  while (index < text.length) {
    if (text[index] !== '`' || isEscaped(text, index)) {
      index += 1
      continue
    }
    let delimiterEnd = index
    while (delimiterEnd < text.length && text[delimiterEnd] === '`') delimiterEnd += 1
    const delimiter = text.slice(index, delimiterEnd)
    const closing = text.indexOf(delimiter, delimiterEnd)
    if (closing === -1 || text.slice(delimiterEnd, closing).includes('\n')) {
      index = delimiterEnd
      continue
    }
    const closingEnd = closing + delimiter.length
    for (let position = index; position < closingEnd; position += 1) {
      if (masked[position] !== '\n') masked[position] = ' '
    }
    index = closingEnd
  }
  return masked.join('')
}

function isEscaped(text: string, index: number): boolean {
  let slashCount = 0
  index -= 1
  while (index >= 0 && text[index] === '\\') {
    slashCount += 1
    index -= 1
  }
  return slashCount % 2 === 1
}
