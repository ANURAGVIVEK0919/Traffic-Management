import { useLocation } from 'react-router-dom';

export default function AppSidebar() {
  const location = useLocation();
  const path = location.pathname || '';

  const activeKey = path.startsWith('/dashboard')
    ? 'overview'
    : (path.startsWith('/upload') || path.startsWith('/loading'))
      ? 'results'
      : 'simulation';

  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar-brand">Traffic Sim</div>
      <nav className="sidebar-nav">
        <button
          type="button"
          className={`nav-item ${activeKey === 'overview' ? 'nav-item-active' : ''}`}
          aria-current={activeKey === 'overview' ? 'page' : undefined}
        >
          Overview
        </button>
        <button
          type="button"
          className={`nav-item ${activeKey === 'simulation' ? 'nav-item-active' : ''}`}
          aria-current={activeKey === 'simulation' ? 'page' : undefined}
        >
          Simulation
        </button>
        <button
          type="button"
          className={`nav-item ${activeKey === 'results' ? 'nav-item-active' : ''}`}
          aria-current={activeKey === 'results' ? 'page' : undefined}
        >
          Results
        </button>
      </nav>
    </aside>
  );
}
