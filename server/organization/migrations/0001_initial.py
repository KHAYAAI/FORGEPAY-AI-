from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Legal entity name, e.g. 'Maruti Suzuki India Ltd'", max_length=256)),
                ("slug", models.SlugField(help_text="URL-safe identifier, auto-generated from name", unique=True)),
                ("spend_limit_per_order", models.PositiveIntegerField(default=5000000, help_text="Maximum single-order value in ZAR cents before approval is required")),
                ("spend_limit_per_month", models.PositiveIntegerField(default=50000000, help_text="Monthly spend cap in ZAR cents across all members")),
                ("subscription_tier", models.CharField(choices=[("starter", "Starter"), ("growth", "Growth"), ("enterprise", "Enterprise")], default="starter", max_length=32)),
                ("country_code", models.CharField(default="ZA", help_text="ISO 3166-1 alpha-2", max_length=2)),
                ("currency_code", models.CharField(default="ZAR", help_text="ISO 4217", max_length=3)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="OrganizationMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("admin", "Admin"), ("procurement_manager", "Procurement Manager"), ("buyer", "Buyer"), ("viewer", "Viewer")], default="buyer", max_length=32)),
                ("spend_limit_override", models.PositiveIntegerField(blank=True, help_text="Per-order spend limit override in ZAR cents. Null = use org default.", null=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="members", to="organization.organization")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="org_membership", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SupplierContract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("supplier_id", models.CharField(help_text="Medusa/VocalMarket vendor ID", max_length=128)),
                ("supplier_name", models.CharField(max_length=256)),
                ("is_preferred", models.BooleanField(default=False, help_text="Preferred suppliers are highlighted in Hermes recommendations")),
                ("is_exclusive", models.BooleanField(default=False, help_text="If True, Hermes will warn before recommending a non-contracted competitor")),
                ("contract_terms", models.JSONField(blank=True, default=dict, help_text="Volume tiers, payment terms, SLAs, etc.")),
                ("valid_from", models.DateField()),
                ("valid_until", models.DateField(blank=True, help_text="Null = open-ended contract", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supplier_contracts", to="organization.organization")),
            ],
            options={"ordering": ["-is_preferred", "supplier_name"]},
        ),
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("order_id", models.CharField(blank=True, help_text="Medusa order ID once created", max_length=128)),
                ("order_total_cents", models.PositiveIntegerField(help_text="Total in ZAR cents")),
                ("order_items", models.JSONField(help_text="Snapshot of items at time of request")),
                ("conversation_id", models.CharField(blank=True, help_text="Hermes conversation to resume when order is approved", max_length=256)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="pending", max_length=32)),
                ("requester_notes", models.TextField(blank=True, help_text="Business justification from requester")),
                ("approver_notes", models.TextField(blank=True)),
                ("expires_at", models.DateTimeField(blank=True, help_text="Approval requests expire after 48h if not acted on", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approval_requests", to="organization.organization")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="submitted_approvals", to=settings.AUTH_USER_MODEL)),
                ("approver", models.ForeignKey(blank=True, help_text="Set when the request is approved or rejected", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="acted_on_approvals", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="organizationmember",
            constraint=models.UniqueConstraint(fields=["organization", "user"], name="unique_org_member"),
        ),
        migrations.AddConstraint(
            model_name="suppliercontract",
            constraint=models.UniqueConstraint(fields=["organization", "supplier_id"], name="unique_org_supplier_contract"),
        ),
        migrations.AddIndex(
            model_name="approvalrequest",
            index=models.Index(fields=["organization", "status"], name="org_approval_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="approvalrequest",
            index=models.Index(fields=["requester", "status"], name="org_approval_requester_status_idx"),
        ),
    ]
