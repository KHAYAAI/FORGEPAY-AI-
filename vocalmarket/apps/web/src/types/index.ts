export type Vertical = "grocery" | "b2b_procurement" | "healthcare";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  org_id?: string;
  role?: string;
}

export interface Product {
  id: string;
  name: string;
  price: number;
  currency: string;
  inStock: boolean;
  isCurated?: boolean;
}

export interface AgentResponse {
  text: string;
  products?: Product[];
  suggested_actions?: Array<{ label: string; payload: string }>;
}

export interface Conversation {
  id: string;
  vertical: Vertical;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  products?: Product[];
}

export interface Order {
  id: string;
  status: "pending" | "confirmed" | "shipped" | "delivered" | "cancelled";
  vertical: Vertical;
  total_amount: number;
  currency: string;
  created_at: string;
  items: OrderItem[];
}

export interface OrderItem {
  id: string;
  name: string;
  quantity: number;
  unit_price: number;
  currency: string;
}

export const VERTICAL_LABELS: Record<Vertical, string> = {
  grocery: "Grocery",
  b2b_procurement: "B2B Procurement",
  healthcare: "Healthcare",
};

export const VERTICAL_DESCRIPTIONS: Record<Vertical, string> = {
  grocery: "Voice-first grocery shopping with same-day delivery",
  b2b_procurement: "AI-powered supplier discovery and RFQ management",
  healthcare: "Compliant prescription and OTC ordering",
};
