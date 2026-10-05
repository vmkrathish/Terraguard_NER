import { type FormEvent, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { passwordRuleError } from "../../utils/password";

interface Props {
  onClose: () => void;
}

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  authority: "Authority",
  field_officer: "Field Officer",
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "Never";
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

type View = "view" | "edit";

// The account's mini-profile dashboard: view info, edit name/email, change
// password. Reuses the project's existing modal shell (.ai-modal-*, from
// AlertComposer/ImpactSimulatorModal) and form styling (.form-alert,
// .field-error, .password-field, .strength-meter, from SignupPage) rather
// than inventing new patterns. Role is displayed only — never an editable
// field, never sent in the update request (ProfileUpdateRequest has no
// `role` field at all on the backend, so this isn't just a UI restriction).
export default function ProfileModal({ onClose }: Props) {
  const { user, updateProfile, changePassword } = useAuth();
  const [view, setView] = useState<View>("view");

  const [fullName, setFullName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [savingPassword, setSavingPassword] = useState(false);

  if (!user) return null;

  async function handleSaveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileError(null);
    setProfileSuccess(null);

    const trimmedName = fullName.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (trimmedName.length < 2) {
      setProfileError("Full name must be at least 2 characters long.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(trimmedEmail)) {
      setProfileError("Enter a valid email address.");
      return;
    }

    const updates: { full_name?: string; email?: string } = {};
    if (trimmedName !== (user!.full_name || "")) updates.full_name = trimmedName;
    if (trimmedEmail !== user!.email) updates.email = trimmedEmail;

    if (Object.keys(updates).length === 0) {
      setProfileSuccess("Nothing to update.");
      return;
    }

    setSavingProfile(true);
    try {
      await updateProfile(updates);
      setProfileSuccess("Profile updated.");
      setView("view");
    } catch (err: any) {
      setProfileError(err?.response?.data?.detail || "Couldn't update your profile. Please try again.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (!currentPassword) {
      setPasswordError("Enter your current password.");
      return;
    }
    const ruleError = passwordRuleError(newPassword);
    if (ruleError) {
      setPasswordError(ruleError);
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordError("New passwords don't match.");
      return;
    }

    setSavingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      setPasswordSuccess("Password changed.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setShowPasswordSection(false);
    } catch (err: any) {
      setPasswordError(err?.response?.data?.detail || "Couldn't change your password. Please try again.");
    } finally {
      setSavingPassword(false);
    }
  }

  function startEdit() {
    setFullName(user!.full_name || "");
    setEmail(user!.email);
    setProfileError(null);
    setProfileSuccess(null);
    setView("edit");
  }

  return (
    <div className="ai-modal-backdrop" onClick={onClose}>
      <div className="ai-modal profile-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-header">
          <h3 style={{ margin: 0 }}>{view === "view" ? "My Profile" : "Edit Profile"}</h3>
          <button className="ai-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="ai-modal-body">
          {view === "view" ? (
            <div className="profile-view fade-in-up">
              <div className="profile-avatar-row">
                <div className="avatar profile-avatar">
                  {(user.full_name || user.email || "?").trim().slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="profile-name">{user.full_name || "—"}</div>
                  <span className={`role-label role-${user.role}`}>
                    {(ROLE_LABEL[user.role] || user.role).toUpperCase()}
                  </span>
                </div>
              </div>

              {profileSuccess && <div className="form-alert success">{profileSuccess}</div>}
              {passwordSuccess && <div className="form-alert success">{passwordSuccess}</div>}

              <dl className="profile-info-list">
                <div>
                  <dt>Email</dt>
                  <dd>{user.email}</dd>
                </div>
                <div>
                  <dt>Role</dt>
                  {/* Read-only, by design — see the module docstring above. */}
                  <dd>{ROLE_LABEL[user.role] || user.role}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <span className={`badge badge-${user.is_active === false ? "BAD" : "GOOD"}`}>
                      <span className="badge-icon" aria-hidden="true">{user.is_active === false ? "✕" : "✓"}</span>
                      {user.is_active === false ? "Inactive" : "Active"}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Last seen</dt>
                  <dd>{formatTimestamp(user.last_seen)}</dd>
                </div>
                {user.created_at && (
                  <div>
                    <dt>Member since</dt>
                    <dd>{formatTimestamp(user.created_at)}</dd>
                  </div>
                )}
              </dl>

              <div className="profile-actions">
                <button type="button" className="btn btn-primary" onClick={startEdit}>Edit Profile</button>
              </div>
            </div>
          ) : (
            <div className="fade-in-up">
              {profileError && <div className="form-alert error" role="alert">{profileError}</div>}

              <form className="auth-form" onSubmit={handleSaveProfile} noValidate>
                <label>
                  Full name
                  <input
                    type="text"
                    autoComplete="name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    disabled={savingProfile}
                  />
                </label>
                <label>
                  Email address
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={savingProfile}
                  />
                </label>
                <label>
                  Role
                  <input type="text" value={ROLE_LABEL[user.role] || user.role} disabled readOnly className="profile-role-readonly" />
                </label>

                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" className="btn btn-ghost" onClick={() => setView("view")} disabled={savingProfile}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={savingProfile}>
                    {savingProfile ? "Saving…" : "Save changes"}
                  </button>
                </div>
              </form>

              <div className="profile-password-toggle">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setShowPasswordSection((v) => !v);
                    setPasswordError(null);
                    setPasswordSuccess(null);
                  }}
                >
                  {showPasswordSection ? "Hide password change" : "Change password"}
                </button>

                {showPasswordSection && (
                  <form className="auth-form fade-in-up" onSubmit={handleChangePassword} noValidate style={{ marginTop: 12 }}>
                    {passwordError && <div className="form-alert error" role="alert">{passwordError}</div>}
                    <label>
                      Current password
                      <input
                        type="password"
                        autoComplete="current-password"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        disabled={savingPassword}
                      />
                    </label>
                    <label>
                      New password
                      <input
                        type="password"
                        autoComplete="new-password"
                        placeholder="8+ chars with a letter, a number, and a symbol"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        disabled={savingPassword}
                      />
                    </label>
                    <label>
                      Confirm new password
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={confirmNewPassword}
                        onChange={(e) => setConfirmNewPassword(e.target.value)}
                        disabled={savingPassword}
                      />
                    </label>
                    <button type="submit" className="btn btn-primary" disabled={savingPassword}>
                      {savingPassword ? "Updating…" : "Update password"}
                    </button>
                  </form>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
