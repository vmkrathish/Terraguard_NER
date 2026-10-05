import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import AuthLayout from "./AuthLayout";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const redirectTo = (location.state as { from?: string } | null)?.from || "/";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError("Enter both your email and password.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
      navigate(redirectTo, { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || "Couldn't sign you in. Check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <h1>Welcome back</h1>
      <p className="auth-subtitle">Sign in to your TerraGuard NER console.</p>

      {error && (
        <div className="form-alert error" role="alert">
          {error}
        </div>
      )}

      <form className="auth-form fade-in-up" onSubmit={handleSubmit} noValidate>
        <label>
          Email address
          <input
            type="email"
            autoComplete="email"
            placeholder="you@authority.gov.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isSubmitting}
          />
        </label>

        <label>
          Password
          <div className="password-field">
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
            >
              {showPassword ? "HIDE" : "SHOW"}
            </button>
          </div>
        </label>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -6, marginBottom: 18 }}>
          <Link to="/forgot-password" className="forgot-password-link" style={{ fontSize: 13 }}>
            Forgot password?
          </Link>
        </div>

        <button type="submit" className="btn btn-primary btn-login-primary btn-block" disabled={isSubmitting}>
          {isSubmitting && <span className="btn-spinner" />}
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}
