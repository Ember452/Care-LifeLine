import { Result } from '@arco-design/web-react'
import { useNavigate } from 'react-router-dom'

export default function ForbiddenPage() {
  const navigate = useNavigate()
  return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        status="403"
        title="403"
        subTitle="没有权限访问该页面，请联系管理员"
        extra={
          <a
            onClick={() => navigate('/home')}
            style={{ color: 'var(--brand-500)', cursor: 'pointer' }}
          >
            返回首页
          </a>
        }
      />
    </div>
  )
}
