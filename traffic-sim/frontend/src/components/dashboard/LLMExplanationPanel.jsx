import React from 'react';

const LANE_COLORS = {
  north: '#4ade80',
  south: '#60a5fa',
  east: '#f97316',
  west: '#a78bfa',
};

/**
 * LLMExplanationPanel
 *
 * Shows a live feed of Gemini's plain-English explanations for each
 * signal decision. Displayed in the SimulationPage sidebar.
 *
 * Props:
 *   explanationLog — array of { lane, duration, explanation, timestamp }
 */
export default function LLMExplanationPanel({ explanationLog = [] }) {
  return (
    <div className="llm-panel">
      <div className="llm-panel-header">
        <span className="llm-icon">🤖</span>
        <span className="llm-title">AI Signal Reasoning</span>
        <span className="llm-badge">Gemini</span>
      </div>

      {explanationLog.length === 0 ? (
        <div className="llm-empty">
          <p>Explanations will appear here after each lane switch.</p>
        </div>
      ) : (
        <ul className="llm-log">
          {explanationLog.map((entry, idx) => (
            <li key={`${entry.timestamp}-${idx}`} className="llm-entry">
              <div className="llm-entry-header">
                <span
                  className="llm-lane-chip"
                  style={{ background: LANE_COLORS[entry.lane] || '#888' }}
                >
                  {String(entry.lane).toUpperCase()}
                </span>
                <span className="llm-duration">{Number(entry.duration).toFixed(0)}s</span>
                {idx === 0 && <span className="llm-latest-badge">Latest</span>}
              </div>
              <p className="llm-explanation">{entry.explanation}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
