from django.conf import settings
from django.db import models
from django.utils import timezone

from .organization import Organization


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class ApprovalRequest(models.Model):
    """
    An order that exceeded the requester's spend limit and needs manager sign-off.

    Created by the B2B compliance check when order_total > member.effective_spend_limit().
    Hermes holds the order and re-submits it once approved.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_approvals",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="acted_on_approvals",
        help_text="Set when the request is approved or rejected",
    )

    # Order snapshot — stored so the approval can be acted on days later
    order_id = models.CharField(max_length=128, blank=True, help_text="Medusa order ID once created")
    order_total_cents = models.PositiveIntegerField(help_text="Total in ZAR cents")
    order_items = models.JSONField(help_text="Snapshot of items at time of request")
    conversation_id = models.CharField(
        max_length=256,
        blank=True,
        help_text="Hermes conversation to resume when order is approved",
    )

    status = models.CharField(max_length=32, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    requester_notes = models.TextField(blank=True, help_text="Business justification from requester")
    approver_notes = models.TextField(blank=True)

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Approval requests expire after 48h if not acted on",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["requester", "status"]),
        ]

    def approve(self, approver, notes: str = "") -> None:
        self.status = ApprovalStatus.APPROVED
        self.approver = approver
        self.approver_notes = notes
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "approver", "approver_notes", "resolved_at"])

    def reject(self, approver, notes: str = "") -> None:
        self.status = ApprovalStatus.REJECTED
        self.approver = approver
        self.approver_notes = notes
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "approver", "approver_notes", "resolved_at"])

    def expire(self) -> None:
        self.status = ApprovalStatus.EXPIRED
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at"])

    def __str__(self) -> str:
        return f"ApprovalRequest #{self.pk} by {self.requester} ({self.status})"
