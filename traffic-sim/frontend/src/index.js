if (process.env.NODE_ENV === 'development') {
	require('./debugFrontendFlow')
}

// Import React and ReactDOM
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Create root and render App
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
