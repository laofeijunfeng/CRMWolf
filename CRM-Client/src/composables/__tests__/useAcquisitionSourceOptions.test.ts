import { beforeEach, describe, expect, it, vi } from 'vitest'
import { acquisitionSourceApi } from '@/api/acquisition-source'
import { useAcquisitionSourceOptions } from '../useAcquisitionSourceOptions'

vi.mock('@/api/acquisition-source', () => ({
  acquisitionSourceApi: {
    listOptions: vi.fn(),
  },
}))

const mockedListOptions = vi.mocked(acquisitionSourceApi.listOptions)

const activeReferral = {
  public_id: 'acq_referral',
  name: '客户推荐',
  code: 'REFERRAL',
  is_system: true,
  is_active: true,
  sort_order: 20,
}

const inactiveExhibition = {
  public_id: 'acq_exhibition',
  name: '展会',
  code: 'EXHIBITION',
  is_system: true,
  is_active: false,
  sort_order: 60,
}

describe('useAcquisitionSourceOptions', () => {
  beforeEach(() => {
    mockedListOptions.mockReset()
  })

  it('loads form options without inactive sources', async () => {
    mockedListOptions.mockResolvedValue([activeReferral])

    const { loadFormOptions, formSelectOptions } = useAcquisitionSourceOptions()
    await loadFormOptions()

    expect(mockedListOptions).toHaveBeenCalledWith(false)
    expect(formSelectOptions.value).toEqual([
      { value: 'acq_referral', label: '客户推荐' },
    ])
  })

  it('loads filter options including inactive sources', async () => {
    mockedListOptions.mockResolvedValue([activeReferral, inactiveExhibition])

    const { loadFilterOptions, filterSelectOptions } = useAcquisitionSourceOptions()
    await loadFilterOptions()

    expect(mockedListOptions).toHaveBeenCalledWith(true)
    expect(filterSelectOptions.value).toEqual([
      { value: 'acq_referral', label: '客户推荐' },
      { value: 'acq_exhibition', label: '展会' },
    ])
  })

  it('keeps the current inactive source visible when editing a record', async () => {
    mockedListOptions.mockResolvedValue([activeReferral])

    const { loadFormOptions, ensureOption, formSelectOptions } = useAcquisitionSourceOptions()
    await loadFormOptions()

    ensureOption({
      public_id: 'acq_exhibition',
      name: '展会',
      is_active: false,
    })

    expect(formSelectOptions.value).toEqual([
      { value: 'acq_referral', label: '客户推荐' },
      { value: 'acq_exhibition', label: '展会' },
    ])
  })
})
