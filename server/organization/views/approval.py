from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from organization.models import ApprovalRequest, ApprovalStatus, OrganizationMember
from organization.serializers import ApprovalActionSerializer, ApprovalRequestSerializer


class ApprovalRequestListView(generics.ListCreateAPIView):
    """
    GET  /api/organizations/mine/approvals         — list requests visible to caller
    POST                                           — create a new approval request
    """

    serializer_class = ApprovalRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            membership = self.request.user.org_membership
        except OrganizationMember.DoesNotExist:
            return ApprovalRequest.objects.none()

        org = membership.organization
        # Admins/managers see all pending requests; buyers see only their own
        if membership.can_approve():
            return org.approval_requests.select_related("requester", "approver").filter(
                status=ApprovalStatus.PENDING
            )
        return org.approval_requests.filter(requester=self.request.user).select_related(
            "requester", "approver"
        )

    def perform_create(self, serializer):
        try:
            membership = self.request.user.org_membership
        except OrganizationMember.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of any organization.")

        from django.utils import timezone
        from datetime import timedelta
        serializer.save(
            organization=membership.organization,
            requester=self.request.user,
            expires_at=timezone.now() + timedelta(hours=48),
        )


class ApprovalRequestDetailView(generics.RetrieveAPIView):
    """GET /api/organizations/mine/approvals/<id>"""

    serializer_class = ApprovalRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            org = self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            return ApprovalRequest.objects.none()
        return org.approval_requests.all()


class ApprovalActionView(APIView):
    """
    POST /api/organizations/mine/approvals/<id>/approve
    POST /api/organizations/mine/approvals/<id>/reject
    """

    permission_classes = [permissions.IsAuthenticated]

    def _get_approval(self, pk: int, request) -> ApprovalRequest | None:
        try:
            membership = request.user.org_membership
        except OrganizationMember.DoesNotExist:
            return None
        if not membership.can_approve():
            return None
        try:
            return membership.organization.approval_requests.get(pk=pk, status=ApprovalStatus.PENDING)
        except ApprovalRequest.DoesNotExist:
            return None

    def post(self, request, pk: int, action: str):
        approval = self._get_approval(pk, request)
        if approval is None:
            return Response(
                {"detail": "Not found or you do not have permission to act on this request."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")

        if action == "approve":
            approval.approve(request.user, notes)
            return Response({"status": "approved", "id": approval.pk})
        elif action == "reject":
            approval.reject(request.user, notes)
            return Response({"status": "rejected", "id": approval.pk})

        return Response({"detail": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)
