import React, { useState } from 'react';
import Button from '../ui/Button';
import { applyConfig } from '../../services/signalApi';

/**
 * LLMConfigBox
 *
 * Natural language configuration input for the signal controller.
 * User types a plain English command → Gemini parses it → params returned
 * → onConfigUpdate called with the new params object.
 *
 * Props:
 *   onConfigUpdate(params) — called with { max_green, min_green, yellow_time, ... }
 */
export default function LLMConfigBox({ onConfigUpdate }) {
  const [command, setCommand] = useState('');
  const [loading, setLoading] = useState(false);
  const [acknowledgement, setAcknowledgement] = useState(null);
  const [error, setError] = useState(null);

  const EXAMPLES = [
    'Reduce max green to 20 seconds',
    'Give ambulances highest priority',
    'Set yellow phase to 8 seconds',
    'Minimum green should be 5 seconds',
  ];

  async function handleApply() {
    if (!command.trim()) return;
    setLoading(true);
    setError(null);
    setAcknowledgement(null);

    const result = await applyConfig(command.trim());

    if (result.params && Object.keys(result.params).length > 0) {
      onConfigUpdate(result.params);
      setAcknowledgement(result.acknowledged);
      setCommand('');
    } else {
      setError(result.acknowledged || 'No parameters recognised. Try rephrasing.');
    }

    setLoading(false);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !loading) handleApply();
  }

  return (
    <div className="llm-config-box">
      <div className="llm-panel-header">
        <span className="llm-icon">⚙️</span>
        <span className="llm-title">Configure Controller</span>
        <span className="llm-badge">Gemini</span>
      </div>

      <div className="llm-config-input-row">
        <input
          type="text"
          className="input-control llm-config-input"
          placeholder="e.g. reduce max green to 20 seconds..."
          value={command}
          onChange={e => setCommand(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <Button onClick={handleApply} disabled={loading || !command.trim()}>
          {loading ? 'Applying...' : 'Apply'}
        </Button>
      </div>

      <div className="llm-examples">
        {EXAMPLES.map(ex => (
          <button
            key={ex}
            className="llm-example-chip"
            onClick={() => setCommand(ex)}
            type="button"
          >
            {ex}
          </button>
        ))}
      </div>

      {acknowledgement && (
        <p className="llm-ack">✅ {acknowledgement}</p>
      )}
      {error && (
        <p className="llm-ack llm-ack-error">⚠️ {error}</p>
      )}
    </div>
  );
}
