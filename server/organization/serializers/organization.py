from rest_framework import serializers

from organization.models import Organization, OrganizationMember


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "slug", "spend_limit_per_order", "spend_limit_per_month",
            "subscription_tier", "country_code", "currency_code",
            "is_active", "created_at", "member_count",
        ]
        read_only_fields = ["id", "slug", "created_at", "member_count"]

    def get_member_count(self, obj: Organization) -> int:
        return obj.members.count()


class OrganizationMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    effective_spend_limit = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrganizationMember
        fields = [
            "id", "user", "user_email", "role",
            "spend_limit_override", "effective_spend_limit", "joined_at",
        ]
        read_only_fields = ["id", "joined_at", "user_email", "effective_spend_limit"]
