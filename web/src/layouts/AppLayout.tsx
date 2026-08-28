import { useEffect, useMemo, useState } from 'react'
import { Avatar, Breadcrumb, Button, Drawer, Dropdown, Layout, Menu } from '@arco-design/web-react'
import {
  IconMenu,
  IconMoonFill,
  IconPoweroff,
  IconSunFill,
  IconUser,
} from '@arco-design/web-react/icon'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { navItemsForRole, type NavItem } from '@/app/nav'
import { useSessionStore } from '@/stores/session'
import { ROLE_LABEL } from '@/utils/format'

const { Sider, Header, Content } = Layout

function Logo() {
  return (
    <div
      style={{
        height: 52,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        fontWeight: 700,
        fontSize: 16,
        letterSpacing: 0.2,
        color: 'var(--brand-500)',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
      }}
    >
      Care-LifeLine
    </div>
  )
}

function MenuPanel({ nav, activeKey, onSelect }: { nav: NavItem[]; activeKey: string; onSelect: (path: string) => void }) {
  return (
    <Menu selectedKeys={[activeKey]} onClickMenuItem={(key) => {
      const item = nav.find((n) => n.key === key)
      if (item) onSelect(item.path)
    }}>
      {nav.map((item) => (
        <Menu.Item key={item.key}>
          <item.icon />
          <span style={{ marginLeft: 8 }}>{item.label}</span>
        </Menu.Item>
      ))}
    </Menu>
  )
}

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const role = useSessionStore((s) => s.role)
  const user = useSessionStore((s) => s.user)
  const theme = useSessionStore((s) => s.theme)
  const setTheme = useSessionStore((s) => s.setTheme)
  const logout = useSessionStore((s) => s.logout)

  const nav = useMemo(() => navItemsForRole(role), [role])
  const activeItem = nav.find((item) => location.pathname.startsWith(item.path)) ?? nav[0]

  const [isMobile, setIsMobile] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)')
    const onChange = () => setIsMobile(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const go = (path: string) => {
    navigate(path)
    setDrawerOpen(false)
  }

  const onUserMenuClick = (key: string) => {
    if (key === 'logout') {
      logout()
      navigate('/login', { replace: true })
    } else if (key === 'settings') {
      navigate('/settings')
    }
  }

  const initial = user?.username?.charAt(0).toUpperCase() ?? '访'

  const userDropdown = (
    <Menu onClickMenuItem={onUserMenuClick}>
      <Menu.Item key="info" disabled>
        <div style={{ lineHeight: 1.5 }}>
          <div style={{ color: 'var(--text-1)', fontWeight: 600 }}>{user?.username ?? '未登录'}</div>
          <div style={{ color: 'var(--text-3)', fontSize: 12 }}>
            {ROLE_LABEL[role]} · {role}
          </div>
        </div>
      </Menu.Item>
      <Menu.Item key="settings">
        <IconUser style={{ marginRight: 8 }} />
        个人设置
      </Menu.Item>
      <Menu.Item key="logout">
        <IconPoweroff style={{ marginRight: 8 }} />
        退出登录
      </Menu.Item>
    </Menu>
  )

  const themeBtn = (
    <Button
      shape="circle"
      type="secondary"
      size="small"
      title={theme === 'dark' ? '切换到亮色' : '切换到暗色'}
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
    >
      {theme === 'dark' ? <IconSunFill /> : <IconMoonFill />}
    </Button>
  )

  const breadcrumb = <Breadcrumb>{activeItem ? <Breadcrumb.Item>{activeItem.label}</Breadcrumb.Item> : null}</Breadcrumb>

  return (
    <Layout style={{ height: '100vh' }}>
      {!isMobile && (
        <Sider width={220} style={{ background: 'var(--bg-card)', borderRight: '1px solid var(--border)' }}>
          <Logo />
          <MenuPanel nav={nav} activeKey={activeItem?.key ?? ''} onSelect={go} />
        </Sider>
      )}

      <Layout>
        <Header
          style={{
            height: 52,
            background: 'var(--bg-card)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 20px',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            {isMobile && (
              <Button shape="circle" type="secondary" size="small" onClick={() => setDrawerOpen(true)}>
                <IconMenu />
              </Button>
            )}
            {breadcrumb}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {themeBtn}
            <Dropdown trigger="click" droplist={userDropdown} position="br">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '2px 4px', borderRadius: 6 }}>
                <Avatar size={28} style={{ backgroundColor: 'var(--brand-500)', fontSize: 13 }}>
                  {initial}
                </Avatar>
                {!isMobile && (
                  <span style={{ fontSize: 13, color: 'var(--text-2)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user?.username ?? ''}
                  </span>
                )}
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ overflow: 'auto', background: 'var(--bg-page)' }}>
          <Outlet />
        </Content>
      </Layout>

      {/* <768px 抽屉式导航 */}
      <Drawer
        width={220}
        title={<Logo />}
        visible={drawerOpen}
        onCancel={() => setDrawerOpen(false)}
        footer={null}
        style={{ background: 'var(--bg-card)' }}
      >
        <MenuPanel nav={nav} activeKey={activeItem?.key ?? ''} onSelect={go} />
      </Drawer>
    </Layout>
  )
}
