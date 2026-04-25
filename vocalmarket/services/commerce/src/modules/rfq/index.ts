import { Module } from "@medusajs/framework/utils"
import RFQModuleService from "./service"

export const RFQ_MODULE = "rfq"

export default Module(RFQ_MODULE, { service: RFQModuleService })
