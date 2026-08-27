import { Result } from '@arco-design/web-react'
import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <Result
        status="404"
        title="404"
        subTitle="页面不存在"
        extra={
          <Link to="/home" style={{ color: 'var(--brand-500)' }}>
            返回首页
          </Link>
        }
      />
    </div>
  )
}
