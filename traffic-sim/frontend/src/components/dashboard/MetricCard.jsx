// MetricCard component displays metric comparison results
// No logic, no imports, no styling

export default function MetricCard({ metricKey, label, dynamicValue, staticValue, winner, explanation }) {
  return (
    <div>
      {/* Metric label */}
      <h3>{label}</h3>
      {/* Dynamic value */}
      <p>Dynamic: {dynamicValue ?? 'N/A'}</p>
      {/* Static value */}
      <p>Static: {staticValue ?? 'N/A'}</p>
      {/* Winner */}
      <p>Winner: {winner}</p>
      {/* Explanation */}
      <p>{explanation}</p>
    </div>
  );
}
