import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/bodoni-moda/opsz-italic.css'
import '@fontsource-variable/martian-mono/wdth.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ErrorNet } from './components/Safety'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorNet>
      <App />
    </ErrorNet>
  </StrictMode>,
)
