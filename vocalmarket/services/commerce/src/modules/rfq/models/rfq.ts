import { model } from "@medusajs/framework/utils"

/**
 * RFQ (Request for Quotation) model.
 *
 * Created by a B2B buyer via voice; supplier responds with a quote.
 * Hermes holds the conversation_id so it can resume when a quote arrives.
 */
const RFQ = model.define("rfq", {
  id: model.id().primaryKey(),
  supplier_id: model.text(),
  supplier_name: model.text().default(""),
  status: model
    .enum(["pending", "quoted", "accepted", "rejected", "expired"])
    .default("pending"),
  items: model.json(),
  delivery_date: model.dateTime().nullable(),
  buyer_notes: model.text().default(""),
  supplier_quote: model.json().nullable(),     // Quote details when supplier responds
  response_sla_hours: model.number().default(24),
  requester_user_id: model.text().default(""),
  vertical: model.text().default("b2b_procurement"),
  // Hermes conversation to resume when supplier quote arrives
  conversation_id: model.text().default(""),
})

export default RFQ
