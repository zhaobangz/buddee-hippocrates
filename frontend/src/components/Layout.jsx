import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import PatientBrief from './PatientBrief';
import PerceptionWidget from './PerceptionWidget';
import useStore from '../store/useStore';

const Layout = () => {
  const fetchPatientProfile = useStore((state) => state.fetchPatientProfile);

  useEffect(() => {
    // Sync with backend on mount
    fetchPatientProfile();
  }, [fetchPatientProfile]);

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-200">
      {/* Sidebar Navigation */}
      <Sidebar />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top Header */}
        <TopBar />

        {/* Main Workspace Area */}
        <main className="flex-1 overflow-hidden flex">
          {/* Dynamic Content */}
          <div className="flex-1 overflow-y-auto p-6 custom-scrollbar relative">
            <Outlet />
          </div>

          {/* Right Sidebar - Live Context Panel */}
          <aside className="w-80 border-l border-white/5 bg-slate-900/40 backdrop-blur-xl flex flex-col hidden lg:flex">
             <PatientBrief />
          </aside>
        </main>
      </div>
      
      {/* Floating UI Elements */}
      <PerceptionWidget />
    </div>
  );
};

export default Layout;
