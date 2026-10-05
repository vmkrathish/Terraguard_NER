import axios from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const TOKEN_KEY = "terraguard_token";

export const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// If any request comes back unauthorized, the stored token is no longer
// valid (expired/tampered). Clear it and let the app react by redirecting
// to /login — AuthContext listens for this event.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && !error?.config?.url?.includes("/auth/login")) {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event("terraguard:unauthorized"));
    }
    return Promise.reject(error);
  }
);
