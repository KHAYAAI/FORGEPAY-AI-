import { useCart } from "@/contexts/CartContext";
import type { Product } from "@/types";

export function ProductCard({ product }: { product: Product }) {
  const { items, addItem, setQuantity } = useCart();
  const cartItem = items.find((i) => i.product.id === product.id);
  const qty = cartItem?.quantity ?? 0;

  return (
    <div className="group flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 transition hover:border-indigo-500/40 hover:shadow-lg hover:shadow-indigo-500/5">
      <div className="relative flex aspect-square items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900 text-5xl">
        {product.emoji ?? "🛒"}
        {product.inStock ? (
          <span className="absolute right-2 top-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
            In stock
          </span>
        ) : (
          <span className="absolute right-2 top-2 rounded-full border border-red-500/20 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
            Out of stock
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="text-sm font-medium leading-snug text-slate-100">{product.name}</p>
        <div className="flex items-center justify-between">
          <p className="text-base font-semibold text-indigo-400">
            {product.currency} {product.price.toFixed(2)}
          </p>
          {product.unit && <p className="text-xs text-slate-500">{product.unit}</p>}
        </div>
        {product.rating && (
          <div className="flex items-center gap-1 text-xs text-slate-500">⭐ {product.rating}</div>
        )}
        <div className="mt-auto flex items-center gap-2 pt-1">
          {qty === 0 ? (
            <button
              onClick={() => addItem(product, 1)}
              disabled={!product.inStock}
              className="w-full rounded-lg bg-indigo-600 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Add to cart
            </button>
          ) : (
            <div className="flex w-full items-center justify-between rounded-lg border border-slate-700 bg-slate-800 px-2 py-1">
              <button
                onClick={() => setQuantity(product.id, qty - 1)}
                className="px-1.5 text-slate-300 hover:text-indigo-400"
              >
                −
              </button>
              <span className="text-xs font-medium text-slate-100">{qty}</span>
              <button
                onClick={() => setQuantity(product.id, qty + 1)}
                className="px-1.5 text-slate-300 hover:text-indigo-400"
              >
                +
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
