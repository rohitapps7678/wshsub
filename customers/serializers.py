from rest_framework import serializers
from .models import User, VehicleType, Plan, Subscription, Vehicle


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone', 'username', 'is_customer', 'is_vendor']


class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleType
        fields = ['id', 'name']


class PlanSerializer(serializers.ModelSerializer):
    vehicle_type = VehicleTypeSerializer(read_only=True)
    vehicle_type_id = serializers.PrimaryKeyRelatedField(
        queryset=VehicleType.objects.all(),
        source='vehicle_type',
        write_only=True
    )

    class Meta:
        model = Plan
        fields = ['id', 'name', 'washes', 'price', 'vehicle_type', 'vehicle_type_id']


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    customer = UserSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'customer', 'plan', 'remaining_washes',
            'start_date', 'is_active', 'qr_string',
            'vehicle_number', 'vehicle_number_updated_at'   # ← नया
        ]
        read_only_fields = ['remaining_washes', 'start_date', 'is_active', 'qr_string', 'vehicle_number_updated_at']

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['id', 'number', 'type', 'is_verified', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified']