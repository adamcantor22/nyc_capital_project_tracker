import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './story.css'
import Story from './Story.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Story />
  </StrictMode>,
)
