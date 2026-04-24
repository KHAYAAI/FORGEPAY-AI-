from rest_framework import generics, permissions

from organization.models import OrganizationMember, SupplierContract
from organization.serializers import SupplierContractSerializer


class SupplierContractListView(generics.ListCreateAPIView):
    """
    GET  /api/organizations/mine/contracts  — list supplier contracts
    POST                                    — add a new contract (admin/manager only)
    """

    serializer_class = SupplierContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            org = self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            return SupplierContract.objects.none()
        return org.supplier_contracts.order_by("-is_preferred", "supplier_name")

    def perform_create(self, serializer):
        try:
            membership = self.request.user.org_membership
        except OrganizationMember.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of any organization.")
        if membership.role not in ("admin", "procurement_manager"):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins and procurement managers can add contracts.")
        serializer.save(organization=membership.organization)


class SupplierContractDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/organizations/mine/contracts/<id>"""

    serializer_class = SupplierContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            org = self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            return SupplierContract.objects.none()
        return org.supplier_contracts.all()
