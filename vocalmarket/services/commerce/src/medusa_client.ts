/**
 * Medusa.js 2.x client wrapper.
 *
 * VocalMarket uses Medusa as the commerce backbone: catalog, inventory,
 * multi-vendor orders, and shipping. This module wraps the Medusa JS SDK
 * and adds VocalMarket-specific concepts (preferred suppliers, vertical
 * filtering, curated-supplier boost).
 */

import Medusa from "@medusajs/js-sdk";

const sdk = new Medusa({
  baseUrl: process.env.MEDUSA_BASE_URL ?? "http://medusa:9000",
  auth: { type: "jwt" },
  apiKey: process.env.MEDUSA_API_KEY ?? "",
});

export interface VocalProduct {
  id: string;
  variantId: string;
  name: string;
  description: string;
  price: number;
  currency: string;
  inStock: boolean;
  stockQuantity: number;
  supplierId: string;
  supplierName: string;
  isCurated: boolean; // Preferred/locked-in supplier flag
  vertical: string;
  tags: string[];
}

export interface CreateOrderPayload {
  userId: string;
  items: Array<{ variantId: string; quantity: number }>;
  shippingAddressId?: string;
  vertical: string;
  notes?: string;
}

export interface Order {
  id: string;
  status: string;
  total: number;
  currency: string;
  items: OrderItem[];
  createdAt: string;
}

export interface OrderItem {
  productId: string;
  variantId: string;
  name: string;
  quantity: number;
  unitPrice: number;
  supplierId: string;
}

// ── Product search ────────────────────────────────────────────────────────────

export async function searchProducts(
  query: string,
  vertical: string,
  filters: {
    priceMax?: number;
    inStockOnly?: boolean;
    supplierId?: string;
    tags?: string[];
  } = {}
): Promise<VocalProduct[]> {
  const result = await sdk.store.product.list({
    q: query,
    collection_id: [getCollectionForVertical(vertical)],
    limit: 20,
    fields:
      "id,title,description,variants.id,variants.prices,variants.inventory_quantity,metadata",
  });

  const products = (result.products ?? []).map((p: any) =>
    mapToVocalProduct(p, vertical)
  );

  let filtered = products;
  if (filters.inStockOnly) filtered = filtered.filter((p) => p.inStock);
  if (filters.priceMax !== undefined)
    filtered = filtered.filter((p) => p.price <= filters.priceMax!);
  if (filters.supplierId)
    filtered = filtered.filter((p) => p.supplierId === filters.supplierId);
  if (filters.tags?.length)
    filtered = filtered.filter((p) =>
      filters.tags!.some((t) => p.tags.includes(t))
    );

  // Boost curated/preferred suppliers to the top
  return filtered.sort((a, b) => {
    if (a.isCurated && !b.isCurated) return -1;
    if (!a.isCurated && b.isCurated) return 1;
    return 0;
  });
}

// ── Inventory ─────────────────────────────────────────────────────────────────

export async function checkInventory(
  variantIds: string[]
): Promise<Record<string, { available: boolean; quantity: number }>> {
  const result = await sdk.admin.inventoryItem.list({
    sku: variantIds,
  });

  const map: Record<string, { available: boolean; quantity: number }> = {};
  for (const item of result.inventory_items ?? []) {
    const qty = (item as any).stocked_quantity ?? 0;
    map[(item as any).sku] = { available: qty > 0, quantity: qty };
  }
  return map;
}

// ── Order creation ────────────────────────────────────────────────────────────

export async function createOrder(payload: CreateOrderPayload): Promise<Order> {
  // 1. Create cart
  const cartResult = await sdk.store.cart.create({
    region_id: getRegionForVertical(payload.vertical),
    metadata: { user_id: payload.userId, vertical: payload.vertical },
  });
  const cartId: string = (cartResult as any).cart.id;

  // 2. Add line items
  for (const item of payload.items) {
    await sdk.store.cart.createLineItem(cartId, {
      variant_id: item.variantId,
      quantity: item.quantity,
    });
  }

  // 3. Set shipping address if provided
  if (payload.shippingAddressId) {
    await sdk.store.cart.update(cartId, {
      shipping_address: { id: payload.shippingAddressId } as any,
    });
  }

  // 4. Complete cart → creates order
  const orderResult = await sdk.store.cart.complete(cartId);
  return mapToOrder((orderResult as any).order);
}

export async function getOrder(orderId: string): Promise<Order> {
  const result = await sdk.store.order.retrieve(orderId, {
    fields: "id,status,total,currency_code,items,created_at",
  });
  return mapToOrder((result as any).order);
}

// ── Vendor / supplier management ──────────────────────────────────────────────

/** Returns true if this supplier is in VocalMarket's curated/locked-in list. */
export function isCuratedSupplier(supplierId: string): boolean {
  const curated = (process.env.CURATED_SUPPLIER_IDS ?? "").split(",").filter(Boolean);
  return curated.includes(supplierId);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getCollectionForVertical(vertical: string): string {
  const map: Record<string, string> = {
    grocery: process.env.MEDUSA_COLLECTION_GROCERY ?? "",
    b2b_procurement: process.env.MEDUSA_COLLECTION_B2B ?? "",
    healthcare: process.env.MEDUSA_COLLECTION_HEALTHCARE ?? "",
  };
  return map[vertical] ?? "";
}

function getRegionForVertical(vertical: string): string {
  return process.env.MEDUSA_REGION_ZA ?? "reg_01";
}

function mapToVocalProduct(p: any, vertical: string): VocalProduct {
  const variant = p.variants?.[0] ?? {};
  const price = variant.prices?.[0]?.amount ?? 0;
  const supplierId: string = p.metadata?.supplier_id ?? "";
  return {
    id: p.id,
    variantId: variant.id ?? "",
    name: p.title ?? "",
    description: p.description ?? "",
    price: price / 100, // Medusa stores cents
    currency: variant.prices?.[0]?.currency_code?.toUpperCase() ?? "ZAR",
    inStock: (variant.inventory_quantity ?? 0) > 0,
    stockQuantity: variant.inventory_quantity ?? 0,
    supplierId,
    supplierName: p.metadata?.supplier_name ?? "",
    isCurated: isCuratedSupplier(supplierId),
    vertical,
    tags: p.tags?.map((t: any) => t.value) ?? [],
  };
}

function mapToOrder(o: any): Order {
  return {
    id: o.id,
    status: o.status,
    total: (o.total ?? 0) / 100,
    currency: o.currency_code?.toUpperCase() ?? "ZAR",
    items: (o.items ?? []).map((i: any) => ({
      productId: i.product_id,
      variantId: i.variant_id,
      name: i.title,
      quantity: i.quantity,
      unitPrice: (i.unit_price ?? 0) / 100,
      supplierId: i.metadata?.supplier_id ?? "",
    })),
    createdAt: o.created_at,
  };
}
