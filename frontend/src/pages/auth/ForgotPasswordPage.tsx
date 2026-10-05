import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import AuthLayout from "./AuthLayout";

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();

  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<{ message: string; resetLink?: string | null } | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await forgotPassword(email.trim().toLowerCase());
      setResult({ message: res.message, resetLink: res.reset_link });
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (result) {
    return (
      <AuthLayout>
        <div className="success-panel fade-in-up">
          <div className="icon-circle">✓</div>
          <h1>Check your reset link</h1>
          <p className="auth-subtitle">{result.message}</p>

          {result.resetLink && (
            <>
              <p className="auth-subtitle" style={{ marginBottom: 4 }}>
                No email service is configured yet in this environment, so your reset link is shown here directly:
              </p>
              <div className="reset-link-box">
                <Link to={result.resetLink.replace(window.location.origin, "")}>{result.resetLink}</Link>
              </div>
            </>
          )}

          <p className="auth-footer-link">
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h1>Forgot your password?</h1>
      <p className="auth-subtitle">Enter your account email and we'll generate a reset link.</p>

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

        <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
          {isSubmitting && <span className="btn-spinner" />}
          {isSubmitting ? "Sending…" : "Send reset link"}
        </button>
      </form>

      <p className="auth-footer-link">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
