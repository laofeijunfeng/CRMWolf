import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import operationLogApi, {
  type ResourceType,
  type EventType,
  type OperationLog,
  type GetResourceLogsParams
} from '@/api/operationLog'

export interface TimelineFilters {
  eventTypes: EventType[]
  dateRange: 'today' | 'week' | 'month' | 'custom' | null
  customStartDate: string | null
  customEndDate: string | null
  keyword: string
}

export interface UseTimelineOptions {
  resourceType?: ResourceType
  resourceId?: number
  useMyLogs?: boolean
  pageSize?: number
}

export function useTimeline(options: UseTimelineOptions = {}) {
  const {
    resourceType,
    resourceId,
    useMyLogs = false,
    pageSize = 20
  } = options

  const logs = ref<OperationLog[]>([])
  const loading = ref(false)
  const total = ref(0)
  const currentPage = ref(1)
  const hasMore = ref(true)

  const filters = ref<TimelineFilters>({
    eventTypes: [],
    dateRange: null,
    customStartDate: null,
    customEndDate: null,
    keyword: ''
  })

  const filteredLogs = computed(() => {
    let result = logs.value

    if (filters.value.keyword) {
      const keyword = filters.value.keyword.toLowerCase()
      result = result.filter(log => 
        log.event_type.toLowerCase().includes(keyword) ||
        log.remark?.toLowerCase().includes(keyword) ||
        JSON.stringify(log.content).toLowerCase().includes(keyword)
      )
    }

    if (filters.value.eventTypes.length > 0) {
      result = result.filter(log => filters.value.eventTypes.includes(log.event_type))
    }

    if (filters.value.dateRange && filters.value.dateRange !== 'custom') {
      const now = new Date()
      let startDate: Date

      switch (filters.value.dateRange) {
        case 'today':
          startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate())
          break
        case 'week':
          startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
          break
        case 'month':
          startDate = new Date(now.getFullYear(), now.getMonth(), 1)
          break
        default:
          return result
      }

      result = result.filter(log => {
        const logDate = new Date(log.operated_at)
        return logDate >= startDate
      })
    }

    if (filters.value.dateRange === 'custom' && filters.value.customStartDate && filters.value.customEndDate) {
      const startDate = new Date(filters.value.customStartDate)
      const endDate = new Date(filters.value.customEndDate)
      endDate.setHours(23, 59, 59)

      result = result.filter(log => {
        const logDate = new Date(log.operated_at)
        return logDate >= startDate && logDate <= endDate
      })
    }

    return result
  })

  const fetchLogs = async (page = 1, append = false) => {
    if (loading.value) return

    loading.value = true
    try {
      let response

      if (useMyLogs) {
        response = await operationLogApi.getMyLogs({
          page_no: page,
          page_size: pageSize
        })
      } else if (resourceType && resourceId) {
        const params: GetResourceLogsParams = {
          primary_resource_type: resourceType,
          primary_resource_id: resourceId,
          page_no: page,
          page_size: pageSize
        }

        if (filters.value.eventTypes.length > 0) {
          params.event_types = filters.value.eventTypes
        }

        response = await operationLogApi.getResourceLogs(params)
      } else {
        throw new Error('Either resourceType+resourceId or useMyLogs must be provided')
      }

      const newData = response.list

      if (append) {
        logs.value = [...logs.value, ...newData]
      } else {
        logs.value = newData
      }

      total.value = response.total
      currentPage.value = page
      hasMore.value = logs.value.length < total.value
    } catch (error: unknown) {
      console.error('获取操作记录失败', error)
      ElMessage.error(error.response?.data?.detail || '获取操作记录失败')
    } finally {
      loading.value = false
    }
  }

  const loadMore = () => {
    if (!hasMore.value || loading.value) return
    fetchLogs(currentPage.value + 1, true)
  }

  const refresh = () => {
    currentPage.value = 1
    hasMore.value = true
    fetchLogs(1, false)
  }

  const updateFilters = (newFilters: Partial<TimelineFilters>) => {
    filters.value = { ...filters.value, ...newFilters }
    refresh()
  }

  const resetFilters = () => {
    filters.value = {
      eventTypes: [],
      dateRange: null,
      customStartDate: null,
      customEndDate: null,
      keyword: ''
    }
    refresh()
  }

  return {
    logs: filteredLogs,
    allLogs: logs,
    loading,
    total,
    currentPage,
    hasMore,
    filters,
    fetchLogs,
    loadMore,
    refresh,
    updateFilters,
    resetFilters
  }
}
