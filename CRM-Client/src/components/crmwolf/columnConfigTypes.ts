export interface ColumnConfigOption {
  key: string
  title: string
  visible: boolean
  fixed?: 'left' | 'right' | undefined
  configurable: boolean
  hideable: boolean
}
