import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import type RFQModuleService from "../../../modules/rfq/service"
import { RFQ_MODULE } from "../../../modules/rfq"

interface RFQLineItem {
  product_id: string
  quantity: number
  notes?: string
}

interface RFQBody {
  items: RFQLineItem[]
  supplier_id: string
  delivery_date?: string
  buyer_notes?: string
  conversation_id?: string
}

/**
 * POST /store/rfq
 *
 * Creates a Request for Quotation and records it in the RFQ module.
 * The intelligence service is notified separately (via the AI orchestrator)
 * to track RFQ response time once the supplier replies.
 *
 * Called by RequestQuoteTool in the B2B procurement vertical.
 */
export const POST = async (req: MedusaRequest, res: MedusaResponse) => {
  const body = req.body as RFQBody

  if (!body.items?.length) {
    return res.status(400).json({ message: "items must be a non-empty array" })
  }
  if (!body.supplier_id) {
    return res.status(400).json({ message: "supplier_id is required" })
  }

  const rfqService = req.scope.resolve<RFQModuleService>(RFQ_MODULE)

  const userId =
    (req as any).auth_context?.actor_id ??
    (req.headers["x-user-id"] as string) ??
    ""

  const rfq = await rfqService.createRFQs({
    supplier_id: body.supplier_id,
    supplier_name: body.supplier_id,   // enriched when supplier onboards via intelligence service
    status: "pending",
    items: body.items,
    delivery_date: body.delivery_date ? new Date(body.delivery_date) : null,
    buyer_notes: body.buyer_notes ?? "",
    response_sla_hours: 24,
    requester_user_id: userId,
    vertical: (req.headers["x-vertical"] as string) ?? "b2b_procurement",
    conversation_id: body.conversation_id ?? (req.headers["x-conversation-id"] as string) ?? "",
  })

  return res.status(201).json({
    id: rfq.id,
    supplier_id: rfq.supplier_id,
    supplier_name: rfq.supplier_name,
    status: rfq.status,
    response_sla_hours: rfq.response_sla_hours,
  })
}

/**
 * GET /store/rfq
 * List RFQs for the authenticated buyer.
 */
export const GET = async (req: MedusaRequest, res: MedusaResponse) => {
  const rfqService = req.scope.resolve<RFQModuleService>(RFQ_MODULE)
  const userId =
    (req as any).auth_context?.actor_id ??
    (req.headers["x-user-id"] as string) ??
    ""

  const [rfqs] = await rfqService.listAndCountRFQs(
    { requester_user_id: userId },
    { order: { created_at: "DESC" }, take: 20 }
  )

  return res.json({ rfqs })
}
