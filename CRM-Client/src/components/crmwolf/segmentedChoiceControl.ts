/** 分段选择每个选项按钮的元素 id；宿主可用它把焦点移到指定选项（如校验失败时的首个选项）。 */
export function segmentedChoiceOptionId(idPrefix: string, value: string): string {
  return `${idPrefix}-${value.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}
