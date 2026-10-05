// Mirrors the backend's `password_strength_error()` rule exactly
// (backend/app/core/security.py) so a weak password is rejected here, with
// the same wording, before it's ever sent to the backend — which remains
// the authoritative check either way (a request that bypasses this client
// check, e.g. a direct API call, is still rejected server-side).
//
// Rule: at least 8 characters, with at least one letter (either case — no
// separate uppercase/lowercase requirement), one number, and one special
// character.
//
// Previously lived in SignupPage.tsx (now removed — self-registration no
// longer exists, see Account Management) and was imported from there by
// ResetPasswordPage.tsx/ProfileModal.tsx; moved here so both keep working
// without depending on a page component.
export function passwordRuleError(pw: string): string | null {
  if (pw.length < 8) return "Password must be at least 8 characters long.";
  if (!/[A-Za-z]/.test(pw)) return "Password must include at least one letter.";
  if (!/[0-9]/.test(pw)) return "Password must include at least one number.";
  if (!/[^A-Za-z0-9]/.test(pw)) return "Password must include at least one special character (e.g. !@#$%^&*).";
  return null;
}
