export const demoDrivers = {
  lavender: {
    name: 'Driver A · Lavender Racing',
  },
  mint: {
    name: 'Driver B · Mint Motorsport',
  },
  peach: {
    name: 'Driver C · Peach GP',
  },
}

export type DriverId = keyof typeof demoDrivers

export const demoLapTimes = [
  { lap: 1, lavender: 88.2, mint: 88.9, peach: 89.4 },
  { lap: 2, lavender: 87.1, mint: 87.6, peach: 88.3 },
  { lap: 3, lavender: 86.4, mint: 87.0, peach: 87.8 },
  { lap: 4, lavender: 86.9, mint: 86.5, peach: 87.1 },
  { lap: 5, lavender: 85.8, mint: 86.2, peach: 86.6 },
  { lap: 6, lavender: 86.2, mint: 86.8, peach: 87.0 },
]

export const driverColours: Record<DriverId, string> = {
  lavender: '#9476be',
  mint: '#43866b',
  peach: '#bd7652',
}