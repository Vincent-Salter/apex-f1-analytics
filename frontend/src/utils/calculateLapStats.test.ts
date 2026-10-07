import { describe, expect, it } from 'vitest'
import { calculateLapStats } from './calculateLapStats'

describe('calculateLapStats', () => {
  it('calculates statistics for multiple laps', () => {
    const stats = calculateLapStats([86.4, 86.9, 85.8])

    expect(stats.fastestLap).toBe(85.8)
    expect(stats.averageLap).toBeCloseTo(86.366666, 5)
    expect(stats.lapsAnalysed).toBe(3)
  })

  it('handles a single lap', () => {
    expect(calculateLapStats([85.8])).toEqual({
      fastestLap: 85.8,
      averageLap: 85.8,
      lapsAnalysed: 1,
    })
  })

  it('handles an empty dataset', () => {
    expect(calculateLapStats([])).toEqual({
      fastestLap: null,
      averageLap: null,
      lapsAnalysed: 0,
    })
  })

  it('does not change the original array', () => {
    const laps = [86.4, 86.9, 85.8]

    calculateLapStats(laps)

    expect(laps).toEqual([86.4, 86.9, 85.8])
  })
})
