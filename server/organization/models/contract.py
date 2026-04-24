from django.db import models

from .organization import Organization


class SupplierContract(models.Model):
    """
    A negotiated contract between an OEM organization and a supplier.

    Tracks preferred pricing tiers, SLAs, and contract validity.
    When a supplier is under contract, Hermes highlights them
    and the B2B vertical can enforce contracted pricing.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="supplier_contracts",
    )
    supplier_id = models.CharField(
        max_length=128,
        help_text="Medusa/VocalMarket vendor ID",
    )
    supplier_name = models.CharField(max_length=256)

    is_preferred = models.BooleanField(
        default=False,
        help_text="Preferred suppliers are highlighted in Hermes recommendations",
    )
    is_exclusive = models.BooleanField(
        default=False,
        help_text="If True, Hermes will warn before recommending a non-contracted competitor",
    )

    # Negotiated terms stored as JSON for flexibility
    # Example: {"volume_tiers": [{"min_qty": 100, "discount_pct": 5}], "payment_days": 30}
    contract_terms = models.JSONField(
        default=dict,
        blank=True,
        help_text="Volume tiers, payment terms, SLAs, etc.",
    )

    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True, help_text="Null = open-ended contract")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "supplier_id"],
                name="unique_org_supplier_contract",
            ),
        ]
        ordering = ["-is_preferred", "supplier_name"]

    def is_active(self) -> bool:
        from django.utils import timezone
        today = timezone.now().date()
        if self.valid_from > today:
            return False
        if self.valid_until and self.valid_until < today:
            return False
        return True

    def __str__(self) -> str:
        return f"{self.organization} ↔ {self.supplier_name}"
