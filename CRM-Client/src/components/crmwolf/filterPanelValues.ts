export type FilterValue = string | number
export type FilterValues = Record<string, FilterValue>

export interface FilterFieldShape {
  key: string
}

export const syncFilterValues = (
  fields: readonly FilterFieldShape[],
  externalValues: FilterValues
): FilterValues => {
  const synchronizedValues: FilterValues = {}
  fields.forEach(field => {
    synchronizedValues[field.key] = externalValues[field.key] ?? ''
  })
  Object.entries(externalValues).forEach(([key, value]) => {
    if (!(key in synchronizedValues)) synchronizedValues[key] = value
  })
  return synchronizedValues
}

export const buildResetValues = (
  fields: readonly FilterFieldShape[],
  currentValues: FilterValues
): FilterValues => {
  const resetValues = syncFilterValues(fields, currentValues)
  Object.keys(resetValues).forEach(key => {
    resetValues[key] = ''
  })
  return resetValues
}
