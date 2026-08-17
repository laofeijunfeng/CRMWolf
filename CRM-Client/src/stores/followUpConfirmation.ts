import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  followUpConfirmationApi,
  type FollowUpConfirmationResolveResponse
} from '@/api/followUpTask'

export const useFollowUpConfirmationStore = defineStore('followUpConfirmation', () => {
  const pendingCount = ref(0)
  const resolvingCaseId = ref<string | null>(null)
  const postResolveRefreshError = ref<string | null>(null)


  const fetchPendingCount = async (): Promise<void> => {
    pendingCount.value = await followUpConfirmationApi.getPendingCount()
  }

  const resolveCase = async (caseId: string, replyText: string): Promise<FollowUpConfirmationResolveResponse> => {
    resolvingCaseId.value = caseId
    postResolveRefreshError.value = null
    try {
      const response = await followUpConfirmationApi.resolve(caseId, { reply_text: replyText })
      if (response.decision.resolved) {
        pendingCount.value = Math.max(0, pendingCount.value - 1)
      }
      try {
        await fetchPendingCount()
      } catch {
        postResolveRefreshError.value = '确认已处理，但待确认数量刷新失败，请稍后重试。'
      }
      return response
    } finally {
      resolvingCaseId.value = null
    }
  }

  return {
    pendingCount,
    resolvingCaseId,
    postResolveRefreshError,
    fetchPendingCount,
    resolveCase,
  }
})
