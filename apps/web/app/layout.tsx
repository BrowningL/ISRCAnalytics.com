import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'ISRC Analytics - Music Streaming Analytics Dashboard',
  description: 'Track your music streaming performance across Spotify and Apple Music',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          {/* Fixed black border frame */}
          <div className="fixed inset-0 pointer-events-none border-[18px] border-black z-50" />
          
          {/* Main content */}
          <div className="min-h-screen bg-white dark:bg-gray-900">
            {children}
          </div>
        </Providers>
      </body>
    </html>
  )
}
