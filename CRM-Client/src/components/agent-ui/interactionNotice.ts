/**
 * Per-card submission state owned by the chat column.
 *
 * The server card alone cannot say whether a submit was confirmed not saved (the
 * lost-response check said so) or was already handled elsewhere (stale
 * action id), so the chat records that outcome next to the card it came from.
 */
export type InteractionNotice =
  | { kind: 'failed'; choice: string; clientRequestId: string }
  | { kind: 'expired' }
  | { kind: 'invalid' }
