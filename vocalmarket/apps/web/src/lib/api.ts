import { clearAuth, getToken } from "./auth";
import type { AuthUser, CartItem, Conversation, Message, Order, Vertical } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const GATEWAY_BASE = import.meta.env.VITE_GATEWAY_BASE ?? "http://localhost:8080";

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

// ── Payments (via API Gateway → payments service → ForgePay) ────────────────
//
// Routed through the gateway rather than called directly so the payments
// service and ForgePay credentials never need to be reachable from the
// browser. The gateway accepts the same DRF token the web app already holds:
// it tries to decode it as a JWT first, and falls back to verifying it
// against Enthusiast's /api/users/me/ when that fails (see
// api_gateway/src/main.py verify_token()), so no separate login is required.

async function gatewayRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${GATEWAY_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, string>;
    throw new ApiError(res.status, body["detail"] ?? `Payment request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type PaymentMethod = "card" | "stablecoin" | "x402";

export interface PaymentSession {
  session_id: string;
  payment_url: string;
  wallet_address: string | null;
  chain_id: number | null;
  expires_at: number | null;
  method: PaymentMethod;
}

export async function initiatePayment(params: {
  orderId: string;
  amount: number;
  currency?: "ZAR" | "USDC" | "USDT";
  method?: PaymentMethod;
  returnUrl?: string;
  cancelUrl?: string;
  items: CartItem[];
}): Promise<PaymentSession> {
  return gatewayRequest<PaymentSession>("/v1/payments/initiate", {
    method: "POST",
    body: JSON.stringify({
      order_id: params.orderId,
      amount: params.amount,
      currency: params.currency ?? "ZAR",
      method: params.method ?? "card",
      return_url: params.returnUrl ?? "",
      cancel_url: params.cancelUrl ?? "",
      metadata: {
        items: params.items.map(({ product, quantity }) => ({
          product_id: product.id,
          name: product.name,
          quantity,
          unit_price: product.price,
        })),
      },
    }),
  });
}

export async function getPaymentSession(sessionId: string): Promise<Record<string, unknown>> {
  return gatewayRequest(`/v1/payments/sessions/${sessionId}`);
}
