import type { Map as MlMap } from 'maplibre-gl'
import { OTHER_COLOR, THEME_SLOTS } from './themes'

const INK = '#1d2230'
const SCALE = 2 // draw at 2x for crisp markers

/** Tier B marker: a tinted disc hatched at 45° with an ink ring (the hatch says "approximate"). */
function hatchedDisc(color: string, size = 22): ImageData {
  const px = size * SCALE
  const c = document.createElement('canvas')
  c.width = c.height = px
  const g = c.getContext('2d')!
  const r = px / 2 - 2 * SCALE
  g.save()
  g.beginPath()
  g.arc(px / 2, px / 2, r, 0, Math.PI * 2)
  g.fillStyle = '#ffffff'
  g.fill()
  g.clip()
  g.strokeStyle = color
  g.lineWidth = 2.2 * SCALE
  for (let x = -px; x < px * 2; x += 5 * SCALE) {
    g.beginPath()
    g.moveTo(x, px)
    g.lineTo(x + px, 0)
    g.stroke()
  }
  g.restore()
  g.beginPath()
  g.arc(px / 2, px / 2, r, 0, Math.PI * 2)
  g.strokeStyle = color
  g.lineWidth = 1.6 * SCALE
  g.stroke()
  g.beginPath()
  g.arc(px / 2, px / 2, r + 1.1 * SCALE, 0, Math.PI * 2)
  g.strokeStyle = INK
  g.lineWidth = 0.9 * SCALE
  g.stroke()
  return g.getImageData(0, 0, px, px)
}

export function addPatterns(map: MlMap) {
  for (const { color } of [...THEME_SLOTS, { color: OTHER_COLOR }]) {
    map.addImage(`b-${color}`, hatchedDisc(color), { pixelRatio: SCALE })
  }
}
