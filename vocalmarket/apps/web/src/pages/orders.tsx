import { useEffect, useState } from "react";
import { listOrders } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { useApp } from "@/contexts/AppContext";
import type { Order, Vertical } from "@/types";

const STATUS_BADGE: Record<Order["status"], "default" | "indigo" | "success" | "warning" | "danger"> = {
  pending: "warning",
  confirmed: "indigo",
  shipped: "indigo",
  delivered: "success",
  cancelled: "danger",
};

const VERTICAL_LABELS: Record<Vertical, string> = {
  grocery: "Grocery",
  b2b_procurement: "B2B Procurement",
  healthcare: "Healthcare",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatCurrency(amount: number, currency: string) {
  return `${currency} ${amount.toFixed(2)}`;
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Order | null>(null);
  const { toast } = useApp();

  useEffect(() => {
    listOrders()
      .then(setOrders)
      .catch((err: Error) => {
        toast(err.message ?? "Failed to load orders", "error");
        setOrders(MOCK_ORDERS);
      })
      .finally(() => setLoading(false));
  }, [toast]);

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Orders</h1>
        <p className="mt-1 text-sm text-slate-400">Your purchase history across all verticals</p>
      </div>

      {loading ? (
        <OrdersSkeleton />
      ) : orders.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Order list */}
          <div className="lg:col-span-2 space-y-3">
            {orders.map((order) => (
              <button
                key={order.id}
                onClick={() => setSelected(selected?.id === order.id ? null : order)}
                className={[
                  "w-full rounded-xl border p-4 text-left transition-all",
                  selected?.id === order.id
                    ? "border-indigo-500/40 bg-slate-800/60"
                    : "border-slate-800 bg-slate-900 hover:border-slate-700 hover:bg-slate-800/40",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-slate-100">
                        #{order.id.slice(0, 8).toUpperCase()}
                      </span>
                      <Badge variant={STATUS_BADGE[order.status]}>
                        {order.status}
                      </Badge>
                      <Badge variant="default">
                        {VERTICAL_LABELS[order.vertical] ?? order.vertical}
                      </Badge>
                    </div>
                    <p className="mt-1.5 text-xs text-slate-500">{formatDate(order.created_at)}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {order.items.length} item{order.items.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold text-slate-100">
                      {formatCurrency(order.total_amount, order.currency)}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Order detail panel */}
          {selected && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-100">
                  Order #{selected.id.slice(0, 8).toUpperCase()}
                </h2>
                <button
                  onClick={() => setSelected(null)}
                  className="text-slate-500 hover:text-slate-300"
                  aria-label="Close"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="mb-4 space-y-1 text-xs text-slate-400">
                <div className="flex justify-between">
                  <span>Status</span>
                  <Badge variant={STATUS_BADGE[selected.status]}>{selected.status}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Vertical</span>
                  <span className="text-slate-300">{VERTICAL_LABELS[selected.vertical]}</span>
                </div>
                <div className="flex justify-between">
                  <span>Placed</span>
                  <span className="text-slate-300">{formatDate(selected.created_at)}</span>
                </div>
              </div>

              <div className="border-t border-slate-800 pt-4">
                <p className="mb-3 text-xs font-medium text-slate-400">Items</p>
                <div className="space-y-2">
                  {selected.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="truncate text-xs text-slate-200">{item.name}</p>
                        <p className="text-xs text-slate-500">×{item.quantity}</p>
                      </div>
                      <p className="ml-2 shrink-0 text-xs font-medium text-slate-300">
                        {formatCurrency(item.unit_price * item.quantity, item.currency)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-4">
                <span className="text-sm font-medium text-slate-300">Total</span>
                <span className="text-sm font-semibold text-slate-100">
                  {formatCurrency(selected.total_amount, selected.currency)}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OrdersSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-20 rounded-xl border border-slate-800 bg-slate-900 animate-pulse" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 py-16 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-800 text-slate-500">
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-300">No orders yet</p>
      <p className="mt-1 text-xs text-slate-500">Orders placed via voice or text will appear here</p>
    </div>
  );
}

// Shown when API is unreachable (dev/demo mode)
const MOCK_ORDERS: Order[] = [
  {
    id: "3f8a1b2c-demo",
    status: "delivered",
    vertical: "grocery",
    total_amount: 287.45,
    currency: "R",
    created_at: new Date(Date.now() - 2 * 86400_000).toISOString(),
    items: [
      { id: "i1", name: "Full Cream Milk 2L", quantity: 3, unit_price: 32.99, currency: "R" },
      { id: "i2", name: "Brown Bread", quantity: 2, unit_price: 18.50, currency: "R" },
      { id: "i3", name: "Chicken Breasts 1kg", quantity: 2, unit_price: 89.99, currency: "R" },
    ],
  },
  {
    id: "7c4e9d1a-demo",
    status: "confirmed",
    vertical: "b2b_procurement",
    total_amount: 45_000.00,
    currency: "R",
    created_at: new Date(Date.now() - 5 * 86400_000).toISOString(),
    items: [
      { id: "i4", name: "M8 Steel Bolts ISO 9001 (5000 units)", quantity: 1, unit_price: 45_000.00, currency: "R" },
    ],
  },
];
