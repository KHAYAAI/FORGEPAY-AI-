from django.urls import path
from rest_framework import generics, permissions
from rest_framework.response import Response

from organization.models import OrganizationMember, SupplierContract
from organization.views import (
    ApprovalActionView,
    ApprovalRequestDetailView,
    ApprovalRequestListView,
    MemberDetailView,
    OrganizationMembersView,
    OrganizationView,
    SupplierContractDetailView,
    SupplierContractListView,
)


class _OrgMemberContextView(generics.RetrieveAPIView):
    """
    Internal endpoint called by the AI orchestrator to get the calling user's
    org context: spend limit, role, contracted suppliers.
    Only accessible by service-account tokens (is_service_account=True).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id: str):
        if not request.user.is_service_account:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Internal endpoint — service accounts only.")

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.select_related("org_membership__organization").get(pk=user_id)
            membership = target_user.org_membership
        except (User.DoesNotExist, OrganizationMember.DoesNotExist):
            return Response({"org_id": None, "role": None, "spend_limit_cents": 5_000_000})

        contracts = SupplierContract.objects.filter(
            organization=membership.organization,
        ).values("supplier_id", "supplier_name", "is_preferred", "is_exclusive")

        return Response({
            "org_id": membership.organization.pk,
            "org_slug": membership.organization.slug,
            "role": membership.role,
            "spend_limit_cents": membership.effective_spend_limit(),
            "currency_code": membership.organization.currency_code,
            "country_code": membership.organization.country_code,
            "contracted_suppliers": list(contracts),
        })


urlpatterns = [
    # Organization
    path("api/organizations/mine", OrganizationView.as_view(), name="org_detail"),

    # Members
    path("api/organizations/mine/members", OrganizationMembersView.as_view(), name="org_members"),
    path("api/organizations/mine/members/<int:pk>", MemberDetailView.as_view(), name="org_member_detail"),

    # Supplier contracts
    path("api/organizations/mine/contracts", SupplierContractListView.as_view(), name="org_contracts"),
    path("api/organizations/mine/contracts/<int:pk>", SupplierContractDetailView.as_view(), name="org_contract_detail"),

    # Approval workflow
    path("api/organizations/mine/approvals", ApprovalRequestListView.as_view(), name="org_approvals"),
    path("api/organizations/mine/approvals/<int:pk>", ApprovalRequestDetailView.as_view(), name="org_approval_detail"),
    path("api/organizations/mine/approvals/<int:pk>/<str:action>", ApprovalActionView.as_view(), name="org_approval_action"),

    # Internal endpoint for AI orchestrator to query member spend limits
    path("api/internal/org-member-context/<str:user_id>", _OrgMemberContextView.as_view(), name="org_member_context"),
]
