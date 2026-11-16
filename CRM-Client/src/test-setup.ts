import { afterEach, vi } from 'vitest'
import cssEscape from 'css.escape'

// jsdom has no layout engine; keep the browser APIs used by responsive controls
// available while individual tests can still stub viewport changes explicitly.
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: (query: string): MediaQueryList => {
    const target = new EventTarget()
    const constraints = [...query.matchAll(/\((min|max)-width:\s*(\d+)px\)/g)]
    return {
      media: query,
      matches: constraints.length > 0 && constraints.every((match) => {
        const width = Number(match[2])
        return match[1] === 'min' ? window.innerWidth >= width : window.innerWidth <= width
      }),
      onchange: null,
      addListener: (listener) => target.addEventListener('change', listener as EventListener),
      removeListener: (listener) => target.removeEventListener('change', listener as EventListener),
      addEventListener: target.addEventListener.bind(target),
      removeEventListener: target.removeEventListener.bind(target),
      dispatchEvent: target.dispatchEvent.bind(target),
    }
  },
})

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  writable: true,
  value: vi.fn(),
})

if (typeof window.CSS?.escape !== 'function') {
  if (window.CSS === undefined) {
    Object.defineProperty(window, 'CSS', {
      configurable: true,
      writable: true,
      value: { escape: cssEscape },
    })
  } else {
    Object.defineProperty(window.CSS, 'escape', {
      configurable: true,
      writable: true,
      value: cssEscape,
    })
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})
