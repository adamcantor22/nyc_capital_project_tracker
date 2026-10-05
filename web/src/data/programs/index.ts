import type { ProgramAdapter } from '../types'
import { nycCapital } from './nycCapital'
import { sca } from './sca'

/** Adding a capital program: write an adapter and list it here; the manifest says which are exported. */
export const adapters: Record<string, ProgramAdapter> = {
  [nycCapital.id]: nycCapital,
  [sca.id]: sca,
}
