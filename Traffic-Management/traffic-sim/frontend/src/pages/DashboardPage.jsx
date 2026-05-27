import React, { useEffect, useState } from 'react';
import { fetchSimulationResults } from '../services/api';
import { determineWinner } from '../utils/dashboardUtils';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from 'recharts';
import { useLocation, useParams } from 'react-router-dom';
import AppSidebar from '../components/layout/AppSidebar';
import Card from '../components/ui/Card';
import Section from '../components/ui/Section';
import './dashboard.css';

export default function DashboardPage() {
  const METRICS = [
    { key: 'avg_wait_time', label: 'Average Wait Time (s)' },
    { key: 'total_vehicles_crossed', label: 'Total Vehicles Crossed' },
    { key: 'co2_estimate', label: 'CO2 Estimate (g)' },
    { key: 'avg_green_utilization', label: 'Green Light Utilization (%)' },
    { key: 'ambulance_avg_wait_time', label: 'Ambulance Wait Time (s)' }
  ];

  const params = useParams();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search || '');
  const rlSessionId = searchParams.get('rl_id') || null;
  const staticSessionId = searchParams.get('static_id') || null;
  const sessionId = params.sessionId || params.id || null;
  const effectiveSessionId = rlSessionId || sessionId;
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState('Loading results...');

  useEffect(() => {
    if (!effectiveSessionId) {
      setError('Missing session id');
      return;
    }

    async function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function fetchResults() {
      setError(null);
      setStatusMessage('Finalizing results...');

      let resultsReady = false;

      for (let attempt = 1; attempt <= 10; attempt += 1) {
        try {
          const res = rlSessionId && staticSessionId
            ? await fetchSimulationResults({ rlId: rlSessionId, staticId: staticSessionId })
            : await fetchSimulationResults(effectiveSessionId);
          if (res && !res.error) {
            console.log('API RESULT:', res);
            console.log('API RESULT dynamic.total_vehicles_crossed:', res?.dynamic?.total_vehicles_crossed);
            console.log('API RESULT static.total_vehicles_crossed:', res?.static?.total_vehicles_crossed);
            console.log('DASHBOARD SESSION IDS:', {
              effectiveSessionId,
              rlSessionId,
              staticSessionId,
              routeId: params?.id || null
            });
            setResults(res);
            resultsReady = true;
            break;
          }
        } catch (err) {
          console.warn('Results not ready yet:', err);
        }

        if (attempt < 10) {
          await sleep(1000);
        }
      }

      if (!resultsReady) {
        setError('Results not ready, please retry');
        setStatusMessage('Loading results...');
        return;
      }
    }
    fetchResults();
  }, [effectiveSessionId, rlSessionId, staticSessionId]);

  if (error) {
    return (
      <div className="dashboard">
        <AppSidebar />
        <main className="content">
          <div className="status-banner status-warning">Error: {error}</div>
        </main>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="dashboard">
        <AppSidebar />
        <main className="content">
          <header className="content-header">
            <h1>Simulation Comparison Dashboard</h1>
            <p>{statusMessage}</p>
          </header>
          <section className="kpi-grid">
            {Array.from({ length: 4 }).map((_, idx) => (
              <Card key={`loading-kpi-${idx}`} className="kpi-card skeleton-card">
                <div className="skeleton-line skeleton-line-short" />
                <div className="skeleton-line skeleton-line-wide" />
              </Card>
            ))}
          </section>
          <Section>
            <div className="skeleton-line skeleton-line-short" />
            <div className="skeleton-block" />
          </Section>
        </main>
      </div>
    );
  }

  const chartData = METRICS.map(metric => ({
    metric: metric.label,
    Dynamic: results.dynamic[metric.key] ?? null,
    Static: results.static[metric.key] ?? null
  }));
  const wins = results?.benchmark?.wins || { dynamic: 0, static: 0, tie: 0, 'n/a': 0 };
  const uplift = results?.benchmark?.uplift || {};
  const chartHasData = chartData.some((item) => item.Dynamic !== null || item.Static !== null);
  const signalLog = Array.isArray(results?.actual_signal_log) ? results.actual_signal_log : [];

  const kpiCards = [
    {
      key: 'avg_wait_time',
      label: 'Average Wait Time',
      value: typeof results?.dynamic?.avg_wait_time === 'number' ? `${results.dynamic.avg_wait_time.toFixed(2)}s` : '--'
    },
    {
      key: 'total_vehicles_crossed',
      label: 'Vehicles Crossed',
      value: typeof results?.dynamic?.total_vehicles_crossed === 'number' ? results.dynamic.total_vehicles_crossed.toFixed(0) : '--'
    },
    {
      key: 'avg_green_utilization',
      label: 'Green Utilization',
      value: typeof results?.dynamic?.avg_green_utilization === 'number' ? `${results.dynamic.avg_green_utilization.toFixed(2)}%` : '--'
    },
    {
      key: 'ambulance_avg_wait_time',
      label: 'Ambulance Wait',
      value: typeof results?.dynamic?.ambulance_avg_wait_time === 'number' ? `${results.dynamic.ambulance_avg_wait_time.toFixed(2)}s` : '--'
    }
  ];

  return (
    <div className="dashboard">
      <AppSidebar />

      <main className="content">
        <header className="content-header">
          <h1>Simulation Comparison Dashboard</h1>
          <p>Compare Adaptive Traffic Management and static traffic control performance with session-level diagnostics.</p>
        </header>

        <section className="kpi-grid">
          {kpiCards.map((item) => (
            <Card key={item.label} className="kpi-card">
              <p>{item.label}</p>
              <h2>{item.value}</h2>
              <div className={`kpi-trend ${typeof uplift?.[item.key]?.uplift_pct === 'number' && uplift[item.key].uplift_pct < 0 ? 'kpi-trend-down' : 'kpi-trend-up'}`}>
                {typeof uplift?.[item.key]?.uplift_pct === 'number'
                  ? `${uplift[item.key].uplift_pct >= 0 ? '↑' : '↓'} ${Math.abs(uplift[item.key].uplift_pct).toFixed(2)}%`
                  : 'No trend data'}
              </div>
            </Card>
          ))}
        </section>

        <Section
          title="Performance Comparison"
          actions={(
            <div className="benchmark-summary">
              <span>Adaptive Wins: {wins.dynamic}</span>
              <span>Static Wins: {wins.static}</span>
              <span>Ties: {wins.tie}</span>
            </div>
          )}
        >
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="align-right">Dynamic (Adaptive)</th>
                <th className="align-right">Static</th>
                <th>Winner</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map((metric) => {
                const dynamicValue = results.dynamic[metric.key] ?? null;
                const staticValue = results.static[metric.key] ?? null;
                const { winner } = determineWinner(metric.key, dynamicValue, staticValue);
                const winnerLabel = winner === 'dynamic' ? 'Adaptive Wins' : winner === 'static' ? 'Static Wins' : winner === 'tie' ? 'Tie' : 'N/A';
                const winnerClass = winner === 'n/a' ? 'na' : (winner || 'na');
                const upliftPct = uplift?.[metric.key]?.uplift_pct;
                const upliftText = typeof upliftPct === 'number' ? `${upliftPct >= 0 ? '+' : ''}${upliftPct.toFixed(2)}%` : 'N/A';
                return (
                  <tr key={metric.key}>
                    <td>{metric.label}</td>
                    <td className="metric-dynamic align-right">{dynamicValue !== null ? dynamicValue.toFixed(2) : '--'}</td>
                    <td className="metric-static align-right">{staticValue !== null ? staticValue.toFixed(2) : '--'}</td>
                    <td>
                      <span className={`winner-pill winner-${winnerClass}`}>
                        {winnerLabel} ({upliftText})
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Section>

        <Section title="Benchmark Metrics">
          <div className="chart-wrap chart-wrap-large">
            {chartHasData ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="metric" stroke="var(--muted)" />
                  <YAxis stroke="var(--muted)" />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Dynamic" fill="var(--primary)" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="Static" fill="var(--muted)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">No data available</div>
            )}
          </div>
        </Section>

        <Section title="Actual Signal Durations">
          {signalLog.length === 0 ? (
            <p className="muted-text">No actual signal duration data available for this session.</p>
          ) : (
            <div className="table-wrap">
              <table className="decision-table">
                <thead>
                  <tr>
                    <th>Lane</th>
                    <th className="align-right">Duration (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {signalLog.map((item, index) => (
                    <tr key={index}>
                      <td>{String(item.lane).toUpperCase()}</td>
                      <td className="align-right">{Number(item.duration).toFixed(1)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

      </main>
    </div>
  );
}
