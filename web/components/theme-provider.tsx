'use client'

import * as React from 'react'

type Theme = 'light' | 'dark' | 'system'

export type ThemeProviderProps = React.PropsWithChildren<{
  attribute?: 'class' | 'data-theme' | string
  defaultTheme?: Theme
  enableSystem?: boolean
  forcedTheme?: Theme
  storageKey?: string
}>

type ThemeProviderState = {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  systemTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
}

const initialState: ThemeProviderState = {
  theme: 'system',
  resolvedTheme: 'light',
  systemTheme: 'light',
  setTheme: () => null,
}

const ThemeProviderContext = React.createContext<ThemeProviderState>(initialState)

function getSystemTheme() {
  if (typeof window === 'undefined') {
    return 'light'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({
  children,
  attribute = 'class',
  defaultTheme = 'system',
  enableSystem = true,
  forcedTheme,
  storageKey = 'vite-ui-theme',
}: ThemeProviderProps) {
  const [theme, setThemeState] = React.useState<Theme>(() => {
    if (forcedTheme) {
      return forcedTheme
    }

    if (typeof window === 'undefined') {
      return defaultTheme
    }

    return (window.localStorage.getItem(storageKey) as Theme | null) ?? defaultTheme
  })
  const [systemTheme, setSystemTheme] = React.useState<'light' | 'dark'>(getSystemTheme)

  React.useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const updateSystemTheme = () => setSystemTheme(media.matches ? 'dark' : 'light')

    updateSystemTheme()
    media.addEventListener('change', updateSystemTheme)

    return () => media.removeEventListener('change', updateSystemTheme)
  }, [])

  React.useEffect(() => {
    if (forcedTheme) {
      setThemeState(forcedTheme)
    }
  }, [forcedTheme])

  const resolvedTheme = theme === 'system' && enableSystem ? systemTheme : theme === 'dark' ? 'dark' : 'light'

  React.useEffect(() => {
    const root = window.document.documentElement

    if (attribute === 'class') {
      root.classList.remove('light', 'dark')
      root.classList.add(resolvedTheme)
    } else {
      root.setAttribute(attribute, resolvedTheme)
    }
  }, [attribute, resolvedTheme])

  const value = React.useMemo<ThemeProviderState>(
    () => ({
      theme,
      resolvedTheme,
      systemTheme,
      setTheme: (nextTheme) => {
        window.localStorage.setItem(storageKey, nextTheme)
        setThemeState(nextTheme)
      },
    }),
    [resolvedTheme, storageKey, systemTheme, theme],
  )

  return <ThemeProviderContext.Provider value={value}>{children}</ThemeProviderContext.Provider>
}

export const useTheme = () => {
  const context = React.useContext(ThemeProviderContext)

  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }

  return context
}
