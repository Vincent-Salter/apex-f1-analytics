import { useEffect, useState } from "react";
import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import "./App.css";
import type { DemoLap, DriverId } from "./data/demoData";

import { formatLapTime } from "./utils/formatLapTime";
import { calculateLapStats } from "./utils/calculateLapStats";

type Session = {
    session_key: number;
    meeting_key: number | null;
    session_name: string | null;
    session_type: string | null;
    circuit_short_name: string | null;
    country_name: string | null;
    session_started_at_utc: string | null;
};

type Driver = {
    session_key: number;
    driver_number: number;
    full_name: string | null;
    name_acronym: string | null;
    team_name: string | null;
    team_colour: string | null;
};

type RealLap = {
    session_key: number;
    driver_number: number;
    lap_number: number;
    lap_started_at_utc: string | null;
    lap_duration_seconds: number | null;
    is_pit_out_lap: boolean | null;
    lap_time_status: "available" | "missing" | "invalid";
    is_eligible_for_timed_stats: boolean;
    delta_to_previous_lap_seconds: number | null
    rolling_5_lap_average_seconds: number | null
    rolling_5_lap_sample_count: number

};

function escapeCsvCell(value: string | number | boolean | null): string {
    if (value === null) return "";

    const text = String(value);

    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function App() {
    // Declare state before using it in calculations.
    const [showAnalytics, setShowAnalytics] = useState(false);
    const [selectedDriver, setSelectedDriver] = useState<DriverId>("lavender");
    const [startLap, setStartLap] = useState(1);
    const [endLap, setEndLap] = useState(6);

    const [laps, setLaps] = useState<DemoLap[]>([]);
    const [lapsStatus, setLapsStatus] = useState<"loading" | "ready" | "error">(
        "loading",
    );

    const [apiStatus, setApiStatus] = useState<
        "checking" | "connected" | "unavailable"
    >("checking");

    const [sessions, setSessions] = useState<Session[]>([]);
    const [selectedSession, setSelectedSession] = useState<number | null>(null);
    const [sessionsStatus, setSessionsStatus] = useState<
        "loading" | "ready" | "empty" | "error"
    >("loading");

    const [realDrivers, setRealDrivers] = useState<Driver[]>([]);
    const [selectedRealDriver, setSelectedRealDriver] = useState<number | null>(
        null,
    );

    const [driversStatus, setDriversStatus] = useState<
        "idle" | "loading" | "ready" | "empty" | "error"
    >("idle");

    const [realLaps, setRealLaps] = useState<RealLap[]>([]);

    const [realLapsStatus, setRealLapsStatus] = useState<
        "idle" | "loading" | "ready" | "empty" | "error"
    >("idle");

    const [realStartLap, setRealStartLap] = useState(1);
    const [realEndLap, setRealEndLap] = useState<number | null>(null);

    useEffect(() => {
        setRealLaps([]);
        setRealStartLap(1);
        setRealEndLap(null);

        if (selectedSession === null || selectedRealDriver === null) {
            setRealLapsStatus("idle");
            return;
        }

        const controller = new AbortController();
        const sessionKey = selectedSession;
        const driverNumber = selectedRealDriver;

        setRealLapsStatus("loading");

        async function loadRealLaps() {
            try {
                const params = new URLSearchParams({
                    driver_number: String(driverNumber),
                });

                const response = await fetch(
                    `http://127.0.0.1:8000/api/sessions/${sessionKey}/laps?${params}`,
                    { signal: controller.signal },
                );

                if (!response.ok) {
                    throw new Error(`Lap request failed: ${response.status}`);
                }

                const data: unknown = await response.json();

                if (!Array.isArray(data)) {
                    throw new Error("Expected a lap array");
                }

                const valid = data.every(
                    (lap) =>
                        lap !== null &&
                        typeof lap === "object" &&
                        lap.session_key === sessionKey &&
                        lap.driver_number === driverNumber &&
                        Number.isInteger(lap.lap_number) &&
                        lap.lap_number > 0 &&
                        (lap.lap_duration_seconds === null ||
                            (typeof lap.lap_duration_seconds === "number" &&
                                Number.isFinite(lap.lap_duration_seconds))) &&
                        ["available", "missing", "invalid"].includes(
                            lap.lap_time_status,
                        ) &&
                        typeof lap.is_eligible_for_timed_stats === "boolean" &&
                        (!lap.is_eligible_for_timed_stats ||
                            (lap.lap_time_status === "available" &&
                                lap.lap_duration_seconds > 0 &&
                                lap.is_pit_out_lap === false)),
                );

                if (!valid) {
                    throw new Error("Invalid lap response");
                }

                if (controller.signal.aborted) return;

                const loadedLaps = (data as RealLap[]).sort(
                    (a, b) => a.lap_number - b.lap_number,
                );

                setRealLaps(loadedLaps);
                setRealStartLap(loadedLaps[0]?.lap_number ?? 1);
                setRealEndLap(
                    loadedLaps[loadedLaps.length - 1]?.lap_number ?? null,
                );

                setRealLapsStatus(loadedLaps.length > 0 ? "ready" : "empty");
            } catch {
                if (!controller.signal.aborted) {
                    setRealLapsStatus("error");
                }
            }
        }

        void loadRealLaps();

        return () => controller.abort();
    }, [selectedSession, selectedRealDriver]);

    useEffect(() => {
        setRealDrivers([]);
        setSelectedRealDriver(null);

        if (selectedSession === null) {
            setDriversStatus("idle");
            return;
        }

        const controller = new AbortController();
        const sessionKey = selectedSession;

        setDriversStatus("loading");

        async function loadDrivers() {
            try {
                const response = await fetch(
                    `http://127.0.0.1:8000/api/sessions/${sessionKey}/drivers`,
                    { signal: controller.signal },
                );

                if (!response.ok) {
                    throw new Error(
                        `Driver request failed: ${response.status}`,
                    );
                }

                const data: unknown = await response.json();

                if (!Array.isArray(data)) {
                    throw new Error("Expected a driver array");
                }

                const valid = data.every(
                    (driver) =>
                        driver !== null &&
                        typeof driver === "object" &&
                        driver.session_key === sessionKey &&
                        Number.isInteger(driver.driver_number) &&
                        driver.driver_number > 0,
                );

                if (!valid) {
                    throw new Error("Invalid driver identifiers");
                }

                if (controller.signal.aborted) return;

                const loadedDrivers = data as Driver[];

                setRealDrivers(loadedDrivers);
                setSelectedRealDriver(loadedDrivers[0]?.driver_number ?? null);
                setDriversStatus(loadedDrivers.length > 0 ? "ready" : "empty");
            } catch {
                if (!controller.signal.aborted) {
                    setDriversStatus("error");
                }
            }
        }

        void loadDrivers();

        return () => controller.abort();
    }, [selectedSession]);

    useEffect(() => {
        const controller = new AbortController();

        async function loadSessions() {
            try {
                const response = await fetch(
                    "http://127.0.0.1:8000/api/sessions",
                    { signal: controller.signal },
                );

                if (!response.ok) {
                    throw new Error(
                        `Session request failed: ${response.status}`,
                    );
                }

                const data: unknown = await response.json();

                if (!Array.isArray(data)) {
                    throw new Error("Expected a session array");
                }

                const valid = data.every(
                    (session) =>
                        session !== null &&
                        typeof session === "object" &&
                        Number.isInteger(session.session_key) &&
                        session.session_key > 0,
                );

                if (!valid) {
                    throw new Error("Invalid session identifiers");
                }

                if (controller.signal.aborted) return;

                const loadedSessions = data as Session[];

                setSessions(loadedSessions);
                setSelectedSession(loadedSessions[0]?.session_key ?? null);
                setSessionsStatus(
                    loadedSessions.length > 0 ? "ready" : "empty",
                );
            } catch {
                if (!controller.signal.aborted) {
                    setSessionsStatus("error");
                }
            }
        }

        void loadSessions();

        return () => controller.abort();
    }, []);

    useEffect(() => {
        const controller = new AbortController();

        async function loadLaps() {
            try {
                const response = await fetch(
                    "http://127.0.0.1:8000/api/demo/laps",
                    { signal: controller.signal },
                );

                if (!response.ok) {
                    throw new Error(`Lap request failed: ${response.status}`);
                }

                const data = await response.json();

                if (
                    data.source !== "fictional-demo" ||
                    !Array.isArray(data.laps) ||
                    data.laps.length === 0
                ) {
                    throw new Error("Unexpected or empty lap response");
                }

                const valid = data.laps.every(
                    (lap: DemoLap) =>
                        lap !== null &&
                        typeof lap === "object" &&
                        Number.isInteger(lap.lap) &&
                        lap.lap > 0 &&
                        [lap.lavender, lap.mint, lap.peach].every(
                            (time) =>
                                typeof time === "number" &&
                                Number.isFinite(time) &&
                                time > 0,
                        ),
                );

                if (!valid) {
                    throw new Error("Invalid lap records");
                }

                const loadedLaps: DemoLap[] = [...data.laps].sort(
                    (a, b) => a.lap - b.lap,
                );

                setLaps(loadedLaps);
                setStartLap(loadedLaps[0].lap);
                setEndLap(loadedLaps[loadedLaps.length - 1].lap);
                setLapsStatus("ready");
            } catch {
                if (!controller.signal.aborted) {
                    setLapsStatus("error");
                }
            }
        }

        void loadLaps();

        return () => controller.abort();
    }, []);

    useEffect(() => {
        const controller = new AbortController();

        async function checkApi() {
            try {
                const response = await fetch(
                    "http://127.0.0.1:8000/api/health",
                    { signal: controller.signal },
                );

                if (!response.ok) {
                    throw new Error(`Health check failed: ${response.status}`);
                }

                const data = await response.json();

                if (data.status !== "ok" || data.service !== "apex-api") {
                    throw new Error("Unexpected health-check response");
                }

                setApiStatus("connected");
            } catch {
                if (!controller.signal.aborted) {
                    setApiStatus("unavailable");
                }
            }
        }

        void checkApi();

        return () => controller.abort();
    }, []);

    // The cards and chart use the same dataset.
    const filteredLaps = laps.filter(
        (lap) => lap.lap >= startLap && lap.lap <= endLap,
    );

    function exportSelectedLaps() {
        const rows = filteredLaps.map((lap) => [
            lap.lap,
            selectedDriver,
            lap[selectedDriver].toFixed(3),
            formatLapTime(lap[selectedDriver]),
        ]);

        const csv = [
            [
                "lap_number",
                "demo_driver_id",
                "lap_time_seconds",
                "lap_time_formatted",
            ],
            ...rows,
        ]
            .map((row) => row.join(","))
            .join("\r\n");

        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);

        const link = document.createElement("a");
        link.href = url;
        link.download = `apex-demo-${selectedDriver}-laps-${startLap}-${endLap}.csv`;

        document.body.appendChild(link);
        link.click();
        link.remove();

        // Give the browser time to start the download before releasing the URL.
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    const realDriver = realDrivers.find(
        (driver) =>
            driver.session_key === selectedSession &&
            driver.driver_number === selectedRealDriver,
    );

    // Match records to the current selection so old data isn't displayed
    // during a driver or session change.
    const currentRealLaps = realLaps.filter(
        (lap) =>
            lap.session_key === selectedSession &&
            lap.driver_number === selectedRealDriver,
    );
    const filteredRealLaps = currentRealLaps.filter(
        (lap) =>
            lap.lap_number >= realStartLap &&
            (realEndLap === null || lap.lap_number <= realEndLap),
    );

    const eligibleRealTimes = filteredRealLaps

        .filter((lap) => lap.is_eligible_for_timed_stats)
        .map((lap) => lap.lap_duration_seconds)
        .filter(
            (time): time is number =>
                typeof time === "number" && Number.isFinite(time) && time > 0,
        );

    const realStats = calculateLapStats(eligibleRealTimes);

    const realChartData = filteredRealLaps.map((lap) => ({
        lap: lap.lap_number,
        lapTime: lap.is_eligible_for_timed_stats
            ? lap.lap_duration_seconds
            : null,
    }));

    const realDataReady =
        realLapsStatus === "ready" && currentRealLaps.length > 0;

    function exportRealLaps() {
        if (!realDataReady || filteredRealLaps.length === 0) return;

        const header = [
            "session_key",
            "driver_number",
            "lap_number",
            "lap_started_at_utc",
            "lap_duration_seconds",
            "lap_time_formatted",
            "is_pit_out_lap",
            "lap_time_status",
            "is_eligible_for_timed_stats",
        ];

        const rows = filteredRealLaps.map((lap) => [
            lap.session_key,
            lap.driver_number,
            lap.lap_number,
            lap.lap_started_at_utc,
            lap.lap_duration_seconds,
            lap.lap_duration_seconds !== null &&
            Number.isFinite(lap.lap_duration_seconds) &&
            lap.lap_duration_seconds > 0
                ? formatLapTime(lap.lap_duration_seconds)
                : null,
            lap.is_pit_out_lap,
            lap.lap_time_status,
            lap.is_eligible_for_timed_stats,
        ]);

        const csv = [header, ...rows]
            .map((row) => row.map(escapeCsvCell).join(","))
            .join("\r\n");

        const blob = new Blob([csv], {
            type: "text/csv;charset=utf-8;",
        });

        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");

        link.href = url;
        link.download =
            `apex-session-${selectedSession}-driver-${selectedRealDriver}` +
            `-laps-${realStartLap}-${realEndLap ?? "all"}.csv`;

        document.body.appendChild(link);
        link.click();
        link.remove();

        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    return (
        <section id="center">
            <div>
                <h1>
                    apex<span className="brand-dot">.</span>
                </h1>

                <p className="tagline">Race data. A fresh perspective.</p>

                <p className="read-the-docs">
                    Your Formula 1 analytics workspace — built one lap at a
                    time.
                </p>
            </div>

            <button
                type="button"
                className="explore-button"
                onClick={() => setShowAnalytics((previous) => !previous)}
                aria-expanded={showAnalytics}
                aria-controls="analytics-panel"
            >
                {showAnalytics
                    ? "Hide race analytics"
                    : "Explore race analytics →"}
            </button>
            <p className={`api-status api-status--${apiStatus}`} role="status">
                {apiStatus === "checking" && "Checking backend connection…"}
                {apiStatus === "connected" && ""}
                {apiStatus === "unavailable" &&
                    "Backend unavailable — check the API server and refresh."}
            </p>

            <section
                id="analytics-panel"
                hidden={!showAnalytics}
                aria-labelledby="analytics-heading"
            >
                <h2 id="analytics-heading">Driver snapshot</h2>
                {lapsStatus === "loading" && (
                  <p>
                  Historical F1 data processed in Databricks and served through
                  PostgreSQL and FastAPI.
                </p>                

                )}

                {lapsStatus === "error" && (
                    <p role="alert">
                        Could not load lap data. Check the backend is running,
                        then refresh this page.
                    </p>
                )}

                {lapsStatus === "ready" && (
                    <p role="status">
                        Laps loaded from the Python API.
                    </p>
                )}

                <div className="driver-filter">
                    <label htmlFor="session-select">
                        Available real sessions
                    </label>

                    <select
                        id="session-select"
                        value={selectedSession ?? ""}
                        disabled={sessionsStatus !== "ready"}
                        onChange={(event) =>
                            setSelectedSession(Number(event.target.value))
                        }
                    >
                        <option value="" disabled>
                            Select a session
                        </option>

                        {sessions.map((session) => (
                            <option
                                key={session.session_key}
                                value={session.session_key}
                            >
                                {session.circuit_short_name ??
                                    session.country_name ??
                                    "Unknown circuit"}
                                {" · "}
                                {session.session_name ?? "Session"}
                                {" · "}
                                {session.session_started_at_utc
                                    ? session.session_started_at_utc.slice(
                                          0,
                                          10,
                                      )
                                    : `ID ${session.session_key}`}
                            </option>
                        ))}
                    </select>

                    <p>
  Historical F1 data processed in Databricks and served through
  PostgreSQL and FastAPI.
</p>


                    <div className="driver-filter">
                        <label htmlFor="real-driver-select">
                            Real session driver
                        </label>

                        <select
                            id="real-driver-select"
                            value={selectedRealDriver ?? ""}
                            disabled={driversStatus !== "ready"}
                            onChange={(event) =>
                                setSelectedRealDriver(
                                    Number(event.target.value),
                                )
                            }
                        >
                            <option value="" disabled>
                                Select a driver
                            </option>

                            {realDrivers.map((driver) => (
                                <option
                                    key={`${driver.session_key}-${driver.driver_number}`}
                                    value={driver.driver_number}
                                >
                                    {driver.driver_number}
                                    {" · "}
                                    {driver.full_name ??
                                        driver.name_acronym ??
                                        "Unknown driver"}
                                    {" · "}
                                    {driver.team_name ?? "Unknown team"}
                                </option>
                            ))}
                        </select>

                        <p role="status">
                            {driversStatus === "idle" &&
                                "Choose a session first."}
                            {driversStatus === "loading" &&
                                "Loading real drivers…"}
                            {driversStatus === "empty" &&
                                "No drivers stored for this session."}
                            {driversStatus === "error" &&
                                "Could not load drivers. Check the backend, then refresh."}
                            {driversStatus === "ready" &&
                                `${realDrivers.length} real drivers loaded. This selection is not connected to the demo chart yet.`}
                        </p>
                    </div>

                    <div className="real-lap-preview">
                        <h3>
                            {realDriver?.full_name ?? "Real driver"} · Session
                            analytics
                        </h3>

                        <p role="status">
                            {realLapsStatus === "idle" &&
                                "Choose a real session and driver."}
                            {realLapsStatus === "loading" &&
                                "Loading real laps…"}
                            {realLapsStatus === "error" &&
                                "Could not load laps. Check the backend, then refresh."}
                            {realLapsStatus === "empty" &&
                                "No laps stored for this driver."}
                            {realDataReady &&
                                `${filteredRealLaps.length} recorded laps in range · ${realStats.lapsAnalysed} eligible timed laps`}
                        </p>
                        <div className="driver-filter">
                            <label htmlFor="real-start-lap">From lap</label>

                            <select
                                id="real-start-lap"
                                value={realStartLap}
                                onChange={(event) => {
                                    const nextStart = Number(
                                        event.target.value,
                                    );

                                    setRealStartLap(nextStart);

                                    if (
                                        realEndLap === null ||
                                        nextStart > realEndLap
                                    ) {
                                        setRealEndLap(nextStart);
                                    }
                                }}
                            >
                                {currentRealLaps.map((lap) => (
                                    <option
                                        key={lap.lap_number}
                                        value={lap.lap_number}
                                    >
                                        Lap {lap.lap_number}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="driver-filter">
                            <label htmlFor="real-end-lap">To lap</label>

                            <select
                                id="real-end-lap"
                                value={realEndLap ?? ""}
                                onChange={(event) =>
                                    setRealEndLap(Number(event.target.value))
                                }
                            >
                                {currentRealLaps
                                    .filter(
                                        (lap) => lap.lap_number >= realStartLap,
                                    )
                                    .map((lap) => (
                                        <option
                                            key={lap.lap_number}
                                            value={lap.lap_number}
                                        >
                                            Lap {lap.lap_number}
                                        </option>
                                    ))}
                            </select>
                        </div>

                        {realDataReady && (
                            <>
                                <div
                                    className="stats-grid"
                                    aria-live="polite"
                                    aria-atomic="true"
                                >
                                    <div className="stat-card stat-card--lavender">
                                        <h3>Fastest eligible lap</h3>
                                        <p className="stat-value">
                                            {realStats.fastestLap === null
                                                ? "—"
                                                : formatLapTime(
                                                      realStats.fastestLap,
                                                  )}
                                        </p>
                                    </div>

                                    <div className="stat-card stat-card--mint">
                                        <h3>Average eligible lap</h3>
                                        <p className="stat-value">
                                            {realStats.averageLap === null
                                                ? "—"
                                                : formatLapTime(
                                                      realStats.averageLap,
                                                  )}
                                        </p>
                                    </div>

                                    <div className="stat-card stat-card--peach">
                                        <h3>Timed laps analysed</h3>
                                        <p className="stat-value">
                                            {realStats.lapsAnalysed}
                                        </p>
                                    </div>
                                </div>

                                <div className="lap-chart">
                                    <h3>Real lap-time trend</h3>
                                    <p className="chart-description">
                                        Missing, invalid and pit-out lap times
                                        are excluded. Gaps represent excluded or
                                        unavailable times.
                                    </p>

                                    <div
                                        className="chart-container"
                                        role="group"
                                        aria-label={`Eligible lap times for ${
                                            realDriver?.full_name ??
                                            "the selected driver"
                                        }`}
                                    >
                                        <ResponsiveContainer
                                            width="100%"
                                            height="100%"
                                        >
                                            <LineChart
                                                data={realChartData}
                                                margin={{
                                                    top: 16,
                                                    right: 16,
                                                    bottom: 16,
                                                    left: 0,
                                                }}
                                                accessibilityLayer
                                            >
                                                <CartesianGrid
                                                    stroke="#e9e4ee"
                                                    strokeDasharray="4 4"
                                                />

                                                <XAxis
                                                    dataKey="lap"
                                                    type="number"
                                                    domain={[
                                                        "dataMin",
                                                        "dataMax",
                                                    ]}
                                                    allowDecimals={false}
                                                    tick={{
                                                        fill: "#757589",
                                                        fontSize: 12,
                                                    }}
                                                    tickLine={false}
                                                    axisLine={false}
                                                    label={{
                                                        value: "Lap number",
                                                        position:
                                                            "insideBottom",
                                                        offset: -10,
                                                        fill: "#757589",
                                                    }}
                                                />

                                                <YAxis
                                                    domain={["auto", "auto"]}
                                                    tick={{
                                                        fill: "#757589",
                                                        fontSize: 12,
                                                    }}
                                                    tickLine={false}
                                                    axisLine={false}
                                                    width={65}
                                                    tickFormatter={(value) =>
                                                        `${Number(value).toFixed(0)}s`
                                                    }
                                                />

                                                <Tooltip
                                                    labelFormatter={(label) =>
                                                        `Lap ${label}`
                                                    }
                                                    formatter={(value) => [
                                                        formatLapTime(
                                                            Number(value),
                                                        ),
                                                        "Lap time",
                                                    ]}
                                                    contentStyle={{
                                                        background: "#ffffff",
                                                        border: "1px solid #e9e4ee",
                                                        borderRadius: "12px",
                                                    }}
                                                />

                                                <Line
                                                    type="linear"
                                                    dataKey="lapTime"
                                                    stroke="#9476be"
                                                    strokeWidth={2}
                                                    dot={{ r: 2 }}
                                                    activeDot={{ r: 5 }}
                                                    connectNulls={false}
                                                    isAnimationActive={false}
                                                />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                                <div className="lap-details">
  <h3>Lap-by-lap analysis</h3>
  <p className="chart-description">
    Negative delta means faster; positive means slower.
    Rolling averages use eligible laps from the current and preceding
    four lap numbers.
  </p>

  <div className="lap-table-scroll">
    <table className="lap-table">
      <caption className="chart-description">
        Selected laps for {realDriver?.full_name ?? 'the selected driver'}
      </caption>

      <thead>
        <tr>
          <th scope="col">Lap</th>
          <th scope="col">Recorded time</th>
          <th scope="col">Δ vs previous lap</th>
          <th scope="col">5-lap average</th>
          <th scope="col">Samples</th>
          <th scope="col">Timed stats</th>
        </tr>
      </thead>

      <tbody>
        {filteredRealLaps.map((lap) => {
          const delta = lap.delta_to_previous_lap_seconds

          return (
            <tr key={`${lap.session_key}-${lap.driver_number}-${lap.lap_number}`}>
              <th scope="row">{lap.lap_number}</th>

              <td>
                {lap.lap_time_status === 'available' &&
                lap.lap_duration_seconds !== null
                  ? formatLapTime(lap.lap_duration_seconds)
                  : '—'}
              </td>

              <td>
                {delta === null ? (
                  '—'
                ) : (
                  <span
                    className={
                      delta < 0
                        ? 'lap-delta--faster'
                        : delta > 0
                          ? 'lap-delta--slower'
                          : ''
                    }
                  >
                    {delta > 0 ? '+' : ''}
                    {delta.toFixed(3)}s
                  </span>
                )}
              </td>

              <td>
                {lap.rolling_5_lap_average_seconds === null
                  ? '—'
                  : formatLapTime(lap.rolling_5_lap_average_seconds)}
              </td>

              <td>{lap.rolling_5_lap_sample_count}/5</td>

              <td>
                {lap.is_eligible_for_timed_stats
                  ? 'Included'
                  : lap.lap_time_status === 'missing'
                    ? 'Missing time'
                    : lap.lap_time_status === 'invalid'
                      ? 'Invalid time'
                      : 'Excluded'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  </div>
</div>

                            </>
                        )}
                    </div>
                </div>

                <button
                    type="button"
                    className="export-button"
                    onClick={exportRealLaps}
                    disabled={!realDataReady || filteredRealLaps.length === 0}
                >
                    Export real selected laps ↓
                </button>
            </section>
        </section>
    );
}

export default App;
