import pytest
from datetime import date, timedelta
from model_bakery import baker
from rest_framework.test import APIClient

from account.models import User
from organization.models import (
    ApprovalRequest,
    ApprovalStatus,
    MemberRole,
    Organization,
    OrganizationMember,
    SupplierContract,
)


@pytest.fixture
def org():
    return baker.make(Organization, name="Test OEM", currency_code="ZAR", spend_limit_per_order=5_000_000)


@pytest.fixture
def admin_user(org):
    user = baker.make(User)
    baker.make(OrganizationMember, user=user, organization=org, role=MemberRole.ADMIN)
    return user


@pytest.fixture
def buyer_user(org):
    user = baker.make(User)
    baker.make(OrganizationMember, user=user, organization=org, role=MemberRole.BUYER)
    return user


@pytest.fixture
def manager_user(org):
    user = baker.make(User)
    baker.make(OrganizationMember, user=user, organization=org, role=MemberRole.PROCUREMENT_MANAGER)
    return user


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def manager_client(manager_user):
    client = APIClient()
    client.force_authenticate(user=manager_user)
    return client


@pytest.mark.django_db
class TestOrganizationView:
    def test_get_own_org(self, admin_client, org):
        resp = admin_client.get("/api/organizations/mine")
        assert resp.status_code == 200
        assert resp.data["name"] == org.name

    def test_unauthenticated_rejected(self):
        resp = APIClient().get("/api/organizations/mine")
        assert resp.status_code == 401

    def test_non_member_gets_404(self):
        outsider = baker.make(User)
        client = APIClient()
        client.force_authenticate(user=outsider)
        resp = client.get("/api/organizations/mine")
        assert resp.status_code == 404

    def test_admin_can_update_spend_limit(self, admin_client, org):
        resp = admin_client.patch("/api/organizations/mine", {"spend_limit_per_order": 10_000_000}, format="json")
        assert resp.status_code == 200
        org.refresh_from_db()
        assert org.spend_limit_per_order == 10_000_000

    def test_buyer_cannot_update_org(self, buyer_client):
        resp = buyer_client.patch("/api/organizations/mine", {"spend_limit_per_order": 1}, format="json")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestMembersView:
    def test_admin_can_list_members(self, admin_client, org, admin_user, buyer_user):
        resp = admin_client.get("/api/organizations/mine/members")
        assert resp.status_code == 200
        ids = [m["user"] for m in resp.data["results"]]
        assert admin_user.pk in ids
        assert buyer_user.pk in ids

    def test_buyer_can_list_members(self, buyer_client):
        resp = buyer_client.get("/api/organizations/mine/members")
        assert resp.status_code == 200

    def test_admin_can_add_member(self, admin_client, org):
        new_user = baker.make(User)
        resp = admin_client.post(
            "/api/organizations/mine/members",
            {"user": new_user.pk, "role": "buyer"},
            format="json",
        )
        assert resp.status_code == 201
        assert OrganizationMember.objects.filter(user=new_user, organization=org).exists()

    def test_buyer_cannot_add_member(self, buyer_client):
        new_user = baker.make(User)
        resp = buyer_client.post(
            "/api/organizations/mine/members",
            {"user": new_user.pk, "role": "buyer"},
            format="json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestApprovalWorkflow:
    def _make_approval(self, org, requester):
        return baker.make(
            ApprovalRequest,
            organization=org,
            requester=requester,
            order_total_cents=6_000_000,
            order_items=[{"sku": "STEEL-ROD", "qty": 500, "unit_price": 12000}],
            status=ApprovalStatus.PENDING,
            expires_at=None,
        )

    def test_buyer_can_create_approval_request(self, buyer_client, org):
        resp = buyer_client.post(
            "/api/organizations/mine/approvals",
            {
                "order_total_cents": 6_000_000,
                "order_items": [{"sku": "STEEL-ROD", "qty": 500}],
                "requester_notes": "Urgent for Q2 production run",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "pending"

    def test_buyer_sees_only_own_approvals(self, buyer_client, buyer_user, org, manager_user):
        other_user = baker.make(User)
        baker.make(OrganizationMember, user=other_user, organization=org, role=MemberRole.BUYER)
        own = self._make_approval(org, buyer_user)
        other = self._make_approval(org, other_user)
        resp = buyer_client.get("/api/organizations/mine/approvals")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.data["results"]]
        assert own.pk in ids
        assert other.pk not in ids

    def test_manager_sees_all_pending(self, manager_client, org, buyer_user, manager_user):
        a1 = self._make_approval(org, buyer_user)
        a2 = self._make_approval(org, manager_user)
        resp = manager_client.get("/api/organizations/mine/approvals")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.data["results"]]
        assert a1.pk in ids
        assert a2.pk in ids

    def test_manager_can_approve(self, manager_client, org, buyer_user):
        approval = self._make_approval(org, buyer_user)
        resp = manager_client.post(
            f"/api/organizations/mine/approvals/{approval.pk}/approve",
            {"notes": "Approved for Q2"},
            format="json",
        )
        assert resp.status_code == 200
        approval.refresh_from_db()
        assert approval.status == ApprovalStatus.APPROVED

    def test_manager_can_reject(self, manager_client, org, buyer_user):
        approval = self._make_approval(org, buyer_user)
        resp = manager_client.post(
            f"/api/organizations/mine/approvals/{approval.pk}/reject",
            {"notes": "Over monthly budget"},
            format="json",
        )
        assert resp.status_code == 200
        approval.refresh_from_db()
        assert approval.status == ApprovalStatus.REJECTED

    def test_buyer_cannot_approve(self, buyer_client, org, buyer_user):
        approval = self._make_approval(org, buyer_user)
        resp = buyer_client.post(
            f"/api/organizations/mine/approvals/{approval.pk}/approve",
            {},
            format="json",
        )
        assert resp.status_code == 404  # 404 because can_approve() returns False

    def test_invalid_action_returns_400(self, manager_client, org, buyer_user):
        approval = self._make_approval(org, buyer_user)
        resp = manager_client.post(
            f"/api/organizations/mine/approvals/{approval.pk}/cancel",
            {},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestSupplierContracts:
    def test_admin_can_add_contract(self, admin_client, org):
        resp = admin_client.post(
            "/api/organizations/mine/contracts",
            {
                "supplier_id": "sup-001",
                "supplier_name": "Steel SA (Pty) Ltd",
                "is_preferred": True,
                "is_exclusive": False,
                "contract_terms": {"payment_days": 30},
                "valid_from": str(date.today()),
            },
            format="json",
        )
        assert resp.status_code == 201
        assert SupplierContract.objects.filter(organization=org, supplier_id="sup-001").exists()

    def test_buyer_cannot_add_contract(self, buyer_client):
        resp = buyer_client.post(
            "/api/organizations/mine/contracts",
            {
                "supplier_id": "sup-999",
                "supplier_name": "Rogue Supplier",
                "valid_from": str(date.today()),
            },
            format="json",
        )
        assert resp.status_code == 403

    def test_list_contracts_returns_org_contracts_only(self, admin_client, org):
        baker.make(SupplierContract, organization=org, supplier_id="sup-A", valid_from=date.today())
        other_org = baker.make(Organization)
        baker.make(SupplierContract, organization=other_org, supplier_id="sup-B", valid_from=date.today())
        resp = admin_client.get("/api/organizations/mine/contracts")
        assert resp.status_code == 200
        supplier_ids = [c["supplier_id"] for c in resp.data["results"]]
        assert "sup-A" in supplier_ids
        assert "sup-B" not in supplier_ids
