import type { ComponentType } from 'react'
import {
  IconHome,
  IconMessage,
  IconFile,
  IconDashboard,
  IconUserGroup,
  IconApps,
  IconSettings,
} from '@arco-design/web-react/icon'
import type { Role } from '@/types/contract'

export interface NavItem {
  key: string
  label: string
  path: string
  icon: ComponentType
  /** 可访问角色；缺省表示所有已登录用户可见 */
  roles?: Role[]
}

export const navItems: NavItem[] = [
  { key: 'home', label: '首页', path: '/home', icon: IconHome },
  { key: 'chat', label: '智能问诊', path: '/chat', icon: IconMessage },
  { key: 'report', label: '报告解读', path: '/report', icon: IconFile },
  { key: 'chronic', label: '慢病管理', path: '/chronic', icon: IconDashboard },
  { key: 'workbench', label: '医生工作台', path: '/workbench', icon: IconUserGroup, roles: ['clinician', 'admin'] },
  { key: 'admin', label: '管理后台', path: '/admin', icon: IconApps, roles: ['admin'] },
  { key: 'settings', label: '设置', path: '/settings', icon: IconSettings },
]

/** 按当前角色过滤可见导航项 */
export function navItemsForRole(role: Role): NavItem[] {
  return navItems.filter((item) => !item.roles || item.roles.includes(role))
}
