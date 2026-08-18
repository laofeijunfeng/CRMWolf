import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { acquisitionSourceApi } from '@/api/acquisition-source'
import {
  toAcquisitionSourceSelectOptions,
  type AcquisitionSourceInfo,
  type AcquisitionSourceOption,
} from '@/schemas/acquisition-source'
import { handleApiError } from '@/utils/errorHandler'

interface UseAcquisitionSourceOptionsReturn {
  formOptions: Ref<AcquisitionSourceOption[]>
  filterOptions: Ref<AcquisitionSourceOption[]>
  formSelectOptions: ComputedRef<{ value: string; label: string }[]>
  filterSelectOptions: ComputedRef<{ value: string; label: string }[]>
  loading: Ref<boolean>
  loadFormOptions: () => Promise<void>
  loadFilterOptions: () => Promise<void>
  ensureOption: (option?: AcquisitionSourceInfo | null) => void
}

function toEnsuredOption(option: AcquisitionSourceInfo): AcquisitionSourceOption {
  return {
    public_id: option.public_id,
    name: option.name,
    code: option.public_id,
    is_system: false,
    is_active: option.is_active,
    sort_order: Number.MAX_SAFE_INTEGER,
  }
}

export function useAcquisitionSourceOptions(): UseAcquisitionSourceOptionsReturn {
  const formOptions = ref<AcquisitionSourceOption[]>([])
  const filterOptions = ref<AcquisitionSourceOption[]>([])
  const loading = ref(false)

  const formSelectOptions = computed(() => toAcquisitionSourceSelectOptions(formOptions.value))
  const filterSelectOptions = computed(() => toAcquisitionSourceSelectOptions(filterOptions.value))

  const loadFormOptions = async (): Promise<void> => {
    loading.value = true
    try {
      formOptions.value = await acquisitionSourceApi.listOptions(false)
    } catch (error) {
      handleApiError(error, '获取获客来源')
    } finally {
      loading.value = false
    }
  }

  const loadFilterOptions = async (): Promise<void> => {
    loading.value = true
    try {
      filterOptions.value = await acquisitionSourceApi.listOptions(true)
    } catch (error) {
      handleApiError(error, '获取获客来源')
    } finally {
      loading.value = false
    }
  }

  const ensureOption = (option?: AcquisitionSourceInfo | null): void => {
    if (option === undefined || option === null || option.public_id.trim() === '') return
    if (formOptions.value.some((item) => item.public_id === option.public_id)) return
    formOptions.value = [...formOptions.value, toEnsuredOption(option)]
  }

  return {
    formOptions,
    filterOptions,
    formSelectOptions,
    filterSelectOptions,
    loading,
    loadFormOptions,
    loadFilterOptions,
    ensureOption,
  }
}
