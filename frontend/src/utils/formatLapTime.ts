export function formatLapTime(seconds: number): string {
  const totalMilliseconds = Math.round(seconds * 1000)
  const minutes = Math.floor(totalMilliseconds / 60000)
  const remainingMilliseconds = totalMilliseconds % 60000

  const wholeSeconds = Math.floor(remainingMilliseconds / 1000)
  const milliseconds = remainingMilliseconds % 1000

  return `${minutes}:${String(wholeSeconds).padStart(2, '0')}.${String(
    milliseconds
  ).padStart(3, '0')}`
}
