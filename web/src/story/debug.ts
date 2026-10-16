/** Switches for testing the story map on a phone, from the page's query string (?dbg=nopts,nostroke): each changes
 * one thing about the plate 1 dots so a crash can be pinned to it. Unknown switches do nothing.
 * - nopts: no dots at all
 * - sortkey: dots sorted by MapLibre at draw time (circle-sort-key), as before, instead of in the data
 * - nostroke: dots without their white outline
 * - few: only points holding $1M or more
 * - z12: the dots' source tiled to zoom 12 instead of 10 */
export const DEBUG: ReadonlySet<string> = (() => {
  try { return new Set((new URLSearchParams(location.search).get('dbg') ?? '').split(',').filter(Boolean)) } catch { return new Set<string>() }
})()
