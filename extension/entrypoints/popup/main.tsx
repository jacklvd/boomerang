import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { browser } from 'wxt/browser'

import { App } from '@/src/ui/app'
import '@/src/ui/styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('popup root is missing from index.html')

createRoot(root).render(
  <StrictMode>
    <App tabs={browser.tabs} scripting={browser.scripting} />
  </StrictMode>,
)
