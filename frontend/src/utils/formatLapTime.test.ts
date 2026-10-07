import { describe, expect, it } from 'vitest'
import { formatLapTime } from './formatLapTime'

describe('formatLapTime', () => {
  it('formats seconds as minutes, seconds and milliseconds', () => {
    expect(formatLapTime(85.8)).toBe('1:25.800')
  })

  it('pads single-digit seconds and milliseconds with zeros', () => {
    expect(formatLapTime(61.005)).toBe('1:01.005')
  })

  it('formats a time below one minute', () => {
    expect(formatLapTime(9.25)).toBe('0:09.250')
  })

  it('rounds to the nearest millisecond', () => {
    expect(formatLapTime(86.766666)).toBe('1:26.767')
  })

  it('handles rounding into the next minute', () => {
    expect(formatLapTime(59.9996)).toBe('1:00.000')
  })

  it('formats zero seconds', () => {
    expect(formatLapTime(0)).toBe('0:00.000')
  })
})
