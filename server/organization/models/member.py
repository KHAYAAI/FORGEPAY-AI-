from django.conf import settings
from django.db import models

from .organization import Organization


class MemberRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    PROCUREMENT_MANAGER = "procurement_manager", "Procurement Manager"
    BUYER = "buyer", "Buyer"
    VIEWER = "viewer", "Viewer"


class OrganizationMember(models.Model):
    """
    Links a User to an Organization with a role and optional per-user spend override.

    A user belongs to exactly one organization (OneToOne to User).
    The spend_limit_override, when set, takes precedence over the org-level limit
    for this specific user — useful for limiting junior buyers while giving
    managers a higher threshold.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_membership",
    )
    role = models.CharField(max_length=32, choices=MemberRole.choices, default=MemberRole.BUYER)

    # Per-member spend override. Null means: use org.spend_limit_per_order.
    spend_limit_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Per-order spend limit override in ZAR cents. Null = use org default.",
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_org_member"),
        ]

    def effective_spend_limit(self) -> int:
        """Return the spend limit that applies to this member in ZAR cents."""
        if self.spend_limit_override is not None:
            return self.spend_limit_override
        return self.organization.spend_limit_per_order

    def can_approve(self) -> bool:
        return self.role in (MemberRole.ADMIN, MemberRole.PROCUREMENT_MANAGER)

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
