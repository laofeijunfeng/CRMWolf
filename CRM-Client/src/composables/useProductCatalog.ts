import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { toast } from 'vue-sonner'
import productApi from '@/api/product'
import type { ProductResponse } from '@/schemas/product'
import { handleApiError } from '@/utils/errorHandler'

export const EMPTY_CATALOG_MESSAGE = '团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建'
export const PRODUCT_VIEW_FORBIDDEN_MESSAGE = '没有产品查看权限'

export interface UseProductCatalogReturn {
  products: Ref<ProductResponse[]>
  loading: Ref<boolean>
  forbidden: Ref<boolean>
  empty: ComputedRef<boolean>
  load: () => Promise<void>
  optionsFor: (currentPublicId?: string | null) => ProductResponse[]
}

function isForbiddenError(error: unknown): error is { response: { status: 403 } } {
  if (typeof error !== 'object' || error === null || !('response' in error)) return false
  const response = error.response
  return typeof response === 'object' && response !== null && 'status' in response && response.status === 403
}

export function useProductCatalog(): UseProductCatalogReturn {
  const products = ref<ProductResponse[]>([])
  const loading = ref(false)
  const forbidden = ref(false)
  const empty = computed(() => products.value.every(product => !product.is_active))

  const load = async (): Promise<void> => {
    loading.value = true
    forbidden.value = false
    try {
      products.value = await productApi.list()
    } catch (error) {
      products.value = []
      if (isForbiddenError(error)) {
        forbidden.value = true
        toast.error(PRODUCT_VIEW_FORBIDDEN_MESSAGE)
      } else {
        handleApiError(error, '获取产品')
      }
    } finally {
      loading.value = false
    }
  }

  const optionsFor = (currentPublicId?: string | null): ProductResponse[] => {
    const currentId = currentPublicId ?? ''
    const active = products.value.filter(product => product.is_active)
    if (currentId === '' || active.some(product => product.public_id === currentId)) {
      return active
    }
    const current = products.value.find(product => product.public_id === currentId)
    return current === undefined ? active : [...active, current]
  }

  return {
    products,
    loading,
    forbidden,
    empty,
    load,
    optionsFor,
  }
}
