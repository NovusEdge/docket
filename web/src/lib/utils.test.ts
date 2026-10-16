import { expect, test } from 'vitest'
import { cn } from './utils'

test('later tailwind classes win', () => {
  expect(cn('px-2 text-sm', 'px-4')).toBe('text-sm px-4')
})
