
import { BrowserRouter, Routes, Route } from 'react-router-dom'  // Router imports
import SimulationPage from './pages/SimulationPage'
import LoadingPage from './pages/LoadingPage'
import DashboardPage from './pages/DashboardPage'
import VideoUploadPage from './pages/VideoUploadPage'

// App component with routes only
export default function App() {
	return (
		<BrowserRouter>
			<Routes>
				<Route path="/" element={<SimulationPage />} />
				<Route path="/upload" element={<VideoUploadPage />} />
				<Route path="/loading" element={<LoadingPage />} />
				<Route path="/dashboard" element={<DashboardPage />} />
				<Route path="/dashboard/:id" element={<DashboardPage />} />
			</Routes>
		</BrowserRouter>
	)
}
