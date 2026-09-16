export interface OpportunityProductSummarySource {
  product_name?: string | null
  product_modules?: { name: string }[]
}

export const formatOpportunityModuleNames = (
  source: OpportunityProductSummarySource,
): string =>
  (source.product_modules ?? [])
    .map(module => module.name)
    .filter(name => name.trim() !== '')
    .join('、')

export const formatOpportunityProductName = (
  source: OpportunityProductSummarySource,
  emptyLabel = '-',
): string => {
  const productName = source.product_name?.trim() ?? ''
  if (productName !== '') return productName
  return emptyLabel
}

export const formatOpportunityProductSummary = (
  source: OpportunityProductSummarySource,
  emptyLabel = '-',
): string => {
  const productName = source.product_name?.trim() ?? ''
  const moduleNames = formatOpportunityModuleNames(source)
  if (productName !== '' && moduleNames !== '') return `${productName} · ${moduleNames}`
  if (productName !== '') return productName
  if (moduleNames !== '') return moduleNames
  return emptyLabel
}
