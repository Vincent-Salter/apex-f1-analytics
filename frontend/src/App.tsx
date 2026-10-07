import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'
import {
  demoDrivers,
  demoLapTimes,
  driverColours,
} from './data/demoData'
import type { DriverId } from './data/demoData'

import { formatLapTime } from './utils/formatLapTime'
import { calculateLapStats } from './utils/calculateLapStats'




function App() {
  // Declare state before using it in calculations.
  const [showAnalytics, setShowAnalytics] = useState(false)
  const [selectedDriver, setSelectedDriver] = useState<DriverId>('lavender')
  const [startLap, setStartLap] = useState(1)
  const [endLap, setEndLap] = useState(6)


  const driver = demoDrivers[selectedDriver]

  // The cards and chart use the same dataset.
  const filteredLaps = demoLapTimes.filter(
    (lap) => lap.lap >= startLap && lap.lap <= endLap
  )
  
  const lapTimes = filteredLaps.map((lap) => lap[selectedDriver])
  
  const { fastestLap, averageLap, lapsAnalysed } =
  calculateLapStats(lapTimes)

    function exportSelectedLaps() {
      const rows = filteredLaps.map((lap) => [
        lap.lap,
        selectedDriver,
        lap[selectedDriver].toFixed(3),
        formatLapTime(lap[selectedDriver]),
      ])
    
      const csv = [
        ['lap_number', 'demo_driver_id', 'lap_time_seconds', 'lap_time_formatted'],
        ...rows,
      ]
        .map((row) => row.join(','))
        .join('\r\n')
    
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
    
      const link = document.createElement('a')
      link.href = url
      link.download = `apex-demo-${selectedDriver}-laps-${startLap}-${endLap}.csv`
    
      document.body.appendChild(link)
      link.click()
      link.remove()
    
      // Give the browser time to start the download before releasing the URL.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
    
  
  return (
    <section id="center">
      <div>
        <h1>
          apex<span className="brand-dot">.</span>
        </h1>

        <p className="tagline">Race data. A fresh perspective.</p>

        <p className="read-the-docs">
          Your Formula 1 analytics workspace — built one lap at a time.
        </p>
      </div>

      <button
        type="button"
        className="explore-button"
        onClick={() => setShowAnalytics((previous) => !previous)}
        aria-expanded={showAnalytics}
        aria-controls="analytics-panel"
      >
        {showAnalytics ? 'Hide race analytics' : 'Explore race analytics →'}
      </button>

      <section
        id="analytics-panel"
        hidden={!showAnalytics}
        aria-labelledby="analytics-heading"
      >
        <h2 id="analytics-heading">Driver snapshot</h2>
        <p>Fictional sample session — not real race results.</p>

        <div className="driver-filter">
          <label htmlFor="driver-select">Choose a demo driver</label>

          <select
            id="driver-select"
            value={selectedDriver}
            onChange={(event) =>
              setSelectedDriver(event.target.value as DriverId)
            }
          >
            <option value="lavender">{demoDrivers.lavender.name}</option>
            <option value="mint">{demoDrivers.mint.name}</option>
            <option value="peach">{demoDrivers.peach.name}</option>
          </select>
        </div>
        <div className="driver-filter">
  <label htmlFor="start-lap">From lap</label>
  <select
    id="start-lap"
    value={startLap}
    onChange={(event) => {
      const nextStartLap = Number(event.target.value)
      setStartLap(nextStartLap)

      if (nextStartLap > endLap) {
        setEndLap(nextStartLap)
      }
    }}
  >
    {demoLapTimes.map((lap) => (
      <option key={lap.lap} value={lap.lap}>
        Lap {lap.lap}
      </option>
    ))}
  </select>
</div>

<div className="driver-filter">
  <label htmlFor="end-lap">To lap</label>
  <select
    id="end-lap"
    value={endLap}
    onChange={(event) => setEndLap(Number(event.target.value))}
  >
    {demoLapTimes
      .filter((lap) => lap.lap >= startLap)
      .map((lap) => (
        <option key={lap.lap} value={lap.lap}>
          Lap {lap.lap}
        </option>
      ))}
  </select>
</div>

<button
  type="button"
  className="export-button"
  onClick={exportSelectedLaps}
>
  Export selected laps ↓
</button>

        <div className="stats-grid" aria-live="polite" aria-atomic="true">
          <div className="stat-card stat-card--lavender">
            <h3>Fastest lap</h3>
            <p className="stat-value">
  {fastestLap === null ? '—' : formatLapTime(fastestLap)}
</p>

            <p className="stat-hint">
              Fastest timed lap in the demo session
            </p>
          </div>

          <div className="stat-card stat-card--mint">
            <h3>Average lap time</h3>
            <p className="stat-value">
  {averageLap === null ? '—' : formatLapTime(averageLap)}
</p>

            <p className="stat-hint">Across demo timed laps</p>
          </div>

          <div className="stat-card stat-card--peach">
            <h3>Laps analysed</h3>
            <p className="stat-value">{lapsAnalysed}</p>
            <p className="stat-hint">Sample dataset only</p>
          </div>
        </div>

        {/* Keep the chart outside the three-column card grid. */}
        <div className="lap-chart">
          <h3>Lap-time trend</h3>
          <p className="chart-description">
  Fictional sample data · laps {startLap}–{endLap} · the chart and
  summary cards use the same selected laps.
</p>


          {/* Mount the chart only when its panel is visible. */}
          {showAnalytics && (
            <div
              className="chart-container"
              role="group"
              aria-label={`Example lap times for ${driver.name}`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={filteredLaps}
                  margin={{ top: 16, right: 16, bottom: 16, left: 0 }}
                  accessibilityLayer
                >
                  <CartesianGrid
                    stroke="#e9e4ee"
                    strokeDasharray="4 4"
                  />

                  <XAxis
                    dataKey="lap"
                    tick={{ fill: '#757589', fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                    label={{
                      value: 'Lap number',
                      position: 'insideBottom',
                      offset: -10,
                      fill: '#757589',
                    }}
                  />

                  <YAxis
                    domain={[84, 90]}
                    tick={{ fill: '#757589', fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                    width={55}
                    tickFormatter={(value) => `${value}s`}
                  />

                  <Tooltip
                    labelFormatter={(label) => `Lap ${label}`}
                    formatter={(value) => [
                      `${Number(value).toFixed(3)} seconds`,
                      'Lap time',
                    ]}
                    contentStyle={{
                      background: '#ffffff',
                      border: '1px solid #e9e4ee',
                      borderRadius: '12px',
                    }}
                  />

                  <Line
                    type="linear"
                    dataKey={selectedDriver}
                    name={driver.name}
                    stroke={driverColours[selectedDriver]}
                    strokeWidth={3}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </section>
    </section>
  )
}

export default App
