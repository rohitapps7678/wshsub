from rest_framework import serializers
from django.utils import timezone
from django.db.models import Count

from .models import Vendor
from customers.models import User, WashHistory
from customers.serializers import UserSerializer


class VendorSerializer(serializers.ModelSerializer):
    """
    मुख्य serializer - vendor list, detail, profile के लिए इस्तेमाल होता है
    Admin panel में extra stats दिखाने के लिए annotated fields
    """
    user = UserSerializer(read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    
    # Admin / dashboard के लिए extra computed fields
    # Note: इन्हें view में .annotate() करके populate करना होगा
    total_washes = serializers.IntegerField(read_only=True, default=0)
    today_washes = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Vendor
        fields = [
            'id',
            'user',
            'user_phone',
            'center_name',
            'address',
            'latitude',
            'longitude',
            'is_approved',
            'is_active',
            'created_at',
            'updated_at',
            # extra stats
            'total_washes',
            'today_washes',
            # registration code fields (admin/debug के लिए optional दिखा सकते हैं)
            'registration_code',
            'registration_code_used',
            'registration_code_created_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_phone',
            'created_at',
            'updated_at',
            'total_washes',
            'today_washes',
            'is_approved',                  # admin ही बदल सकता है
            'registration_code',
            'registration_code_used',
            'registration_code_created_at',
        ]

# vendors/serializers.py
class WashHistoryVendorSerializer(serializers.ModelSerializer):
    customer_phone = serializers.CharField(source='subscription.customer.phone', read_only=True)
    customer_name = serializers.CharField(source='subscription.customer.name', read_only=True, allow_null=True)
    plan_name = serializers.CharField(source='subscription.plan.name', read_only=True)
    
    # vehicle_number सीधे CharField से ले रहे हैं (related नहीं है)
    vehicle_number = serializers.CharField(source='subscription.vehicle_number', read_only=True, allow_null=True)
    
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = WashHistory
        fields = [
            'id',
            'wash_time',
            'time_ago',
            'customer_phone',
            'customer_name',
            'plan_name',
            'vehicle_number',
            'notes',
            'latitude',
            'longitude',
        ]

    def get_time_ago(self, obj):
        delta = timezone.now() - obj.wash_time
        days = delta.days
        seconds = delta.seconds

        if days > 0:
            return f"{days} day{'s' if days > 1 else ''} ago"
        elif seconds >= 3600:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"{minutes} min{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"

class VendorRegisterSerializer(serializers.ModelSerializer):
    """
    Vendor registration के लिए serializer
    अब admin_password की जगह registration_code इस्तेमाल होगा
    Code को DB में store करके validate करेंगे (Vendor model में fields मौजूद हैं)
    """
    phone = serializers.CharField(max_length=15, write_only=True)
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    registration_code = serializers.CharField(
        max_length=32,
        write_only=True,
        help_text="Admin द्वारा दिया गया registration code"
    )
    center_name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Vendor
        fields = [
            'phone',
            'password',
            'registration_code',
            'center_name',
            'address',
            'latitude',
            'longitude',
        ]

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("यह मोबाइल नंबर पहले से रजिस्टर्ड है।")
        return value

    def validate_registration_code(self, value):
        """
        registration_code की validity चेक करें
        - मौजूद होना चाहिए
        - पहले इस्तेमाल नहीं हुआ होना चाहिए
        - समय सीमा के अंदर होना चाहिए (उदाहरण: 72 घंटे)
        """
        try:
            vendor = Vendor.objects.get(
                registration_code=value,
                registration_code_used=False
            )
        except Vendor.DoesNotExist:
            raise serializers.ValidationError("यह registration code गलत है या इस्तेमाल हो चुका है।")

        # समय सीमा चेक (उदाहरण: 72 घंटे)
        if vendor.registration_code_created_at:
            expiry_time = vendor.registration_code_created_at + timezone.timedelta(hours=72)
            if timezone.now() > expiry_time:
                raise serializers.ValidationError("यह registration code expire हो चुका है।")

        # context में vendor object डाल दें ताकि create में इस्तेमाल हो सके
        self.context['pending_vendor'] = vendor
        return value

    def create(self, validated_data):
        phone = validated_data.pop('phone')
        password = validated_data.pop('password')
        registration_code = validated_data.pop('registration_code')

        # pending vendor object (जिसमें code match हुआ था)
        pending_vendor = self.context.get('pending_vendor')

        if not pending_vendor:
            # theoretically नहीं होना चाहिए, लेकिन safety
            raise serializers.ValidationError("Registration code validation failed.")

        # User बनाओ
        user = User.objects.create_user(
            phone=phone,
            username=phone,
            password=password,
            is_vendor=True,
            is_customer=False
        )

        # पहले से बना pending Vendor object अपडेट करो
        pending_vendor.user = user
        pending_vendor.center_name = validated_data.get('center_name')
        pending_vendor.address = validated_data.get('address', '')
        pending_vendor.latitude = validated_data.get('latitude')
        pending_vendor.longitude = validated_data.get('longitude')
        pending_vendor.is_active = True
        # is_approved अभी False रहेगा — admin approve करेगा

        # registration code इस्तेमाल mark करो
        pending_vendor.registration_code_used = True
        pending_vendor.save()

        return pending_vendor


class AdminVendorCreateSerializer(serializers.ModelSerializer):
    """
    पुराना serializer — अगर कभी direct create की जरूरत पड़े
    (अभी ज्यादातर मामलों में generate-code + self-register flow इस्तेमाल होगा)
    """
    phone = serializers.CharField(max_length=15, write_only=True)
    password = serializers.CharField(write_only=True, min_length=6)

    center_name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Vendor
        fields = [
            'phone',
            'password',
            'center_name',
            'address',
            'latitude',
            'longitude'
        ]