import { useState, useEffect } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, FileText, ListTodo, Search, Rss, Bell, Github, Highlighter, Sparkles, History, Menu, X, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import OfflineIndicator from './OfflineIndicator'
import KeyboardShortcutsHelp, { useKeyboardShortcuts } from './KeyboardShortcuts'

export default function Layout() {
  const { showHelp, setShowHelp } = useKeyboardShortcuts()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const location = useLocation()

  // Detect mobile screen size
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768)
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Close mobile menu when route changes
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [location.pathname])

  const navItems = [
    { to: '/', icon: LayoutDashboard, label: '仪表板', mobileLabel: '首页' },
    { to: '/articles', icon: FileText, label: '文章', mobileLabel: '文章' },
    { to: '/highlights', icon: Highlighter, label: '高亮', mobileLabel: '高亮' },
    { to: '/daily-review', icon: Sparkles, label: '每日复习', mobileLabel: '复习' },
    { to: '/search', icon: Search, label: '搜索', mobileLabel: '搜索' },
    { to: '/subscriptions', icon: Rss, label: '订阅管理', mobileLabel: '订阅' },
    { to: '/notifications', icon: Bell, label: '通知管理', mobileLabel: '通知' },
    { to: '/queues', icon: ListTodo, label: '任务队列', mobileLabel: '队列' },
    { to: '/history-crawl', icon: History, label: '历史采集', mobileLabel: '采集' },
  ]

  const mobileNavItems = navItems.slice(0, 5) // Show only first 5 items in bottom nav

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop Sidebar */}
      <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r bg-card hidden md:block">
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center border-b px-6">
            <h1 className="text-xl font-bold text-primary">
              微信文章抓取
            </h1>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 p-4 overflow-y-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Footer */}
          <div className="border-t p-4">
            <a
              href="https://github.com/daymade/claude-code-skills"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </div>
        </div>
      </aside>

      {/* Mobile Header */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-40 bg-card border-b">
        <div className="flex items-center justify-between px-4 h-14">
          <h1 className="text-lg font-semibold text-primary">微信文章抓取</h1>
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="p-2 rounded-lg hover:bg-accent"
          >
            {isMobileMenuOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
        </div>
      </header>

      {/* Mobile Menu Dropdown */}
      {isMobileMenuOpen && (
        <div className="md:hidden fixed top-14 left-0 right-0 z-30 bg-card border-b shadow-lg">
          <nav className="py-2 max-h-[calc(100vh-3.5rem)] overflow-y-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors',
                    isActive
                      ? 'text-primary bg-primary/10'
                      : 'text-muted-foreground hover:bg-accent'
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      {/* Offline Indicator */}
      <OfflineIndicator />

      {/* Main content */}
      <main className={cn(
        "min-h-screen transition-all",
        "md:ml-64 pt-14 md:pt-0 pb-16 md:pb-0"
      )}>
        <div className="container mx-auto p-4 md:p-8">
          <Outlet />
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-card border-t">
        <div className="flex items-center justify-around">
          {mobileNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex flex-col items-center gap-1 px-3 py-2 text-xs font-medium transition-colors',
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground'
                )
              }
            >
              <item.icon className="h-5 w-5" />
              <span>{item.mobileLabel}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Keyboard Shortcuts Help */}
      <KeyboardShortcutsHelp isOpen={showHelp} onClose={() => setShowHelp(false)} />
    </div>
  )
}
