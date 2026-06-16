import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCart } from "@/contexts/CartContext";
import { useApp } from "@/contexts/AppContext";

export default function CheckoutPage() {
  const { items, subtotal, currency, clearCart } = useCart();
  const { toast } = useApp();
  const navigate = useNavigate();
  const [address, setAddress] = useState("");
  const [placing, setPlacing] = useState(false);

  const deliveryFee = subtotal > 0 ? 25 : 0;
  const total = subtotal + deliveryFee;

  async function handlePlaceOrder() {
    if (!address.trim()) {
      toast("Please enter a delivery address", "error");
      return;
    }
    setPlacing(true);
    await new Promise((r) => setTimeout(r, 1200));
    clearCart();
    toast("Order placed! You'll receive updates via voice or chat.", "success");
    navigate("/orders");
    setPlacing(false);
  }

  if (items.length === 0) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center bg-slate-950 px-4 py-16 text-center">
        <p className="text-sm font-medium text-slate-300">Your cart is empty</p>
        <button
          onClick={() => navigate("/shop")}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Browse products
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Checkout</h1>
        <p className="mt-1 text-sm text-slate-400">Review your order and confirm delivery details</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="mb-4 text-sm font-semibold text-slate-100">Delivery address</h2>
            <textarea
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Enter your delivery address…"
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="mb-4 text-sm font-semibold text-slate-100">Items ({items.length})</h2>
            <div className="space-y-3">
              {items.map(({ product, quantity }) => (
                <div key={product.id} className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-xl">
                    {product.emoji ?? "🛒"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-200">{product.name}</p>
                    <p className="text-xs text-slate-500">×{quantity}</p>
                  </div>
                  <p className="text-sm font-medium text-slate-300">
                    {product.currency} {(product.price * quantity).toFixed(2)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-sm font-semibold text-slate-100">Order summary</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between text-slate-400">
              <span>Subtotal</span>
              <span className="text-slate-200">
                {currency} {subtotal.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Delivery fee</span>
              <span className="text-slate-200">
                {currency} {deliveryFee.toFixed(2)}
              </span>
            </div>
          </div>
          <div className="mt-4 flex justify-between border-t border-slate-800 pt-4 text-base font-semibold">
            <span className="text-slate-300">Total</span>
            <span className="text-indigo-400">
              {currency} {total.toFixed(2)}
            </span>
          </div>
          <button
            onClick={handlePlaceOrder}
            disabled={placing}
            className="mt-6 w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
          >
            {placing ? "Placing order…" : "Place order"}
          </button>
        </div>
      </div>
    </div>
  );
}
