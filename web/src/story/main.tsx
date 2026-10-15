import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './story.css'
import Story from './Story.tsx'
import { isMapQuery } from '../state/url'

// The map tool lived at the site's root until the story took it: a link carrying the map's own state (?p=, ?view=,
// filters) goes on to /map/ with it; other queries (a tracker's tags) stay on the story.
if (isMapQuery(location.search)) location.replace(`${import.meta.env.BASE_URL}map/${location.search}${location.hash}`)
else createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Story />
  </StrictMode>,
)
