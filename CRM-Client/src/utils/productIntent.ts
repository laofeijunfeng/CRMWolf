export interface ProductIntentRef {
  public_id: string
  name: string
}

export interface ProductIntentSource {
  product_public_id?: string | null
  product_name?: string | null
  products?: ProductIntentRef[]
}

export const productPublicIdFromIntent = (source: ProductIntentSource): string => {
  const publicId = source.product_public_id?.trim() ?? ''
  if (publicId !== '') return publicId
  const firstProductId = source.products?.find(product => product.public_id.trim() !== '')?.public_id
  return firstProductId?.trim() ?? ''
}

export const formatProductIntentName = (
  source: ProductIntentSource,
  emptyLabel = '-',
): string => {
  const productName = source.product_name?.trim() ?? ''
  if (productName !== '') return productName

  const publicId = productPublicIdFromIntent(source)
  const matchedName = source.products?.find(product => product.public_id === publicId)?.name.trim() ?? ''
  if (matchedName !== '') return matchedName

  const firstName = source.products?.find(product => product.name.trim() !== '')?.name.trim() ?? ''
  if (firstName !== '') return firstName
  return emptyLabel
}
