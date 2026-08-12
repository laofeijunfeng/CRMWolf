import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  followUpConfirmationApi,
  type FollowUpConfirmationCase,
  type FollowUpConfirmationResolveResponse
} from '@/api/followUpTask'

export const useFollowUpConfirmationStore = defineStore('followUpConfirmation', () => {
  const items = ref<FollowUpConfirmationCase[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const pendingCount = ref(0)
  const loading = ref(false)
  const resolvingCaseId = ref<string | null>(null)
  const loadError = ref<string | null>(null)
  const postResolveRefreshError = ref<string | null>(null)

  const hasPendingCases = computed(() => pendingCount.value > 0)
  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

  const fetchPendingCases = async (requestedPage = page.value): Promise<void> => {
    loading.value = true
    loadError.value = null
    try {
      const normalizedPage = Math.max(1, requestedPage)
      const response = await followUpConfirmationApi.list({
        skip: (normalizedPage - 1) * pageSize.value,
        limit: pageSize.value
      })
      items.value = response.items
      total.value = response.total
      pendingCount.value = response.total
      page.value = normalizedPage
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '待确认事项加载失败'
      throw error
    } finally {
      loading.value = false
    }
  }

  const fetchPendingCount = async (): Promise<void> => {
    pendingCount.value = await followUpConfirmationApi.getPendingCount()
  }

  const resolveCase = async (caseId: string, replyText: string): Promise<FollowUpConfirmationResolveResponse> => {
    resolvingCaseId.value = caseId
    postResolveRefreshError.value = null
    try {
      const response = await followUpConfirmationApi.resolve(caseId, { reply_text: replyText })
      const targetPage = items.value.length === 1 && page.value > 1 ? page.value - 1 : page.value
      if (response.decision.resolved) {
        items.value = items.value.filter(item => item.public_id !== caseId)
        total.value = Math.max(0, total.value - 1)
        pendingCount.value = Math.max(0, pendingCount.value - 1)
        page.value = targetPage
      }
      const refreshResults = await Promise.allSettled([
        fetchPendingCases(targetPage),
        fetchPendingCount()
      ])
      if (refreshResults.some(result => result.status === 'rejected')) {
        loadError.value = null
        postResolveRefreshError.value = '确认已处理，但列表状态刷新失败，请手动刷新。'
      }
      return response
    } finally {
      resolvingCaseId.value = null
    }
  }

  const goToPage = async (targetPage: number): Promise<void> => {
    const normalizedPage = Math.min(Math.max(1, targetPage), totalPages.value)
    if (normalizedPage === page.value) return
    await fetchPendingCases(normalizedPage)
  }

  const refresh = async (): Promise<void> => {
    await Promise.all([fetchPendingCases(page.value), fetchPendingCount()])
  }

  return {
    items,
    total,
    page,
    pageSize,
    totalPages,
    pendingCount,
    loading,
    resolvingCaseId,
    loadError,
    postResolveRefreshError,
    hasPendingCases,
    fetchPendingCases,
    fetchPendingCount,
    resolveCase,
    goToPage,
    refresh
  }
})
