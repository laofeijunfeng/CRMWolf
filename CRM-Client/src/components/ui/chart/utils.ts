import type { ChartConfig } from "."
import { isClient } from "@vueuse/core"
import { useId } from "reka-ui"
import { h, render } from "vue"

const cache: Record<string, string> = {}

function serializeKey(key: Record<string, unknown>): string {
  return JSON.stringify(key, Object.keys(key).sort())
}

interface Constructor<P = object> {
  __isFragment?: never
  __isTeleport?: never
  __isSuspense?: never
  new (...args: unknown[]): {
    $props: P
  }
}

export function componentToString<P>(config: ChartConfig, component: Constructor<P>, props?: P): ((datum: unknown, x: number | Date) => string) | undefined {
  if (!isClient)
    return

  const id = useId()

  return (datum: unknown, x: number | Date): string => {
    const data = datum !== null && typeof datum === "object" && "data" in datum ? datum.data : datum
    if (data === null || typeof data !== "object") return ""
    const record = data as Record<string, unknown>
    const serializedKey = `${id}-${serializeKey(record)}`
    const cachedContent = cache[serializedKey]
    if (cachedContent !== undefined)
      return cachedContent

    const vnode = h<unknown>(component, { ...props, payload: record, config, x })
    const div = document.createElement("div")
    render(vnode, div)
    cache[serializedKey] = div.innerHTML
    return div.innerHTML
  }
}

