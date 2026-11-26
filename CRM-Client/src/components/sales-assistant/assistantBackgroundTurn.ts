import { toast } from 'vue-sonner'
import { z } from 'zod'
import type { Router } from 'vue-router'
import { assistantApi } from '@/api/assistant'
import type { AssistantTurn } from '@/api/assistant'

// A turn keeps running on the server after the chat unmounts; the layout watches it and
// announces the result once, wherever the user is in the app.
const ARMED_KEY = 'crmwolf.assistant.background-turn'
const NOTIFIED_KEY = 'crmwolf.assistant.notified-turns'
const POLL_MS = 5000
const MAX_READ_FAILURES = 12

const BackgroundTurnSchema = z.object({ targetId: z.string().min(1), turnId: z.string().min(1) })
type BackgroundTurn = z.infer<typeof BackgroundTurnSchema>

const readStored = (key: string): unknown => {
  try {
    return JSON.parse(sessionStorage.getItem(key) ?? 'null')
  } catch {
    return null
  }
}

export const handOffAssistantTurn = (turn: BackgroundTurn): void => {
  sessionStorage.setItem(ARMED_KEY, JSON.stringify(turn))
}

export const reclaimAssistantTurn = (): void => {
  sessionStorage.removeItem(ARMED_KEY)
}

const claimNotice = (turnId: string): boolean => {
  const parsed = z.array(z.string()).safeParse(readStored(NOTIFIED_KEY))
  const notified = parsed.success ? parsed.data : []
  if (notified.includes(turnId)) return false
  sessionStorage.setItem(NOTIFIED_KEY, JSON.stringify([...notified, turnId].slice(-20)))
  return true
}

const announce = (turn: AssistantTurn, router: Router): void => {
  const task = turn.task
  const disposition = task.follow_up_disposition
  const confirmable = task.waiting != null || disposition?.status === 'ACTIVE'
  let title = '销售助手已经处理完'
  let description = confirmable ? '有内容等你确认' : '结果已保存'
  if (turn.status === 'FAILED') {
    title = '这条还没有处理完'
    description = '回到销售助手查看原因'
  } else if (disposition != null) {
    title = `${disposition.activity_kind_label}内容已经整理完`
    if (disposition.status === 'ACTIVE' && disposition.total > 0) {
      description = `${disposition.customer_name} · ${disposition.total} 条跟进记录待确认`
    }
  }
  toast(title, {
    description,
    duration: 10_000,
    action: {
      label: turn.status === 'SUCCEEDED' && confirmable ? '去确认' : '去查看',
      onClick: () => { void router.push('/assistant') }
    }
  })
}

export const watchAssistantBackgroundTurn = (router: Router): (() => void) => {
  let reading = false
  let failures = 0
  let cursor = { turnId: '', seq: 0 }
  const tick = async (): Promise<void> => {
    // The chat page owns its own turn; it reclaims the hand-off when it mounts.
    if (reading || router.currentRoute.value.name === 'SalesAssistant') return
    const armed = BackgroundTurnSchema.safeParse(readStored(ARMED_KEY))
    if (!armed.success) return
    const { targetId, turnId } = armed.data
    if (cursor.turnId !== turnId) cursor = { turnId, seq: 0 }
    reading = true
    try {
      const turn = await assistantApi.getTurn(targetId, turnId, cursor.seq)
      failures = 0
      cursor.seq = Math.max(cursor.seq, ...turn.events.map((event) => event.seq))
      if (turn.status !== 'SUCCEEDED' && turn.status !== 'FAILED') return
      if (BackgroundTurnSchema.safeParse(readStored(ARMED_KEY)).data?.turnId !== turnId) return
      reclaimAssistantTurn()
      if (claimNotice(turnId)) announce(turn, router)
    } catch {
      // Fail closed: stop watching quietly; the chat shows the authoritative result on return.
      failures += 1
      if (failures >= MAX_READ_FAILURES) reclaimAssistantTurn()
    } finally {
      reading = false
    }
  }
  const timer = window.setInterval(() => { void tick() }, POLL_MS)
  return (): void => { window.clearInterval(timer) }
}
