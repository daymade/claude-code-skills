import type { Metadata, Viewport } from 'next';
import './globals.css';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: '#0ea5e9',
};

export const metadata: Metadata = {
  title: '微信文章助手 - WeChat Article Scraper',
  description: '微信公众号文章抓取、分析与协作平台',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: '微信文章助手',
  },
  icons: {
    icon: [
      { url: '/icons/icon-72x72.png', sizes: '72x72' },
      { url: '/icons/icon-96x96.png', sizes: '96x96' },
      { url: '/icons/icon-128x128.png', sizes: '128x128' },
      { url: '/icons/icon-144x144.png', sizes: '144x144' },
      { url: '/icons/icon-152x152.png', sizes: '152x152' },
      { url: '/icons/icon-192x192.png', sizes: '192x192' },
      { url: '/icons/icon-384x384.png', sizes: '384x384' },
      { url: '/icons/icon-512x512.png', sizes: '512x512' },
    ],
    apple: [
      { url: '/icons/icon-152x152.png', sizes: '152x152' },
      { url: '/icons/icon-180x180.png', sizes: '180x180' },
    ],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <head>
        <meta name="application-name" content="微信文章助手" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="文章助手" />
        <meta name="format-detection" content="telephone=no" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="msapplication-TileColor" content="#0ea5e9" />
        <meta name="msapplication-tap-highlight" content="no" />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
