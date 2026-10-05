import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import AuthLayout from "./AuthLayout";
import { passwordRuleError } from "../../utils/password";

export default function ResetPasswordPage() {
  const { resetPassword } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!token) {
      setError("This reset link is missing its token. Request a new one.");
      return;
    }
    const passwordError = passwordRuleError(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
      setTimeout(() => navigate("/login", { replace: true }), 1800);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || "Couldn't reset your password. The link may have expired.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (success) {
    return (
      <AuthLayout>
        <div className="success-panel fade-in-up">
          <div className="icon-circle">✓</div>
          <h1>Password updated</h1>
          <p className="auth-subtitle">Redirecting you to sign in…</p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h1>Set a new password</h1>
      <p className="auth-subtitle">Choose a new password for your account.</p>

      {error && (
        <div className="form-alert error" role="alert">
          {error}
        </div>
      )}

      <form className="auth-form fade-in-up" onSubmit={handleSubmit} noValidate>
        <label>
          New password
          <input
            type="password"
            autoComplete="new-password"
            placeholder="8+ chars with a letter, a number, and a symbol"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={isSubmitting}
          />
        </label>

        <label>
          Confirm new password
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Re-enter your new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            disabled={isSubmitting}
          />
        </label>

        <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
          {isSubmitting && <span className="btn-spinner" />}
          {isSubmitting ? "Updating…" : "Update password"}
        </button>
      </form>

      <p className="auth-footer-link">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
