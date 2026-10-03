import { describe, expect, it } from 'vitest'
import { parse, serialize } from './url'

describe('url state', () => {
  it('round-trips filters and selection, omitting defaults', () => {
    const s = { filters: { status: ['current'], theme: ['Parks', 'Health'], tier: [] }, selected: 'HWK1669A' }
    const q = serialize(s)
    expect(q).toBe('?theme=Parks%7CHealth&p=HWK1669A')
    expect(parse(q)).toEqual({ filters: { status: ['current'], theme: ['Parks', 'Health'] }, selected: 'HWK1669A', view: null, measure: null })
  })
  it('keeps an explicitly cleared default and ignores unknown keys', () => {
    expect(serialize({ filters: { status: [] }, selected: null })).toBe('?status=')
    expect(parse('?status=&bogus=1').filters).toEqual({ status: [] })
  })
})

describe('area view in the url', () => {
  it('keeps level and non-default measure', () => {
    expect(serialize({ filters: {}, selected: null, view: 'districts', measure: 'federal' })).toBe('?view=districts&m=federal')
    expect(parse('?view=boroughs').view).toBe('boroughs')
  })
})
