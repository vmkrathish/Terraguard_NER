import { useAuth } from "../../auth/AuthContext";
import FieldOfficerDashboardPage from "./FieldOfficerDashboardPage";
import AuthorityDashboardPage from "./AuthorityDashboardPage";
import AdminDashboardPage from "./AdminDashboardPage";

// Landing route ("/") picks the dashboard by the signed-in user's real
// role (users.role is 'admin' | 'authority' | 'field_officer' — see the
// backend auth schema) — separate pages per role, not one shared page with
// conditional widgets, per the requested dashboard structure.
export default function RoleDashboard() {
  const { user } = useAuth();

  if (user?.role === "field_officer") return <FieldOfficerDashboardPage />;
  if (user?.role === "admin") return <AdminDashboardPage />;
  // "authority" and any unrecognized/legacy role value both fall back to the
  // authority (command-center) view rather than guessing at a narrower one.
  return <AuthorityDashboardPage />;
}
