import React, { useEffect, useState } from 'react';
import { fetchSimulationResults } from '../services/api';
import { determineWinner } from '../utils/dashboardUtils';
import MetricCard from '../components/dashboard/MetricCard';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { useParams } from 'react-router-dom';

// DashboardPage component
export default function DashboardPage() {
  // Metrics to compare
  const METRICS = [
    { key: 'avg_wait_time', label: 'Average Wait Time (s)' },
    { key: 'total_vehicles_crossed', label: 'Total Vehicles Crossed' },
    { key: 'co2_estimate', label: 'CO2 Estimate (g)' },
    { key: 'avg_green_utilization', label: 'Green Light Utilization (%)' },
    { key: 'ambulance_avg_wait_time', label: 'Ambulance Wait Time (s)' }
  ];

  // Get sessionId from route params
  const { sessionId } = useParams();

  // Local state for results and error
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  // Fetch results on mount
  useEffect(() => {
    async function fetchResults() {
      try {
        const res = await fetchSimulationResults(sessionId);
        if (res.error) {
          setError(res.error);
        } else {
          setResults(res);
        }
      } catch (err) {
        setError('Failed to fetch results');
      }
    }
    fetchResults();
  }, [sessionId]);

  // Show error if present
  if (error) {
    return <p>Error: {error}</p>;
  }

  // Show loading if results not loaded
  if (!results) {
    return <p>Loading results...</p>;
  }

  // Prepare chart data
  const chartData = METRICS.map(metric => ({
    metric: metric.label,
    Dynamic: results.dynamic[metric.key] ?? null,
    Static: results.static[metric.key] ?? null
  }));

  // Google Fonts
  if (typeof window !== 'undefined') {
    const link1 = document.createElement('link');
    link1.href = 'https://fonts.googleapis.com/css?family=Share+Tech+Mono:400&display=swap';
    link1.rel = 'stylesheet';
    document.head.appendChild(link1);
    const link2 = document.createElement('link');
    link2.href = 'https://fonts.googleapis.com/css?family=Rajdhani:400,700&display=swap';
    link2.rel = 'stylesheet';
    document.head.appendChild(link2);
  }

  // Styles
  const mainBgStyle = {
    minHeight: '100vh',
    background: '#0a0e1a',
    fontFamily: 'Rajdhani, monospace',
    padding: 0,
    margin: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'flex-start',
  };
  const titleStyle = {
    fontFamily: 'Share Tech Mono, monospace',
    fontSize: 36,
    color: '#00f5d4',
    textShadow: '0 0 16px #00f5d4',
    marginTop: 32,
    marginBottom: 24,
    letterSpacing: 4,
    fontWeight: 700,
    textAlign: 'center',
    borderBottom: '4px solid #00f5d4',
    boxShadow: '0 4px 16px -4px #00f5d4',
    paddingBottom: 8,
    width: 600,
    background: 'transparent',
  };
  const tableStyle = {
    width: 600,
    borderCollapse: 'collapse',
    margin: '0 auto',
    fontFamily: 'Rajdhani, monospace',
    fontSize: 20,
    background: 'transparent',
    boxShadow: '0 0 24px 4px #0f1628',
    marginBottom: 32,
  };
  const thStyle = {
    background: '#1a2035',
    color: '#fff',
    fontFamily: 'Share Tech Mono, monospace',
    fontSize: 22,
    padding: '16px 12px',
    borderLeft: '4px solid #00f5d4',
    borderBottom: '2px solid #0f1628',
    textAlign: 'center',
    letterSpacing: 2,
  };
  const rowStyles = [
    { background: '#0f1628' },
    { background: '#0a0e1a' }
  ];
  const tdStyle = {
    padding: '14px 12px',
    textAlign: 'center',
    fontFamily: 'Rajdhani, monospace',
    fontSize: 20,
    color: '#fff',
    borderBottom: '1px solid #1a2035',
  };
  const cyanStyle = { color: '#00f5d4', fontWeight: 700 };
  const orangeStyle = { color: '#f97316', fontWeight: 700 };
  const pillStyle = {
    display: 'inline-block',
    padding: '6px 18px',
    borderRadius: 16,
    fontSize: 18,
    fontFamily: 'Share Tech Mono, monospace',
    fontWeight: 700,
    letterSpacing: 2,
    margin: '0 auto',
    boxShadow: '0 0 8px 2px #00f5d4',
    textAlign: 'center',
  };
  const winnerStyles = {
    dynamic: { ...pillStyle, background: '#00f5d4', color: '#0a0e1a' },
    static: { ...pillStyle, background: '#f97316', color: '#0a0e1a' },
    tie: { ...pillStyle, background: '#444', color: '#fff', boxShadow: 'none' },
    'n/a': { ...pillStyle, background: '#222', color: '#fff', boxShadow: 'none' },
  };

  // Keyframes for glowing border
  const styleSheet = document.createElement('style');
  styleSheet.innerHTML = `
    .dashboard-table th { border-left: 4px solid #00f5d4; }
    .dashboard-table tr:nth-child(even) { background: #0a0e1a; }
    .dashboard-table tr:nth-child(odd) { background: #0f1628; }
  `;
  if (typeof window !== 'undefined' && !document.head.querySelector('style[data-dashboard]')) {
    styleSheet.setAttribute('data-dashboard', 'true');
    document.head.appendChild(styleSheet);
  }

  return (
    <div style={mainBgStyle}>
      <div style={titleStyle}>Simulation Comparison Dashboard</div>
      <table style={tableStyle} className="dashboard-table">
        <thead>
          <tr>
            <th style={thStyle}>Metric</th>
            <th style={thStyle}>Dynamic (RL)</th>
            <th style={thStyle}>Static</th>
            <th style={thStyle}>Winner</th>
          </tr>
        </thead>
        <tbody>
          {METRICS.map((metric, idx) => {
            const dynamicValue = results.dynamic[metric.key] ?? null;
            const staticValue = results.static[metric.key] ?? null;
            const { winner } = determineWinner(metric.key, dynamicValue, staticValue);
            const winnerLabel =
              winner === 'dynamic' ? 'RL Wins 🏆' :
              winner === 'static' ? 'Static Wins' :
              winner === 'tie' ? 'Tie' : 'N/A';
            const winnerStyle = winnerStyles[winner] || winnerStyles['n/a'];
            return (
              <tr key={metric.key} style={rowStyles[idx % 2]}>
                <td style={tdStyle}>{metric.label}</td>
                <td style={{ ...tdStyle, ...cyanStyle }}>{dynamicValue !== null ? dynamicValue.toFixed(2) : '--'}</td>
                <td style={{ ...tdStyle, ...orangeStyle }}>{staticValue !== null ? staticValue.toFixed(2) : '--'}</td>
                <td style={winnerStyle}>{winnerLabel}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ width: 600, background: '#0a0e1a', padding: '24px 0', borderRadius: 16, marginBottom: 48, boxShadow: '0 0 24px 4px #00f5d4' }}>
        <BarChart width={560} height={300} data={chartData} style={{ background: '#0a0e1a' }}>
          <XAxis dataKey="metric" stroke="#fff" style={{ fontFamily: 'Rajdhani, monospace', fontSize: 18 }} />
          <YAxis stroke="#fff" style={{ fontFamily: 'Rajdhani, monospace', fontSize: 18 }} />
          <Tooltip contentStyle={{ background: '#1a2035', color: '#fff', fontFamily: 'Rajdhani, monospace' }} />
          <Legend wrapperStyle={{ color: '#fff', fontFamily: 'Rajdhani, monospace', fontSize: 18 }} />
          <Bar dataKey="Dynamic" fill="#00f5d4" radius={[8,8,0,0]} />
          <Bar dataKey="Static" fill="#f97316" radius={[8,8,0,0]} />
        </BarChart>
      </div>
    </div>
  );
}
