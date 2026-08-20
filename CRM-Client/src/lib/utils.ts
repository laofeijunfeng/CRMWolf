import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      rounded: [{
        rounded: [
          'wolf',
          'wolf-sm',
          'wolf-md',
          'wolf-lg',
          'wolf-xl',
          'wolf-surface',
          'wolf-overlay',
          'wolf-sheet',
          'wolf-popover',
          'wolf-full'
        ]
      }],
      shadow: [{
        shadow: [
          'wolf-card',
          'wolf-hover',
          'wolf-overlay',
          'wolf-dropdown',
          'wolf-modal',
          'wolf-bottom'
        ]
      }]
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
