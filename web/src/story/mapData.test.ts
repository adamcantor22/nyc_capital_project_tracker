import { describe, expect, it } from 'vitest'
import { sendData } from './mapData'
import type { Props } from './StoryMap'

function fakeMap() {
  const setData: Record<string, number> = {}
  const visible: Record<string, string> = {}
  const map = {
    getSource: (id: string) => ({ setData: () => { setData[id] = (setData[id] ?? 0) + 1 } }),
    setLayoutProperty: (id: string, _k: string, v: string) => { visible[id] = v },
  }
  return { map: map as never, setData, visible }
}

describe('story map data', () => {
  it('sends the points once and hides them between plates instead of clearing them', () => {
    const { map, setData, visible } = fakeMap()
    const sent = new Map<string, unknown[]>()
    const groups = [{ lon: -73.9, lat: 40.7, projects: 1, budget: 1e6, byProgram: { nyc_capital: 1e6 }, lead: 'nyc_capital' }]
    const stations = [{ lon: -73.86, lat: 40.84, place: 'Parkchester', residents: 50000 }]
    const base = { groups, rail: null, districts: null, spots: [] } as unknown as Props
    sendData(map, { ...base, view: { kind: 'builders', focus: null } }, sent)
    expect(visible.pts).toBe('visible')
    sendData(map, { ...base, view: { kind: 'stations', stations, focus: null } }, sent)
    expect(visible.pts).toBe('none')
    expect(visible.stations).toBe('visible')
    sendData(map, { ...base, view: { kind: 'builders', focus: null } }, sent)
    expect(visible.pts).toBe('visible')
    expect(visible.stations).toBe('none')
    expect(setData.pts).toBe(1)
    expect(setData.stations).toBe(1)
  })
})
