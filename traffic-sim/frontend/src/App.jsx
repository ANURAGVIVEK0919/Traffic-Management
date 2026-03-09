
import { BrowserRouter, Routes, Route } from 'react-router-dom'  // Router imports
import SimulationPage from './pages/SimulationPage'
import LoadingPage from './pages/LoadingPage'
import DashboardPage from './pages/DashboardPage'

// App component with routes only
export default function App() {
	return (
		<BrowserRouter>
			<Routes>
				<Route path="/" element={<SimulationPage />} />
				<Route path="/loading" element={<LoadingPage />} />
				<Route path="/dashboard" element={<DashboardPage />} />
				<Route path="/dashboard/:sessionId" element={<DashboardPage />} />
			</Routes>
		</BrowserRouter>
	)
}
