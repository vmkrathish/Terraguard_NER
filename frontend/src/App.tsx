import { useEffect, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import RoleDashboard from "./pages/dashboards/RoleDashboard";
import GisMapPage from "./pages/GisMapPage";
import WeatherMapPage from "./pages/WeatherMapPage";
import PredictionPage from "./pages/PredictionPage";
import IncidentsPage from "./pages/IncidentsPage";
import EmergencyRoutePage from "./pages/EmergencyRoutePage";
import RagAssistantPage from "./pages/RagAssistantPage";
import AlertsPage from "./pages/AlertsPage";
import VillageDataPage from "./pages/VillageDataPage";
import LoginPage from "./pages/auth/LoginPage";
import ForgotPasswordPage from "./pages/auth/ForgotPasswordPage";
import ResetPasswordPage from "./pages/auth/ResetPasswordPage";
import FloatingAssistant from "./components/FloatingAssistant";
import ProfileModal from "./components/profile/ProfileModal";
import AccountManagementModal from "./components/profile/AccountManagementModal";
import ProtectedRoute from "./auth/ProtectedRoute";
import { useAuth } from "./auth/AuthContext";
import logo from "./assets/logo-icon.png";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/map", label: "GIS Map" },
  { to: "/weather", label: "Weather Map" },
  { to: "/prediction", label: "Prediction" },
  { to: "/incidents", label: "Incidents" },
  { to: "/village-data", label: "Village Data" },
  { to: "/route", label: "Emergency Route" },
  { to: "/assistant", label: "AI Assist" },
  { to: "/alerts", label: "Alerts" },
];

function initials(name?: string | null, email?: string) {
  const source = (name || email || "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [accountMgmtOpen, setAccountMgmtOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const showSignInInfo = true;
  // Only Admins and Authorities can ever create/activate/deactivate anyone
  // (see the role matrix in backend/app/api/auth.py) — Field Officers never
  // can, so the menu item isn't shown to them at all. This is purely a
  // convenience hide: every actual permission check happens server-side
  // regardless of what this condition renders.
  const canManageAccounts = user?.role === "admin" || user?.role === "authority";
  const [dashboardEntry, setDashboardEntry] = useState(() => location.pathname === "/");

  useEffect(() => {
    if (!dashboardEntry) return;
    const entryTimer = window.setTimeout(() => setDashboardEntry(false), 1000);
    return () => window.clearTimeout(entryTimer);
  }, [dashboardEntry]);

  // Clicking anywhere outside the profile/logout dropdown (or pressing
  // Escape) closes it automatically, instead of only being closeable by
  // clicking the profile button again.
  useEffect(() => {
    if (!userMenuOpen) return;

    function handlePointerDown(event: PointerEvent) {
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setUserMenuOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [userMenuOpen]);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={`app-shell ${dashboardEntry ? "dashboard-entry" : ""}`}>
      <div className={`sidebar-scrim ${sidebarOpen ? "open" : ""}`} onClick={() => setSidebarOpen(false)} />

      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-brand">
          <img src={logo} alt="TerraGuard NER" />
          <div className="brand-text">
            <strong>
              Terra<span>Guard</span>
            </strong>
          </div>
        </div>

        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} onClick={() => setSidebarOpen(false)}>
              <span className="nav-dot" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="avatar">{initials(user?.full_name, user?.email)}</div>
            <div className="who">
              <div className="name">{user?.full_name || user?.email}</div>
              <div className="role">{user?.role?.replace("_", " ")}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </aside>

      <div className="main-area">
        <div className="topbar">
          <button className="menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            ☰
          </button>
          <div className="sidebar-brand" style={{ border: "none", padding: 0, margin: 0 }}>
            <img src={logo} alt="TerraGuard NER" style={{ width: 26, height: 26 }} />
            <strong style={{ fontSize: 14 }}>
              Terra<span style={{ color: "var(--accent-strong)" }}>Guard</span>
            </strong>
          </div>
          <div className="avatar" style={{ width: 30, height: 30, fontSize: 11 }}>
            {initials(user?.full_name, user?.email)}
          </div>
        </div>

        <main className="main-content">
          {showSignInInfo && (
            <div className="page-signin-menu" ref={userMenuRef}>
              <button
                className="page-signin-info"
                onClick={() => setUserMenuOpen((open) => !open)}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                aria-controls="page-user-menu"
              >
                <div className="avatar">{initials(user?.full_name, user?.email)}</div>
                <div>
                  <strong>{user?.full_name || user?.email}</strong>
                  <span className={`role-label role-${user?.role || "user"}`}>
                    {user?.role?.replace("_", " ").toUpperCase() || "USER"}
                  </span>
                </div>
              </button>
              <div
                id="page-user-menu"
                className={`page-user-menu ${userMenuOpen ? "open" : ""}`}
                role="menu"
                aria-hidden={!userMenuOpen}
              >
                <button
                  type="button"
                  className="page-user-menu-profile"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setProfileOpen(true);
                  }}
                  role="menuitem"
                  tabIndex={userMenuOpen ? 0 : -1}
                >
                  Profile
                </button>
                {canManageAccounts && (
                  <button
                    type="button"
                    className="page-user-menu-profile"
                    onClick={() => {
                      setUserMenuOpen(false);
                      setAccountMgmtOpen(true);
                    }}
                    role="menuitem"
                    tabIndex={userMenuOpen ? 0 : -1}
                  >
                    Account Management
                  </button>
                )}
                <button type="button" onClick={handleLogout} role="menuitem" tabIndex={userMenuOpen ? 0 : -1}>Sign Out</button>
              </div>
            </div>
          )}
          {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
          {accountMgmtOpen && <AccountManagementModal onClose={() => setAccountMgmtOpen(false)} />}
          <div key={location.pathname} className="route-page-transition">
            <Routes>
              <Route path="/" element={<RoleDashboard />} />
              <Route path="/map" element={<GisMapPage />} />
              <Route path="/weather" element={<WeatherMapPage />} />
              <Route path="/prediction" element={<PredictionPage />} />
              <Route path="/incidents" element={<IncidentsPage />} />
              <Route path="/village-data" element={<VillageDataPage />} />
              <Route path="/route" element={<EmergencyRoutePage />} />
              <Route path="/assistant" element={<RagAssistantPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
        {location.pathname !== "/assistant" && <FloatingAssistant />}
      </div>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
