import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import type RFQModuleService from "../../../modules/rfq/service"
import { RFQ_MODULE } from "../../../modules/rfq"

/**
 * GET /admin/rfq
 * List all pending RFQs — used by supplier portal and admin dashboard.
 */
export const GET = async (req: MedusaRequest, res: MedusaResponse) => {
  const rfqService = req.scope.resolve<RFQModuleService>(RFQ_MODULE)
  const status = (req.query.status as string) ?? "pending"
  const supplierId = req.query.supplier_id as string | undefined

  const filters: Record<string, unknown> = { status }
  if (supplierId) filters.supplier_id = supplierId

  const [rfqs, count] = await rfqService.listAndCountRFQs(filters, {
    order: { created_at: "DESC" },
    take: 50,
  })

  return res.json({ rfqs, count })
}
