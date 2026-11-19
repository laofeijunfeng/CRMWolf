import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      spacing: ['space-1', 'space-2', 'space-3', 'space-4', 'space-6', 'space-8']
    },
    classGroups: {
      'font-size': [{ text: ['display', 'title', 'body-strong', 'body', 'caption', 'control-sm'] }],
      shadow: [{ shadow: ['1', '2', '3'] }],
      h: [{ h: ['touch-target', 'control-xs', 'control-sm', 'control', 'control-lg', 'context-tabs'] }],
      'min-h': [{ 'min-h': ['touch-target', 'control-xs', 'control'] }],
      'min-w': [{ 'min-w': ['touch-target', 'menu'] }],
      size: [{ size: ['control-sm', 'control', 'control-lg', 'icon-xs', 'icon-sm', 'icon-lg'] }],
      px: [{ px: ['control-xs', 'control-sm', 'control', 'control-lg'] }],
      gap: [{ gap: ['control-sm', 'control'] }],
      opacity: [{ opacity: ['disabled'] }]
    }
  }
})

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

type OptionalKeys<T extends object> = {
  [K in keyof T]-?: undefined extends T[K] ? K : never
}[keyof T]

type WithoutExplicitUndefined<T extends object> =
  Omit<T, OptionalKeys<T>>
  & { [K in OptionalKeys<T>]?: Exclude<T[K], undefined> }

export function omitUndefined<T extends object>(value: T): WithoutExplicitUndefined<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, entryValue]) => entryValue !== undefined)
  ) as WithoutExplicitUndefined<T>
}
