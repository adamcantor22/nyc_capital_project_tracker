import { useSyncExternalStore } from 'react'

const query = typeof matchMedia === 'function' ? matchMedia('(max-width: 760px)') : null

/** True at phone widths, where the rail becomes a pull-up sheet over a full-screen map. */
export function usePhone(): boolean {
  return useSyncExternalStore(
    (cb) => {
      query?.addEventListener('change', cb)
      return () => query?.removeEventListener('change', cb)
    },
    () => !!query?.matches,
  )
}
