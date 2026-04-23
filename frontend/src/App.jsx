import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import ChatPage from './pages/ChatPage';
import ShadowPage from './pages/ShadowPage';
import AuditPage from './pages/AuditPage';

/**
 * Buddi shell.
 *
 * FE-06 (April-21 re-audit): each top-level route is wrapped in its own
 * `<ErrorBoundary>` so that a thrown exception inside one page cannot
 * crash the entire app. The boundary renders a fallback UI and leaves the
 * router / layout in a usable state.
 */
function App() {
  return (
    <Router>
      <div className="mesh-background" />
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route
              index
              element={
                <ErrorBoundary>
                  <Dashboard />
                </ErrorBoundary>
              }
            />
            <Route
              path="chat"
              element={
                <ErrorBoundary>
                  <ChatPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="shadow"
              element={
                <ErrorBoundary>
                  <ShadowPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="audit"
              element={
                <ErrorBoundary>
                  <AuditPage />
                </ErrorBoundary>
              }
            />
          </Route>
        </Routes>
      </ErrorBoundary>
    </Router>
  );
}

export default App;
