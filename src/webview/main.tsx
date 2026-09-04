import React from 'react';
import ReactDOM from 'react-dom/client';

// Safe mock for acquireVsCodeApi outside of VS Code environment
if (typeof (window as any).acquireVsCodeApi !== 'function') {
  (window as any).acquireVsCodeApi = () => ({
    postMessage: (msg: any) => console.log('Mock postMessage:', msg),
    getState: () => ({}),
    setState: (state: any) => console.log('Mock setState:', state),
  });
}

function App() {
  return (
    <div style={{ padding: '20px', background: '#007acc', color: 'white', borderRadius: '8px' }}>
      <h1>Webview Live!</h1>
      <p>React is rendering successfully in your browser.</p>
    </div>
  );
}

const container = document.getElementById('root');
if (container) {
  const root = ReactDOM.createRoot(container);
  root.render(<App />);
}