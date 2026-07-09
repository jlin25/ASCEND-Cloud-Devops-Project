// Thin client for the ASCEND FastAPI backend.
//
// Types are NOT hand-written here — they are generated from the backend's
// OpenAPI schema into ./api-types.ts. Regenerate after backend changes with:
//   npm run gen:api        (backend must be running on :8000)
// The Pydantic models (backend/jobs/jobs.py + routers) stay the single
// source of truth.

import type { paths } from "./api-types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Request bodies pulled straight from the generated schema, so the
// transcode/trim/extract_audio discriminated union is always in sync.
type CreateTaskBody =
  paths["/tasks"]["post"]["requestBody"]["content"]["application/json"];
type LoginBody =
  paths["/auth/login"]["post"]["requestBody"]["content"]["application/json"];
type RegisterBody =
  paths["/auth/register"]["post"]["requestBody"]["content"]["application/json"];

export type { CreateTaskBody, LoginBody, RegisterBody };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach the backend");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  return res.status === 204 ? (undefined as T) : (res.json() as Promise<T>);
}

export const api = {
  // Health check — no external deps; use for a connectivity indicator.
  health: () => request("/api/message"),

  // Tasks.
  createTask: (job: CreateTaskBody) =>
    request("/tasks", { method: "POST", body: JSON.stringify(job) }),
  listTasks: () => request("/tasks"),
  getTask: (id: string) => request(`/tasks/${id}`),
  getTaskResult: (id: string) => request(`/tasks/${id}/result`),
  deleteTask: (id: string) => request(`/tasks/${id}`, { method: "DELETE" }),

  // Auth (currently stubbed server-side).
  login: (creds: LoginBody) =>
    request("/auth/login", { method: "POST", body: JSON.stringify(creds) }),
  register: (creds: RegisterBody) =>
    request("/auth/register", { method: "POST", body: JSON.stringify(creds) }),
  logout: () => request("/auth/logout", { method: "POST" }),
};
