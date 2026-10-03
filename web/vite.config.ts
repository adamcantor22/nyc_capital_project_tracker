import { createReadStream, existsSync, statSync } from 'node:fs'
import { join, normalize } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const EXPORT = join(__dirname, '..', 'data', 'export')

/** In dev, serve the pipeline's export (data/export) at /data/ so no data is copied into web/.
 * Production builds get it from the deploy workflow, which unpacks the export into dist/data/. */
function exportData(): Plugin {
  return {
    name: 'export-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const path = normalize(join(EXPORT, decodeURIComponent((req.url ?? '').split('?')[0])))
        if (!path.startsWith(EXPORT) || !existsSync(path) || !statSync(path).isFile()) return next()
        res.setHeader('Content-Type', path.endsWith('json') ? 'application/json' : 'application/octet-stream')
        createReadStream(path).pipe(res)
      })
    },
  }
}

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/nyc_capital_project_tracker/' : '/',
  plugins: [react(), exportData()],
  // MapLibre builds its worker from its own bundle; Vite's dependency pre-bundling breaks that in dev.
  optimizeDeps: { exclude: ['maplibre-gl'] },
}))
