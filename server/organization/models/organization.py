from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    """
    An OEM or enterprise buyer account.

    One organization maps to many users (OrganizationMember).
    All procurement data — spend limits, supplier contracts, approval rules —
    lives at the org level so a Maruti procurement team shares the same config.
    """

    name = models.CharField(max_length=256, help_text="Legal entity name, e.g. 'Maruti Suzuki India Ltd'")
    slug = models.SlugField(unique=True, max_length=128, help_text="URL-safe identifier, auto-generated from name")

    # Spend control — values in ZAR cents (1 ZAR = 100 cents)
    spend_limit_per_order = models.PositiveIntegerField(
        default=5_000_000,  # R50,000
        help_text="Maximum single-order value in ZAR cents before approval is required",
    )
    spend_limit_per_month = models.PositiveIntegerField(
        default=50_000_000,  # R500,000
        help_text="Monthly spend cap in ZAR cents across all members",
    )

    # Billing
    subscription_tier = models.CharField(
        max_length=32,
        choices=[("starter", "Starter"), ("growth", "Growth"), ("enterprise", "Enterprise")],
        default="starter",
    )

    # Geography / locale
    country_code = models.CharField(max_length=2, default="ZA", help_text="ISO 3166-1 alpha-2")
    currency_code = models.CharField(max_length=3, default="ZAR", help_text="ISO 4217")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:128]
        super().save(*args, **kwargs)
