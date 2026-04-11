import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'

import Layout from '@/components/Layout'
import Dashboard from '@/pages/Dashboard'
import Articles from '@/pages/Articles'
import ArticleDetail from '@/pages/ArticleDetail'
import Queues from '@/pages/Queues'
import QueueDetail from '@/pages/QueueDetail'
import Search from '@/pages/Search'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'articles', element: <Articles /> },
      { path: 'articles/:id', element: <ArticleDetail /> },
      { path: 'queues', element: <Queues /> },
      { path: 'queues/:id', element: <QueueDetail /> },
      { path: 'search', element: <Search /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
)
