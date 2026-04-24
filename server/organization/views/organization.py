from rest_framework import generics, permissions, status
from rest_framework.response import Response

from organization.models import Organization, OrganizationMember
from organization.serializers import OrganizationMemberSerializer, OrganizationSerializer


class IsOrgAdmin(permissions.BasePermission):
    """Grants access only to org admins."""

    def has_object_permission(self, request, view, obj):
        try:
            membership = request.user.org_membership
        except OrganizationMember.DoesNotExist:
            return False
        if isinstance(obj, Organization):
            return membership.organization == obj and membership.role == "admin"
        return False


class OrganizationView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/organizations/mine   — return the calling user's organization
    PATCH/PUT                      — update org settings (admin only)
    """

    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        try:
            return self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("You are not a member of any organization.")

    def update(self, request, *args, **kwargs):
        org = self.get_object()
        try:
            if request.user.org_membership.role != "admin":
                return Response({"detail": "Only org admins can update organization settings."},
                                status=status.HTTP_403_FORBIDDEN)
        except OrganizationMember.DoesNotExist:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


class OrganizationMembersView(generics.ListCreateAPIView):
    """
    GET  /api/organizations/mine/members  — list all members
    POST                                  — invite a new member (admin only)
    """

    serializer_class = OrganizationMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            org = self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            return OrganizationMember.objects.none()
        return org.members.select_related("user").order_by("role", "user__email")

    def perform_create(self, serializer):
        try:
            membership = self.request.user.org_membership
        except OrganizationMember.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a member of any organization.")
        if membership.role != "admin":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only org admins can add members.")
        serializer.save(organization=membership.organization)


class MemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/organizations/mine/members/<id>
    """

    serializer_class = OrganizationMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            org = self.request.user.org_membership.organization
        except OrganizationMember.DoesNotExist:
            return OrganizationMember.objects.none()
        return org.members.all()
