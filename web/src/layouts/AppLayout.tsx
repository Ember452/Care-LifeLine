import { Layout, Menu, Breadcrumb, Avatar, Dropdown } from '@arco-design/web-react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { navItems } from '@/app/nav'

const { Sider, Header, Content } = Layout

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  const active = navItems.find((item) => location.pathname.startsWith(item.path)) ?? navItems[0]

  const onMenuClick = (key: string) => {
    const target = navItems.find((item) => item.key === key)
    if (target) navigate(target.path)
  }

  const onUserMenuClick = (key: string) => {
    if (key === 'logout') navigate('/login')
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={220} style={{ background: 'var(--bg-card)' }} breakpoint="lg">
        <div
          style={{
            height: 52,
            display: 'flex',
            alignItems: 'center',
            paddingLeft: 20,
            fontWeight: 600,
            fontSize: 16,
            color: 'var(--brand-500)',
          }}
        >
          Care-LifeLine
        </div>
        <Menu selectedKeys={[active.key]} onClickMenuItem={onMenuClick}>
          {navItems.map((item) => (
            <Menu.Item key={item.key}>
              <item.icon />
              <span style={{ marginLeft: 8 }}>{item.label}</span>
            </Menu.Item>
          ))}
        </Menu>
      </Sider>
      <Layout>
        <Header
          style={{
            height: 52,
            background: 'var(--bg-card)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 20px',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Breadcrumb>
            <Breadcrumb.Item>{active.label}</Breadcrumb.Item>
          </Breadcrumb>
          <Dropdown
            trigger="click"
            droplist={
              <Menu onClickMenuItem={onUserMenuClick}>
                <Menu.Item key="logout">退出登录</Menu.Item>
              </Menu>
            }
          >
            <Avatar size={28} style={{ backgroundColor: 'var(--brand-500)', cursor: 'pointer' }}>
              演
            </Avatar>
          </Dropdown>
        </Header>
        <Content style={{ overflow: 'auto', background: 'var(--bg-page)' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
