import { defineStore } from 'pinia'
import { ref } from 'vue'
import { logger } from '@/utils/logger'
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

  const refreshPendingCountAfterResolve = (): void => {
    void fetchPendingCount().catch((error: unknown) => {
      postResolveRefreshError.value = '确认已处理，但待确认数量刷新失败，请稍后重试。'
      logger.warn('[FollowUpConfirmationStore]', 'pendingCountRefresh:failedAfterResolve', {
        errorMessage: error instanceof Error ? error.message : String(error),
      })
    })
  }

  const resolveCase = async (caseId: string, replyText: string): Promise<FollowUpConfirmationResolveResponse> => {
    resolvingCaseId.value = caseId
    postResolveRefreshError.value = null
    try {
      const response = await followUpConfirmationApi.resolve(caseId, { reply_text: replyText })
      if (response.decision.resolved) {
        pendingCount.value = Math.max(0, pendingCount.value - 1)
        refreshPendingCountAfterResolve()
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
