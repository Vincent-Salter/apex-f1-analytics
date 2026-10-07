export function calculateLapStats(lapTimes: number[]) {
    if (lapTimes.length === 0) {
      return {
        fastestLap: null,
        averageLap: null,
        lapsAnalysed: 0,
      }
    }
  
    return {
      fastestLap: Math.min(...lapTimes),
      averageLap:
        lapTimes.reduce((total, time) => total + time, 0) / lapTimes.length,
      lapsAnalysed: lapTimes.length,
    }
  }
  