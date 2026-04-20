"""
Vertical registry — maps each VocalMarket vertical to its Enthusiast DataSet
IDs and agent configuration. Populated from env vars so staging/prod can use
different DataSets without code changes.
"""

from dataclasses import dataclass
from pydantic_settings import BaseSettings


@dataclass
class VerticalConfig:
    name: str
    enthusiast_data_set_id: str
    product_search_agent_id: str
    order_intake_agent_id: str
    # Healthcare extras
    prescription_agent_id: str | None = None


class VerticalSettings(BaseSettings):
    grocery_data_set_id: str = ""
    grocery_product_search_agent_id: str = ""
    grocery_order_intake_agent_id: str = ""

    b2b_data_set_id: str = ""
    b2b_product_search_agent_id: str = ""
    b2b_order_intake_agent_id: str = ""

    healthcare_data_set_id: str = ""
    healthcare_product_search_agent_id: str = ""
    healthcare_order_intake_agent_id: str = ""
    healthcare_prescription_agent_id: str = ""

    class Config:
        env_prefix = "VOCALMARKET_"

    def grocery(self) -> VerticalConfig:
        return VerticalConfig(
            name="grocery",
            enthusiast_data_set_id=self.grocery_data_set_id,
            product_search_agent_id=self.grocery_product_search_agent_id,
            order_intake_agent_id=self.grocery_order_intake_agent_id,
        )

    def b2b_procurement(self) -> VerticalConfig:
        return VerticalConfig(
            name="b2b_procurement",
            enthusiast_data_set_id=self.b2b_data_set_id,
            product_search_agent_id=self.b2b_product_search_agent_id,
            order_intake_agent_id=self.b2b_order_intake_agent_id,
        )

    def healthcare(self) -> VerticalConfig:
        return VerticalConfig(
            name="healthcare",
            enthusiast_data_set_id=self.healthcare_data_set_id,
            product_search_agent_id=self.healthcare_product_search_agent_id,
            order_intake_agent_id=self.healthcare_order_intake_agent_id,
            prescription_agent_id=self.healthcare_prescription_agent_id,
        )


vertical_settings = VerticalSettings()
