import { describe, expect, it } from 'vitest'
import { moneyTicks } from './chartkit'

describe('moneyTicks', () => {
  it('picks round steps that cover the data', () => {
    expect(moneyTicks(45e6).map((t) => t.label)).toEqual(['$0', '$25M', '$50M'])
    expect(moneyTicks(1.52e6).map((t) => t.label)).toEqual(['$0', '$1M', '$2M'])
    const t = moneyTicks(9.8e8)
    expect(t.at(-1)!.v).toBeGreaterThanOrEqual(9.8e8)
  })
})
