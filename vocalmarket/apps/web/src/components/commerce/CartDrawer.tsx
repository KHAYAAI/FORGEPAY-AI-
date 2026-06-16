import { useNavigate } from "react-router-dom";
import { useCart } from "@/contexts/CartContext";

export function CartDrawer() {
  const { items, isOpen, closeCart, subtotal, currency, setQuantity, removeItem, clearCart } = useCart();
  const navigate = useNavigate();

  return (
    <>
      {isOpen && <div className="fixed inset-0 z-40 bg-black/60" onClick={closeCart} />}
      <aside
        className={[
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-slate-800 bg-slate-900 transition-transform duration-300",
          isOpen ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 px-5">
          <h2 className="text-sm font-semibold text-slate-100">Shopping cart</h2>
          <button onClick={closeCart} className="text-slate-500 hover:text-slate-300" aria-label="Close cart">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {items.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-500">Your cart is empty</p>
            </div>
          ) : (
            <div className="space-y-3">
              {items.map(({ product, quantity }) => (
                <div key={product.id} className="flex gap-3 rounded-xl border border-slate-800 bg-slate-800/50 p-3">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-2xl">
                    {product.emoji ?? "🛒"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-slate-200">{product.name}</p>
                    <p className="mt-0.5 text-xs font-semibold text-indigo-400">
                      {product.currency} {product.price.toFixed(2)}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        onClick={() => setQuantity(product.id, quantity - 1)}
                        className="rounded border border-slate-700 px-1.5 text-xs text-slate-300 hover:text-indigo-400"
                      >
                        −
                      </button>
                      <span className="text-xs text-slate-300">{quantity}</span>
                      <button
                        onClick={() => setQuantity(product.id, quantity + 1)}
                        className="rounded border border-slate-700 px-1.5 text-xs text-slate-300 hover:text-indigo-400"
                      >
                        +
                      </button>
                    </div>
                  </div>
                  <button onClick={() => removeItem(product.id)} className="text-slate-500 hover:text-red-400" aria-label="Remove">
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {items.length > 0 && (
          <div className="shrink-0 space-y-3 border-t border-slate-800 p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Subtotal</span>
              <span className="text-lg font-semibold text-slate-100">
                {currency} {subtotal.toFixed(2)}
              </span>
            </div>
            <button
              onClick={() => {
                closeCart();
                navigate("/checkout");
              }}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
            >
              Checkout
            </button>
            <button
              onClick={clearCart}
              className="w-full rounded-lg border border-slate-700 py-2 text-xs text-slate-400 transition hover:border-slate-600 hover:text-slate-300"
            >
              Clear cart
            </button>
          </div>
        )}
      </aside>
    </>
  );
}

export function CartButton() {
  const { itemCount, toggleCart } = useCart();
  return (
    <button
      onClick={toggleCart}
      className="fixed bottom-6 right-6 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 transition hover:scale-105 hover:bg-indigo-500"
      aria-label="Open cart"
    >
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.75}
          d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 1.91-4.612 2.624-7.165a3 3 0 00-2.92-3.835H6.084M7.5 14.25L5.106 5.272M6 18.75a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm9.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z"
        />
      </svg>
      {itemCount > 0 && (
        <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
          {itemCount}
        </span>
      )}
    </button>
  );
}
