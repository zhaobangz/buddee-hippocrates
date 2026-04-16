import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import ChatPage from './pages/ChatPage';
import ShadowPage from './pages/ShadowPage';
import AuditPage from './pages/AuditPage';

function App() {
  return (
    <Router>
      <div className="mesh-background" />
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="shadow" element={<ShadowPage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
