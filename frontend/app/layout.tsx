import './globals.css'
import React from 'react'
import { Navbar } from './components/Navbar'
import { ToastProvider } from './components/ToastProvider'

export const metadata = { title: 'Doc Q&A', description: 'RAG Document QA' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-gray-950 dark:via-gray-900 dark:to-gray-800 text-gray-900 dark:text-gray-100 antialiased">
        <ToastProvider>
          <Navbar />
          <div className="pt-2 pb-8">{children}</div>
        </ToastProvider>
      </body>
    </html>
  )
}
