import { Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import Layout from './components/Layout';
import RiskInbox from './views/RiskInbox';
import Portfolio from './views/Portfolio';
import CaseDetail from './views/CaseDetail';
import Admin from './views/Admin';
import Onboarding from './views/Onboarding';
import Login from './views/Login';

export default function App() {
  return (
    <AppProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<ProtectedLayout />} />
      </Routes>
    </AppProvider>
  );
}

function LoginPage() {
  const { isAuthenticated } = useApp();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <Login />;
}

function ProtectedLayout() {
  const { isAuthenticated } = useApp();
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RiskInbox />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="case/:jobId" element={<CaseDetail />} />
        <Route path="admin" element={<Admin />} />
        <Route path="onboarding" element={<Onboarding />} />
      </Route>
    </Routes>
  );
}
