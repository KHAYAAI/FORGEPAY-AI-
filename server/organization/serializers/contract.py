from rest_framework import serializers

from organization.models import SupplierContract


class SupplierContractSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.SerializerMethodField()

    class Meta:
        model = SupplierContract
        fields = [
            "id", "supplier_id", "supplier_name", "is_preferred", "is_exclusive",
            "contract_terms", "valid_from", "valid_until",
            "is_currently_active", "created_at",
        ]
        read_only_fields = ["id", "created_at", "is_currently_active"]

    def get_is_currently_active(self, obj: SupplierContract) -> bool:
        return obj.is_active()
