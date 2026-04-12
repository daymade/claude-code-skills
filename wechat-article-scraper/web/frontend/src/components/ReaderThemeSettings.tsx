import { useState, useEffect } from 'react'
import { Settings, Type, Palette, Moon, Sun, Eye, BookOpen } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

// 主题配置
export type ThemeType = 'light' | 'dark' | 'sepia' | 'ink'
export type FontType = 'system' | 'lxgwwenkai' | 'syst' | 'noto-serif'

interface ReaderSettings {
  theme: ThemeType
  font: FontType
  fontSize: number
  lineHeight: number
  letterSpacing: number
}

const defaultSettings: ReaderSettings = {
  theme: 'light',
  font: 'system',
  fontSize: 18,
  lineHeight: 1.8,
  letterSpacing: 0.05,
}

// 字体配置
const fontOptions: { value: FontType; label: string; fontFamily: string }[] = [
  { value: 'system', label: '系统默认', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
  { value: 'lxgwwenkai', label: '霞鹜文楷', fontFamily: '"LXGW WenKai", "LXGWWenKai", serif' },
  { value: 'syst', label: '思源宋体', fontFamily: '"Source Han Serif CN", "Noto Serif SC", serif' },
  { value: 'noto-serif', label: 'Noto Serif', fontFamily: '"Noto Serif", Georgia, serif' },
]

// 主题配置
const themeOptions: { value: ThemeType; label: string; icon: typeof Sun; className: string }[] = [
  { value: 'light', label: '白天', icon: Sun, className: 'bg-white text-gray-900' },
  { value: 'sepia', label: '护眼', icon: Eye, className: 'bg-[#f5f1e8] text-[#433422]' },
  { value: 'dark', label: '夜间', icon: Moon, className: 'bg-gray-900 text-gray-100' },
  { value: 'ink', label: '墨水屏', icon: BookOpen, className: 'bg-[#e8e6e1] text-[#2c2c2c]' },
]

// 生成CSS变量
export function generateReaderStyles(settings: ReaderSettings): React.CSSProperties {
  const font = fontOptions.find(f => f.value === settings.font) || fontOptions[0]

  const themeColors: Record<ThemeType, { bg: string; text: string; link: string; border: string; highlight: string }> = {
    light: { bg: '#ffffff', text: '#1a1a1a', link: '#3b82f6', border: '#e5e7eb', highlight: '#fef08a' },
    dark: { bg: '#111827', text: '#f3f4f6', link: '#60a5fa', border: '#374151', highlight: '#854d0e' },
    sepia: { bg: '#f5f1e8', text: '#433422', link: '#92400e', border: '#d6d3cd', highlight: '#fde68a' },
    ink: { bg: '#e8e6e1', text: '#2c2c2c', link: '#1a1a1a', border: '#c4c2bc', highlight: '#a8a4a0' },
  }

  const colors = themeColors[settings.theme]

  return {
    '--reader-bg': colors.bg,
    '--reader-text': colors.text,
    '--reader-link': colors.link,
    '--reader-border': colors.border,
    '--reader-highlight': colors.highlight,
    '--reader-font': font.fontFamily,
    '--reader-font-size': `${settings.fontSize}px`,
    '--reader-line-height': settings.lineHeight,
    '--reader-letter-spacing': `${settings.letterSpacing}em`,
  } as React.CSSProperties
}

// 保存设置到localStorage
export function saveReaderSettings(settings: ReaderSettings) {
  localStorage.setItem('reader-settings', JSON.stringify(settings))
}

// 从localStorage读取设置
export function loadReaderSettings(): ReaderSettings {
  try {
    const saved = localStorage.getItem('reader-settings')
    if (saved) {
      return { ...defaultSettings, ...JSON.parse(saved) }
    }
  } catch {
    // ignore
  }
  return defaultSettings
}

interface ReaderThemeSettingsProps {
  onSettingsChange?: (settings: ReaderSettings) => void
}

export default function ReaderThemeSettings({ onSettingsChange }: ReaderThemeSettingsProps) {
  const [settings, setSettings] = useState<ReaderSettings>(loadReaderSettings())
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    saveReaderSettings(settings)
    onSettingsChange?.(settings)
  }, [settings, onSettingsChange])

  const updateSetting = <K extends keyof ReaderSettings>(key: K, value: ReaderSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const currentTheme = themeOptions.find(t => t.value === settings.theme)
  const currentFont = fontOptions.find(f => f.value === settings.font)

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <button
          className="flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-gray-50 transition-colors"
          title="阅读设置"
        >
          <Settings className="h-4 w-4" />
          <span className="hidden sm:inline">阅读设置</span>
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>阅读主题</DropdownMenuLabel>
        <div className="grid grid-cols-4 gap-2 p-2">
          {themeOptions.map((theme) => {
            const Icon = theme.icon
            return (
              <button
                key={theme.value}
                onClick={() => updateSetting('theme', theme.value)}
                className={`flex flex-col items-center gap-1 rounded-lg border p-2 transition-all ${
                  settings.theme === theme.value
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className={`rounded-full p-1.5 ${theme.className}`}>
                  <Icon className="h-4 w-4" />
                </div>
                <span className="text-xs">{theme.label}</span>
              </button>
            )
          })}
        </div>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-2">
          <Type className="h-4 w-4" />
          字体
        </DropdownMenuLabel>
        <div className="p-2">
          <select
            value={settings.font}
            onChange={(e) => updateSetting('font', e.target.value as FontType)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {fontOptions.map((font) => (
              <option key={font.value} value={font.value}>
                {font.label}
              </option>
            ))}
          </select>
        </div>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-2">
          <Palette className="h-4 w-4" />
          排版
        </DropdownMenuLabel>

        <div className="space-y-4 p-2">
          {/* 字号 */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>字号</span>
              <span>{settings.fontSize}px</span>
            </div>
            <input
              type="range"
              min={14}
              max={24}
              step={1}
              value={settings.fontSize}
              onChange={(e) => updateSetting('fontSize', parseInt(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-gray-200 accent-blue-500"
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>小</span>
              <span>大</span>
            </div>
          </div>

          {/* 行高 */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>行高</span>
              <span>{settings.lineHeight}</span>
            </div>
            <input
              type="range"
              min={1.4}
              max={2.4}
              step={0.1}
              value={settings.lineHeight}
              onChange={(e) => updateSetting('lineHeight', parseFloat(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-gray-200 accent-blue-500"
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>紧凑</span>
              <span>宽松</span>
            </div>
          </div>

          {/* 字间距 */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>字间距</span>
              <span>{settings.letterSpacing}em</span>
            </div>
            <input
              type="range"
              min={0}
              max={0.2}
              step={0.01}
              value={settings.letterSpacing}
              onChange={(e) => updateSetting('letterSpacing', parseFloat(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-gray-200 accent-blue-500"
            />
          </div>
        </div>

        <DropdownMenuSeparator />

        <div className="p-2">
          <button
            onClick={() => {
              setSettings(defaultSettings)
            }}
            className="w-full rounded-md bg-gray-100 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 transition-colors"
          >
            恢复默认设置
          </button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export type { ReaderSettings }
export { defaultSettings }
