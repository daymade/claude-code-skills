import { Outlet, NavLink } from 'react-router-dom'
import { LayoutDashboard, FileText, ListTodo, Search, Github } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function Layout() {
  const navItems = [
    { to: '/', icon: LayoutDashboard, label: '仪表板' },
    { to: '/articles', icon: FileText, label: '文章' },
    { to: '/queues', icon: ListTodo, label: '任务队列' },
    { to: '/search', icon: Search, label: '搜索' },
  ]

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r bg-card">
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center border-b px-6">
            <h1 className="text-xl font-bold text-primary">
              微信文章抓取
            </h1>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 p-4">
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

      {/* Main content */}
      <main className="ml-64 min-h-screen">
        <div className="container mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
