import { api } from "./client";

export type Role = "admin" | "authority" | "field_officer";

export interface AuthUser {
  // Added for the profile mini-dashboard — all additive, an older cached
  // value (e.g. the login/signup response, which never carried these)
  // still satisfies this type since every new field is optional.
  id?: string | null;
  email: string;
  full_name?: string | null;
  role: Role | string;
  is_active?: boolean | null;
  last_seen?: string | null;
  created_at?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
  full_name?: string | null;
  email?: string | null;
}

export async function loginRequest(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/login", { email, password });
  return data;
}

export async function meRequest(): Promise<AuthUser> {
  const { data } = await api.get<AuthUser>("/auth/me");
  return data;
}

export async function logoutRequest(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } catch {
    // logout is best-effort client-side; ignore network errors here
  }
}

export interface ForgotPasswordResponse {
  message: string;
  reset_token?: string | null;
  reset_link?: string | null;
}

export async function forgotPasswordRequest(email: string): Promise<ForgotPasswordResponse> {
  const { data } = await api.post<ForgotPasswordResponse>("/auth/forgot-password", { email });
  return data;
}

export async function resetPasswordRequest(token: string, new_password: string): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>("/auth/reset-password", { token, new_password });
  return data;
}

export interface ProfileUpdateResponse extends AuthUser {
  // Only present when the update changed the email — see the backend
  // docstring on ProfileUpdateResponse. A changed email invalidates the
  // OLD JWT (its `sub` claim no longer resolves to any account), so the
  // caller must swap its stored token for this one to keep the session
  // alive without forcing a re-login mid-edit.
  access_token?: string | null;
}

export async function updateProfileRequest(updates: { full_name?: string; email?: string }): Promise<ProfileUpdateResponse> {
  const { data } = await api.patch<ProfileUpdateResponse>("/auth/profile", updates);
  return data;
}

export async function changePasswordRequest(currentPassword: string, newPassword: string): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return data;
}

// ---------- Account Management ----------
// Self-registration (the old /auth/signup) no longer exists — accounts are
// created only by an already-authenticated, authorized user via POST
// /auth/users below. Every permission check (who may create which role,
// who may activate/deactivate whom) is enforced server-side
// (backend/app/api/auth.py); the frontend only hides actions a user's own
// role could never actually use, it never relies on that hiding for
// security.

export interface UserAccount {
  id: string;
  full_name: string;
  email: string;
  role: Role | string;
  is_active: boolean;
  created_at?: string | null;
  last_seen?: string | null;
}

export interface CreateUserResponse extends UserAccount {
  // The fixed default password ("Terraguard@123") every new account starts
  // with — shown once, here, to the authorized creator so they can pass it
  // to the new user, who changes it after first login.
  initial_password: string;
}

export async function createUserRequest(full_name: string, email: string, role: Role): Promise<CreateUserResponse> {
  const { data } = await api.post<CreateUserResponse>("/auth/users", { full_name, email, role });
  return data;
}

export async function listManageableUsersRequest(): Promise<UserAccount[]> {
  const { data } = await api.get<UserAccount[]>("/auth/users/manageable");
  return data;
}

export async function activateUserRequest(userId: string): Promise<UserAccount> {
  const { data } = await api.post<UserAccount>(`/auth/users/${userId}/activate`);
  return data;
}

export async function deactivateUserRequest(userId: string): Promise<UserAccount> {
  const { data } = await api.post<UserAccount>(`/auth/users/${userId}/deactivate`);
  return data;
}
