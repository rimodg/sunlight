import { createContext, useContext, useState, useCallback, useMemo } from 'react';

const AppContext = createContext(null);

const MOCK_MAP = {
  '/api/v2/risk-inbox': '/mock/risk-inbox.json',
  '/api/v2/portfolio': '/mock/portfolio.json',
  '/api/v2/onboarding/status': '/mock/onboarding.json',
  '/api/v2/tenants': '/mock/admin.json',
};

function jobMockPath(path) {
  const match = path.match(/^\/api\/v2\/jobs\/.+/);
  if (match) return '/mock/job.json';
  return null;
}

export function AppProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('sunlight_api_key') || '');
  const [tenantId, setTenantId] = useState(() => localStorage.getItem('sunlight_tenant_id') || '');
  const [role, setRole] = useState(() => localStorage.getItem('sunlight_role') || 'analyst');
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem('sunlight_user');
    return stored ? JSON.parse(stored) : null;
  });

  const isDemoMode = useMemo(
    () => new URLSearchParams(window.location.search).has('demo'),
    []
  );

  const isAdmin = role === 'admin';
  const isAuthenticated = isDemoMode || !!(apiKey && tenantId);

  const apiFetch = useCallback(async (path, opts = {}) => {
    if (isDemoMode) {
      const mockPath = MOCK_MAP[path] || jobMockPath(path);
      if (mockPath) {
        const res = await fetch(mockPath);
        return res.json();
      }
      return {};
    }

    const headers = { ...opts.headers, 'Content-Type': 'application/json' };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
      headers['Authorization'] = `Bearer ${apiKey}`;
    }
    if (tenantId) headers['X-Tenant-ID'] = tenantId;

    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
    return res.json();
  }, [isDemoMode, apiKey, tenantId]);

  const login = useCallback((key, tenant, userRole = 'analyst') => {
    setApiKey(key);
    setTenantId(tenant);
    setRole(userRole);
    setUser({ tenantId: tenant });
    localStorage.setItem('sunlight_api_key', key);
    localStorage.setItem('sunlight_tenant_id', tenant);
    localStorage.setItem('sunlight_role', userRole);
    localStorage.setItem('sunlight_user', JSON.stringify({ tenantId: tenant }));
  }, []);

  const logout = useCallback(() => {
    setApiKey('');
    setTenantId('');
    setRole('analyst');
    setUser(null);
    localStorage.removeItem('sunlight_api_key');
    localStorage.removeItem('sunlight_tenant_id');
    localStorage.removeItem('sunlight_role');
    localStorage.removeItem('sunlight_user');
  }, []);

  const value = useMemo(() => ({
    user, apiKey, tenantId, role, isDemoMode, isAdmin, isAuthenticated,
    apiFetch, login, logout,
  }), [user, apiKey, tenantId, role, isDemoMode, isAdmin, isAuthenticated, apiFetch, login, logout]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
