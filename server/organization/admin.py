from django.contrib import admin

from organization.models import ApprovalRequest, Organization, OrganizationMember, SupplierContract


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "subscription_tier", "country_code", "is_active", "created_at"]
    list_filter = ["subscription_tier", "country_code", "is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = ["slug", "created_at", "updated_at"]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "spend_limit_override", "joined_at"]
    list_filter = ["role", "organization"]
    search_fields = ["user__email", "organization__name"]
    autocomplete_fields = ["user", "organization"]


@admin.register(SupplierContract)
class SupplierContractAdmin(admin.ModelAdmin):
    list_display = ["supplier_name", "organization", "is_preferred", "is_exclusive", "valid_from", "valid_until"]
    list_filter = ["is_preferred", "is_exclusive", "organization"]
    search_fields = ["supplier_name", "supplier_id", "organization__name"]


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ["pk", "requester", "organization", "order_total_cents", "status", "created_at"]
    list_filter = ["status", "organization"]
    search_fields = ["requester__email", "order_id"]
    readonly_fields = ["created_at", "resolved_at"]
