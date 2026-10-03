import { describe, expect, it } from 'vitest'
import type { Project } from '../data/types'
import { buildIndex, matchPlaces, type Place } from './index'

const p = (id: string, title: string, over: Partial<Project> = {}): Project => ({
  id, program: 'nyc_capital', title, agencies: ['DDC'], sponsor: null, borough: 'Queens', district: 401, districts: [401],
  neighborhood: null, theme: 'Parks', subtheme: null, phase: null, phaseGroup: 'Active', status: 'current', budget: 1, spend: 0,
  spendPct: null, budgetChange: null, budgetCity: null, budgetNonCity: null, forecastCompletion: null, hasSchedule: false,
  firstReported: 202305, lastReported: 202605, tier: 'A', lon: 0, lat: 0, onMap: true, approximate: false, matchedTo: null,
  sourceFlag: null, outsideNyc: null, extra: { pids: [1234] }, ...over,
})

describe('search', () => {
  const idx = buildIndex([
    p('HWK1669A', 'Reconstruction of Hillside Avenue'),
    p('P-4SUNRSE', 'Sunrise Stables Acquisition', { matchedTo: 'Sunrise Playground', borough: 'Brooklyn', districts: [305] }),
  ])
  it('finds by ID, PID, title prefix and place', () => {
    expect(idx.search('HWK1669A')[0].id).toBe('HWK1669A')
    expect(idx.search('1234').length).toBe(2)
    expect(idx.search('hillsi')[0].id).toBe('HWK1669A')
    expect(idx.search('brooklyn 5').map((r) => r.id)).toEqual(['P-4SUNRSE'])
  })
  it('matches neighborhood names by word prefix', () => {
    const places = ['Astoria (Central)', 'Long Island City-Hunters Point'].map(
      (label): Place => ({ kind: 'neighborhood', label, detail: 'Queens', lon: 0, lat: 0, zoom: 14 }),
    )
    expect(matchPlaces(places, 'hunt').map((x) => x.label)).toEqual(['Long Island City-Hunters Point'])
    expect(matchPlaces(places, 'a')).toEqual([])
  })
})
