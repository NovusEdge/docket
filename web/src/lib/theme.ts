import { useEffect, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
const KEY = 'docket-theme'

function read(): ThemeChoice {
  try {
    const t = localStorage.getItem(KEY)
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(read)
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)')
    const apply = () => document.documentElement.classList.toggle('dark', choice === 'dark' || (choice === 'system' && media.matches))
    apply()
    media.addEventListener('change', apply)
    try {
      localStorage.setItem(KEY, choice)
    } catch {
      // Storage is unavailable in private windows; the choice lasts for this page.
    }
    return () => media.removeEventListener('change', apply)
  }, [choice])
  return [choice, setChoice]
}
