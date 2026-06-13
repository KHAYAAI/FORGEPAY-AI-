import { clearAuth, getToken } from "./auth";
import type { AuthUser, Conversation, Message, Order, Vertical } from "@/types";

const API_BASE = (import.meta as { env: Record<string, string> }).env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Token ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearAuth();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, string>;
    throw new ApiError(res.status, body["detail"] ?? `Request failed: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────

export async function login(
  username: string,
  password: string,
): Promise<{ token: string; user: AuthUser }> {
  return request("/api/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout(): Promise<void> {
  await request("/api/auth/logout/", { method: "POST" }).catch(() => {});
  clearAuth();
}

// ── Conversations ─────────────────────────────────────────────────────────

interface PaginatedResult<T> {
  results: T[];
  count: number;
}

export async function listConversations(): Promise<Conversation[]> {
  const data = await request<PaginatedResult<Conversation>>("/api/conversations/");
  return data.results ?? [];
}

export async function getConversation(
  id: string,
): Promise<Conversation & { messages: Message[] }> {
  return request(`/api/conversations/${id}/`);
}

export async function createConversation(vertical: Vertical): Promise<Conversation> {
  return request("/api/conversations/", {
    method: "POST",
    body: JSON.stringify({ vertical }),
  });
}

export async function sendMessage(
  conversationId: string,
  text: string,
): Promise<{ message: Message; response: Message }> {
  return request(`/api/conversations/${conversationId}/messages/`, {
    method: "POST",
    body: JSON.stringify({ content: text }),
  });
}

// ── Orders ────────────────────────────────────────────────────────────────

export async function listOrders(): Promise<Order[]> {
  const data = await request<PaginatedResult<Order>>("/api/orders/");
  return data.results ?? [];
}

export async function getOrder(id: string): Promise<Order> {
  return request(`/api/orders/${id}/`);
}

// ── User ──────────────────────────────────────────────────────────────────

export async function getProfile(): Promise<AuthUser> {
  return request<AuthUser>("/api/profile/");
}

export async function updateProfile(data: Partial<AuthUser>): Promise<AuthUser> {
  return request<AuthUser>("/api/profile/", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}
