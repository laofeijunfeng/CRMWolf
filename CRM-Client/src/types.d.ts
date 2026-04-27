/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'node:url' {
  export const URL: any
  export const fileURLToPath: any
  export const pathToFileURL: any
}
