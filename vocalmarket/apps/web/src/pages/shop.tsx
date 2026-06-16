import { useMemo, useState } from "react";
import { PRODUCT_CATALOG, CATEGORIES } from "@/data/products";
import { ProductCard } from "@/components/commerce/ProductCard";
import { useCart } from "@/contexts/CartContext";

export default function ShopPage() {
  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
  const { openCart, itemCount } = useCart();

  const filtered = useMemo(() => {
    return PRODUCT_CATALOG.filter((p) => {
      const matchesCategory = category === "all" || p.category === category;
      const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [category, search]);

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">🛒 Fresh Groceries</h1>
          <p className="mt-1 text-sm text-slate-400">Same-day delivery available in your area</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products…"
            className="w-56 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
          />
          {itemCount > 0 && (
            <button
              onClick={openCart}
              className="flex items-center gap-1.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-medium text-indigo-400 transition hover:bg-indigo-500/20"
            >
              Cart · {itemCount}
            </button>
          )}
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            onClick={() => setCategory(c.id)}
            className={[
              "rounded-full border px-3.5 py-1.5 text-xs font-medium transition",
              category === c.id
                ? "border-indigo-500 bg-indigo-600 text-white"
                : "border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-600",
            ].join(" ")}
          >
            {c.icon} {c.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 py-16 text-center">
          <p className="text-sm font-medium text-slate-300">No products found</p>
          <p className="mt-1 text-xs text-slate-500">Try a different search or category</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {filtered.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}
