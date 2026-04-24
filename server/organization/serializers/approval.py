from rest_framework import serializers

from organization.models import ApprovalRequest


class ApprovalRequestSerializer(serializers.ModelSerializer):
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    approver_email = serializers.EmailField(source="approver.email", read_only=True, allow_null=True)
    order_total_zar = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id", "requester", "requester_email", "approver", "approver_email",
            "order_id", "order_total_cents", "order_total_zar", "order_items",
            "conversation_id", "status", "requester_notes", "approver_notes",
            "expires_at", "created_at", "resolved_at",
        ]
        read_only_fields = [
            "id", "requester_email", "approver_email", "order_total_zar",
            "status", "approver_notes", "resolved_at",
        ]

    def get_order_total_zar(self, obj: ApprovalRequest) -> str:
        return f"R{obj.order_total_cents / 100:,.2f}"


class ApprovalActionSerializer(serializers.Serializer):
    """Used for approve/reject endpoints."""
    notes = serializers.CharField(required=False, default="", allow_blank=True)
