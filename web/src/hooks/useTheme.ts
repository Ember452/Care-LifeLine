import { useEffect } from 'react'
import { useSessionStore } from '@/stores/session'

export interface ChartPalette {
  brand: string
  success: string
  danger: string
  warning: string
  grid: string
  axis: string
  text: string
  tooltipBg: string
  tooltipBorder: string
}

/** 图表配色按主题取，保证暗色下也可读（Arco 暗色色板） */
const PALETTES: Record<'light' | 'dark', ChartPalette> = {
  light: {
    brand: '#3370FF',
    success: '#00B42A',
    danger: '#F53F3F',
    warning: '#FF7D00',
    grid: '#E5E6EB',
    axis: '#86909C',
    text: '#4E5969',
    tooltipBg: '#FFFFFF',
    tooltipBorder: '#E5E6EB',
  },
  dark: {
    brand: '#4C88FF',
    success: '#23C343',
    danger: '#F76965',
    warning: '#FF9A2E',
    grid: '#333436',
    axis: '#86909C',
    text: '#C9CDD4',
    tooltipBg: '#232324',
    tooltipBorder: '#3A3B3D',
  },
}

/**
 * 把主题同步到 DOM：Arco 读 body[arco-theme]，自绘组件读 html[data-theme]。
 * 返回当前模式下对应的图表配色，供 Recharts 使用。
 */
export function useTheme(): { theme: 'light' | 'dark'; palette: ChartPalette } {
  const theme = useSessionStore((s) => s.theme)

  useEffect(() => {
    document.body.setAttribute('arco-theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.style.colorScheme = theme
  }, [theme])

  return { theme, palette: PALETTES[theme] }
}
