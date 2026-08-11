import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

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
