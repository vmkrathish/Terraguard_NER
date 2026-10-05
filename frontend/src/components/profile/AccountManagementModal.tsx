import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  type Role,
  type UserAccount,
  activateUserRequest,
  createUserRequest,
  deactivateUserRequest,
  listManageableUsersRequest,
} from "../../api/auth";

interface Props {
  onClose: () => void;
}

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  authority: "Authority",
  field_officer: "Field Officer",
};

// Which roles the logged-in user is allowed to CREATE — mirrors
// `_can_create_role()` in backend/app/api/auth.py exactly, but is only a
// convenience for building the role dropdown: the backend re-checks this
// itself on every POST /auth/users regardless of what's offered here.
function creatableRoles(currentUserEmail: string | undefined, role: string | undefined): Role[] {
  const isSuperAdmin = currentUserEmail?.trim().toLowerCase() === "admin.terraguard@gmail.com";
  if (isSuperAdmin) return ["admin", "authority", "field_officer"];
  if (role === "admin") return ["authority", "field_officer"];
  if (role === "authority") return ["field_officer"];
  return [];
}

type View = "list" | "create";

// Account Management — Create User / Activate / Deactivate, scoped to
// exactly what the logged-in user's role permits. Mirrors ProfileModal's
// shell/pattern (same .ai-modal-* CSS, same view/edit-style state toggle)
// rather than inventing a new modal pattern.
export default function AccountManagementModal({ onClose }: Props) {
  const { user } = useAuth();
  const [view, setView] = useState<View>("list");
  const [accounts, setAccounts] = useState<UserAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const roleOptions = creatableRoles(user?.email, user?.role);
  const [role, setRole] = useState<Role | "">(roleOptions[0] || "");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createdAccount, setCreatedAccount] = useState<{ email: string; password: string } | null>(null);

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const rows = await listManageableUsersRequest();
      setAccounts(rows);
    } catch (err: any) {
      setListError(err?.response?.data?.detail || "Couldn't load accounts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  async function handleToggleActive(account: UserAccount) {
    setActionError(null);
    setPendingId(account.id);
    try {
      const updated = account.is_active ? await deactivateUserRequest(account.id) : await activateUserRequest(account.id);
      setAccounts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || "Couldn't update that account's status.");
    } finally {
      setPendingId(null);
    }
  }

  function startCreate() {
    setFullName("");
    setEmail("");
    setRole(roleOptions[0] || "");
    setCreateError(null);
    setCreatedAccount(null);
    setView("create");
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);

    const trimmedName = fullName.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (trimmedName.length < 2) {
      setCreateError("Full name must be at least 2 characters long.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(trimmedEmail)) {
      setCreateError("Enter a valid email address.");
      return;
    }
    if (!role) {
      setCreateError("Choose a role.");
      return;
    }

    setCreating(true);
    try {
      const created = await createUserRequest(trimmedName, trimmedEmail, role);
      setCreatedAccount({ email: created.email, password: created.initial_password });
      setAccounts((prev) => [created, ...prev]);
    } catch (err: any) {
      setCreateError(err?.response?.data?.detail || "Couldn't create that account. Please try again.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="ai-modal-backdrop" onClick={onClose}>
      <div className="ai-modal account-mgmt-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-header">
          <h3 style={{ margin: 0 }}>{view === "list" ? "Account Management" : "Create User"}</h3>
          <button className="ai-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="ai-modal-body">
          {view === "list" ? (
            <div className="fade-in-up">
              {actionError && <div className="form-alert error" role="alert">{actionError}</div>}

              <div className="account-mgmt-toolbar">
                <span className="account-mgmt-hint">
                  {roleOptions.length > 0
                    ? "Create accounts, or activate/deactivate the accounts you manage."
                    : "You can view accounts here, but your role has no management actions."}
                </span>
                {roleOptions.length > 0 && (
                  <button type="button" className="btn btn-primary" onClick={startCreate}>
                    + Create User
                  </button>
                )}
              </div>

              {loading ? (
                <p className="account-mgmt-empty">Loading accounts…</p>
              ) : listError ? (
                <div className="form-alert error" role="alert">{listError}</div>
              ) : accounts.length === 0 ? (
                <p className="account-mgmt-empty">No accounts to show.</p>
              ) : (
                <ul className="account-mgmt-list">
                  {accounts.map((account) => (
                    <li key={account.id} className="account-mgmt-row">
                      <div className="account-mgmt-identity">
                        <div className="account-mgmt-name">{account.full_name}</div>
                        <div className="account-mgmt-email">{account.email}</div>
                      </div>
                      <span className={`role-label role-${account.role}`}>{ROLE_LABEL[account.role] || account.role}</span>
                      <span className={`badge badge-${account.is_active ? "GOOD" : "BAD"}`}>
                        <span className="badge-icon" aria-hidden="true">{account.is_active ? "✓" : "✕"}</span>
                        {account.is_active ? "Active" : "Inactive"}
                      </span>
                      <button
                        type="button"
                        className={`btn btn-sm ${account.is_active ? "btn-ghost" : "btn-primary"}`}
                        disabled={pendingId === account.id}
                        onClick={() => handleToggleActive(account)}
                      >
                        {pendingId === account.id ? "…" : account.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="fade-in-up">
              {createdAccount ? (
                <div className="account-created-success">
                  <div className="form-alert success">Account created for {createdAccount.email}.</div>
                  <p className="account-mgmt-hint">
                    Share this initial password with the new user — they can change it after signing in.
                  </p>
                  <div className="account-initial-password">{createdAccount.password}</div>
                  <div className="profile-actions">
                    <button type="button" className="btn btn-ghost" onClick={startCreate}>Create another</button>
                    <button type="button" className="btn btn-primary" onClick={() => setView("list")}>Back to list</button>
                  </div>
                </div>
              ) : (
                <form className="auth-form" onSubmit={handleCreate} noValidate>
                  {createError && <div className="form-alert error" role="alert">{createError}</div>}
                  <label>
                    Full name
                    <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} disabled={creating} />
                  </label>
                  <label>
                    Email address
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={creating} />
                  </label>
                  <label>
                    Role
                    <select value={role} onChange={(e) => setRole(e.target.value as Role)} disabled={creating}>
                      {roleOptions.map((r) => (
                        <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                      ))}
                    </select>
                  </label>
                  <p className="account-mgmt-hint">
                    The account starts with a default password, shown to you after creation, for the new user's first login.
                  </p>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="button" className="btn btn-ghost" onClick={() => setView("list")} disabled={creating}>
                      Cancel
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={creating}>
                      {creating ? "Creating…" : "Create account"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
