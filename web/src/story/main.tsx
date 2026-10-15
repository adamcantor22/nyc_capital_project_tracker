import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './story.css'
import Story from './Story.tsx'

// The map tool lived at the site's root until the story took it: a link carrying the map's own state (?p=, ?view=,
// filters) goes on to /map/ with it.
if (location.search.length > 1) location.replace(`${import.meta.env.BASE_URL}map/${location.search}${location.hash}`)
else createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Story />
  </StrictMode>,
)
