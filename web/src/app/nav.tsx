import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import {
  IconHome,
  IconMessage,
  IconFile,
  IconDashboard,
  IconUserGroup,
  IconApps,
  IconSettings,
} from '@arco-design/web-react/icon'

export interface NavItem {
  key: string
  label: string
  path: string
  icon: ComponentType
  element: LazyExoticComponent<ComponentType>
}

export const navItems: NavItem[] = [
  { key: 'home', label: '首页', path: '/home', icon: IconHome, element: lazy(() => import('@/pages/HomePage')) },
  { key: 'chat', label: '智能问诊', path: '/chat', icon: IconMessage, element: lazy(() => import('@/pages/ChatPage')) },
  { key: 'report', label: '报告解读', path: '/report', icon: IconFile, element: lazy(() => import('@/pages/ReportPage')) },
  { key: 'chronic', label: '慢病管理', path: '/chronic', icon: IconDashboard, element: lazy(() => import('@/pages/ChronicPage')) },
  { key: 'workbench', label: '医生工作台', path: '/workbench', icon: IconUserGroup, element: lazy(() => import('@/pages/WorkbenchPage')) },
  { key: 'admin', label: '管理后台', path: '/admin', icon: IconApps, element: lazy(() => import('@/pages/AdminPage')) },
  { key: 'settings', label: '设置', path: '/settings', icon: IconSettings, element: lazy(() => import('@/pages/SettingsPage')) },
]
