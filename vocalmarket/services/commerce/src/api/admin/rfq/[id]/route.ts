import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import type RFQModuleService from "../../../../modules/rfq/service"
import { RFQ_MODULE } from "../../../../modules/rfq"

interface QuoteResponseBody {
  quote_items: Array<{
    product_id: string
    unit_price_cents: number
    currency: string
    lead_time_days: number
    notes?: string
  }>
  total_cents: number
  currency: string
  valid_until: string   // ISO date
  payment_terms?: string
}

/**
 * POST /admin/rfq/:id/quote
 * Supplier submits a quote in response to an RFQ.
 * Notifies intelligence service to record RFQ response time.
 *
 * POST /admin/rfq/:id/reject
 * Supplier declines to quote.
 */
export const POST = async (req: MedusaRequest, res: MedusaResponse) => {
  const { id } = req.params
  const action = (req.query.action as string) ?? "quote"

  const rfqService = req.scope.resolve<RFQModuleService>(RFQ_MODULE)

  let rfq
  try {
    rfq = await rfqService.retrieveRFQ(id)
  } catch {
    return res.status(404).json({ message: `RFQ ${id} not found` })
  }

  if (rfq.status !== "pending") {
    return res.status(409).json({ message: `RFQ is already in status: ${rfq.status}` })
  }

  if (action === "reject") {
    await rfqService.updateRFQs({ id }, { status: "rejected" })
    return res.json({ id, status: "rejected" })
  }

  const body = req.body as QuoteResponseBody
  if (!body.quote_items?.length || !body.total_cents) {
    return res.status(400).json({ message: "quote_items and total_cents are required" })
  }

  await rfqService.updateRFQs(
    { id },
    {
      status: "quoted",
      supplier_quote: {
        items: body.quote_items,
        total_cents: body.total_cents,
        currency: body.currency,
        valid_until: body.valid_until,
        payment_terms: body.payment_terms ?? "net30",
        quoted_at: new Date().toISOString(),
      },
    }
  )

  // Notify intelligence service: record RFQ response time (best-effort)
  const createdAt = new Date(rfq.created_at ?? Date.now())
  const responseHours = (Date.now() - createdAt.getTime()) / 3_600_000

  try {
    const intelligenceBase =
      process.env.INTELLIGENCE_BASE_URL ?? "http://intelligence:8004"
    await fetch(`${intelligenceBase}/internal/rfq-response`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        supplier_id: rfq.supplier_id,
        response_time_hours: parseFloat(responseHours.toFixed(2)),
        was_accepted: true,
      }),
    })
  } catch {
    // Non-fatal — intelligence metric failure must not block quote submission
  }

  return res.json({
    id,
    status: "quoted",
    supplier_quote: body,
    conversation_id: rfq.conversation_id,
  })
}
