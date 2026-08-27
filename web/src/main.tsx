import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { ConfigProvider } from '@arco-design/web-react'
import '@arco-design/web-react/dist/css/arco.css'
import './index.css'
import { router } from './app/router.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      theme={{ primaryColor: '#3370FF' }}
      componentConfig={{ Button: { shape: 'round' } }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  </StrictMode>,
)
