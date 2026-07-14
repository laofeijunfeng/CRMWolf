export type FilterValue = string | number
export type FilterValues = Record<string, FilterValue>

export interface FilterFieldShape {
  key: string
}

export const buildResetValues = (
  fields: readonly FilterFieldShape[],
  currentValues: FilterValues
): FilterValues => {
  const resetValues: FilterValues = {}
  fields.forEach(field => {
    resetValues[field.key] = ''
  })
  Object.keys(currentValues).forEach(key => {
    if (!(key in resetValues)) resetValues[key] = ''
  })
  return resetValues
}
