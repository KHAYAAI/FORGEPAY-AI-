import pytest
from django.utils import timezone
from model_bakery import baker

from organization.models import (
    ApprovalRequest,
    ApprovalStatus,
    MemberRole,
    Organization,
    OrganizationMember,
    SupplierContract,
)


@pytest.mark.django_db
class TestOrganization:
    def test_slug_auto_generated_from_name(self):
        org = baker.make(Organization, name="Maruti Suzuki India Ltd", slug="")
        org.slug = ""
        org.save()
        assert org.slug == "maruti-suzuki-india-ltd"

    def test_slug_not_overwritten_if_already_set(self):
        org = Organization(name="Tata Motors", slug="tata-custom")
        org.save()
        assert org.slug == "tata-custom"

    def test_default_spend_limits_in_cents(self):
        org = baker.make(Organization)
        assert org.spend_limit_per_order == 5_000_000   # R50,000
        assert org.spend_limit_per_month == 50_000_000  # R500,000

    def test_default_currency_is_zar(self):
        org = baker.make(Organization)
        assert org.currency_code == "ZAR"
        assert org.country_code == "ZA"

    def test_str(self):
        org = baker.make(Organization, name="Acme Corp")
        assert str(org) == "Acme Corp"


@pytest.mark.django_db
class TestOrganizationMember:
    def test_effective_spend_limit_uses_org_default_when_no_override(self):
        org = baker.make(Organization, spend_limit_per_order=1_000_000)
        member = baker.make(OrganizationMember, organization=org, spend_limit_override=None)
        assert member.effective_spend_limit() == 1_000_000

    def test_effective_spend_limit_uses_override_when_set(self):
        org = baker.make(Organization, spend_limit_per_order=1_000_000)
        member = baker.make(OrganizationMember, organization=org, spend_limit_override=250_000)
        assert member.effective_spend_limit() == 250_000

    def test_can_approve_admin(self):
        member = baker.make(OrganizationMember, role=MemberRole.ADMIN)
        assert member.can_approve() is True

    def test_can_approve_procurement_manager(self):
        member = baker.make(OrganizationMember, role=MemberRole.PROCUREMENT_MANAGER)
        assert member.can_approve() is True

    def test_cannot_approve_buyer(self):
        member = baker.make(OrganizationMember, role=MemberRole.BUYER)
        assert member.can_approve() is False

    def test_cannot_approve_viewer(self):
        member = baker.make(OrganizationMember, role=MemberRole.VIEWER)
        assert member.can_approve() is False

    def test_one_org_per_user_enforced(self):
        from django.db import IntegrityError
        user = baker.make("account.User")
        org1 = baker.make(Organization)
        org2 = baker.make(Organization)
        baker.make(OrganizationMember, user=user, organization=org1)
        with pytest.raises(IntegrityError):
            OrganizationMember.objects.create(user=user, organization=org2, role=MemberRole.BUYER)


@pytest.mark.django_db
class TestSupplierContract:
    def test_is_active_within_validity_window(self):
        from datetime import date, timedelta
        today = date.today()
        contract = baker.make(
            SupplierContract,
            valid_from=today - timedelta(days=30),
            valid_until=today + timedelta(days=30),
        )
        assert contract.is_active() is True

    def test_is_active_open_ended_contract(self):
        from datetime import date, timedelta
        contract = baker.make(
            SupplierContract,
            valid_from=date.today() - timedelta(days=10),
            valid_until=None,
        )
        assert contract.is_active() is True

    def test_is_not_active_future_start(self):
        from datetime import date, timedelta
        contract = baker.make(
            SupplierContract,
            valid_from=date.today() + timedelta(days=5),
            valid_until=None,
        )
        assert contract.is_active() is False

    def test_is_not_active_past_end(self):
        from datetime import date, timedelta
        contract = baker.make(
            SupplierContract,
            valid_from=date.today() - timedelta(days=60),
            valid_until=date.today() - timedelta(days=1),
        )
        assert contract.is_active() is False

    def test_unique_constraint_org_supplier(self):
        from django.db import IntegrityError
        from datetime import date
        org = baker.make(Organization)
        baker.make(SupplierContract, organization=org, supplier_id="sup-001", valid_from=date.today())
        with pytest.raises(IntegrityError):
            SupplierContract.objects.create(
                organization=org,
                supplier_id="sup-001",
                supplier_name="Duplicate",
                valid_from=date.today(),
            )


@pytest.mark.django_db
class TestApprovalRequest:
    def _make_approval(self, **kwargs):
        org = baker.make(Organization)
        requester = baker.make("account.User")
        return baker.make(
            ApprovalRequest,
            organization=org,
            requester=requester,
            order_total_cents=1_000_000,
            order_items=[{"sku": "BOLT-M8", "qty": 100}],
            status=ApprovalStatus.PENDING,
            **kwargs,
        )

    def test_approve_sets_status_and_approver(self):
        approval = self._make_approval()
        approver = baker.make("account.User")
        approval.approve(approver, notes="Looks good")
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.approver == approver
        assert approval.approver_notes == "Looks good"
        assert approval.resolved_at is not None

    def test_reject_sets_status_and_approver(self):
        approval = self._make_approval()
        approver = baker.make("account.User")
        approval.reject(approver, notes="Over budget")
        assert approval.status == ApprovalStatus.REJECTED
        assert approval.approver == approver
        assert approval.approver_notes == "Over budget"

    def test_expire_sets_expired_status(self):
        approval = self._make_approval()
        approval.expire()
        assert approval.status == ApprovalStatus.EXPIRED
        assert approval.resolved_at is not None

    def test_approved_state_persisted(self):
        approval = self._make_approval()
        approver = baker.make("account.User")
        approval.approve(approver)
        refreshed = ApprovalRequest.objects.get(pk=approval.pk)
        assert refreshed.status == ApprovalStatus.APPROVED
