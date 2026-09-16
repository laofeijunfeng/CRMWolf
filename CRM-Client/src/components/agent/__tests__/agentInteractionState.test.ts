import { describe, expect, it } from 'vitest'

import { unlockInteractionActionId } from '../agentInteractionState'

describe('unlockInteractionActionId', () => {
  it('removes the submitted action after a failed confirmation', () => {
    const locked = new Set(['act_confirm_lead'])
    expect(unlockInteractionActionId(locked, 'act_confirm_lead')).toEqual(new Set())
  })

  it('leaves unrelated locks in place', () => {
    const locked = new Set(['act_confirm_lead', 'act_other'])
    expect(unlockInteractionActionId(locked, 'act_confirm_lead')).toEqual(new Set(['act_other']))
  })
})
