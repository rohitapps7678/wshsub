from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from django.db import transaction
from django.db.models import Q, Count
from datetime import datetime

from .models import User, VehicleType, Plan, Subscription, WashHistory, Vehicle
from .serializers import (
    UserSerializer, VehicleTypeSerializer, PlanSerializer,
    SubscriptionSerializer, VehicleSerializer
)
from .utils import attach_qr_to_subscription, get_nearby_vendors
from .permissions import IsSuperAdmin   # अगर अलग फाइल में है तो import करें


# ────────────────────────────────────────────────
#           CUSTOMER PUBLIC / AUTHENTICATED VIEWS
# ────────────────────────────────────────────────

class CustomerRegisterView(APIView):  # कोई permission नहीं चाहिए (public endpoint)

    def post(self, request):
        phone = request.data.get('phone')
        password = request.data.get('password')
        name = request.data.get('name', '').strip()                     # नया
        preferred_language = request.data.get('preferred_language', 'en')  # नया

        if not phone or not password:
            return Response({"error": "phone and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(phone=phone).exists():
            return Response({"error": "Phone number already registered"}, status=status.HTTP_400_BAD_REQUEST)

        # नया यूजर बनाएं
        user = User.objects.create_user(
            phone=phone,
            username=phone,  # या कोई और logic
            password=password,
            name=name,                           # ← save करो
            preferred_language=preferred_language,  # ← save करो
            is_customer=True,
            is_vendor=False
        )

        # ऑप्शनल: JWT token भी लौटा सकते हैं (अगर auto-login चाहते हैं)
        refresh = RefreshToken.for_user(user)

        return Response({
            "message": "Registration successful",
            "user": UserSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

class CustomerLoginView(APIView):
    def post(self, request):
        phone = request.data.get('phone')
        password = request.data.get('password')

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"error": "Invalid credentials"}, status=401)

        if not user.check_password(password):
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data
        })


class VehicleTypeListView(APIView):
    def get(self, request):
        qs = VehicleType.objects.all()
        return Response(VehicleTypeSerializer(qs, many=True).data)


class PlanListView(APIView):
    def get(self, request):
        qs = Plan.objects.all()
        return Response(PlanSerializer(qs, many=True).data)


class MyActiveSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sub = Subscription.objects.filter(
            customer=request.user,
            is_active=True
        ).select_related('plan', 'plan__vehicle_type').order_by('-start_date').first()

        if not sub:
            return Response({"detail": "No active subscription found"}, status=404)

        return Response(SubscriptionSerializer(sub).data)

class BuySubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        plan_id = request.data.get('plan_id')
        vehicle_number = request.data.get('vehicle_number')  # नया फील्ड

        if not plan_id:
            return Response({"error": "plan_id is required"}, status=400)

        if not vehicle_number or not str(vehicle_number).strip():
            return Response({"error": "Vehicle number is required"}, status=400)

        vehicle_number = str(vehicle_number).strip().upper()

        # वैकल्पिक: भारतीय vehicle number format check (MH12AB1234 जैसा)
        # import re
        # if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,2}[0-9]{4}$', vehicle_number):
        #     return Response({"error": "Invalid vehicle number format (e.g. MH12AB1234)"}, status=400)

        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return Response({"error": "Invalid plan"}, status=404)

        # TODO: Payment gateway (Razorpay/Stripe) integration
        # अभी assume payment success

        sub = Subscription.objects.create(
            customer=request.user,
            plan=plan,
            remaining_washes=plan.washes,
            is_active=True,
            vehicle_number=vehicle_number,
            vehicle_number_updated_at=datetime.now()   # timestamp डाल दिया
        )

        attach_qr_to_subscription(sub)

        return Response({
            "message": "Subscription activated successfully",
            "subscription": SubscriptionSerializer(sub).data
        }, status=201)


class MyQRView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sub = Subscription.objects.filter(
            customer=request.user,
            is_active=True
        ).order_by('-start_date').first()

        if not sub:
            return Response({"error": "No active subscription"}, status=404)

        data = {
            "qr_string": str(sub.qr_string),
        }
        if sub.qr_image:
            data["qr_image_url"] = request.build_absolute_uri(sub.qr_image.url)

        return Response(data)


class WashHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        history = WashHistory.objects.filter(
            subscription__customer=request.user
        ).select_related('subscription__plan', 'subscription__plan__vehicle_type', 'vendor').order_by('-wash_time')[:30]

        data = [
            {
                "id": h.id,
                "date": h.wash_time.strftime("%d %b %Y, %H:%M"),
                "center": h.vendor.center_name if h.vendor else "Unknown",
                "vehicle": h.subscription.plan.vehicle_type.name if h.subscription.plan.vehicle_type else "N/A",
                "plan": h.subscription.plan.name,
                "remaining_after": h.subscription.remaining_washes,
                "notes": h.notes[:120] if h.notes else "",
                "location": f"{h.latitude or 'N/A'}, {h.longitude or 'N/A'}"
            }
            for h in history
        ]

        return Response({"history": data, "total_count": history.count()})


class NearbyWashingCentersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            lat = float(request.query_params.get('lat'))
            lon = float(request.query_params.get('lon'))
        except (TypeError, ValueError):
            return Response({"error": "Valid lat and lon query parameters required"}, status=400)

        nearby = get_nearby_vendors(lat, lon, max_km=20.0, limit=10)
        return Response({"centers": nearby})


# ────────────────────────────────────────────────
#           ADMIN ONLY ENDPOINTS (Superuser)
# ────────────────────────────────────────────────

class AdminCustomerListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        customers = User.objects.filter(
            is_customer=True,
            is_vendor=False
        ).annotate(
            subscription_count=Count('subscriptions'),
            active_subscription_count=Count('subscriptions', filter=Q(subscriptions__is_active=True)),
            total_washes=Count('subscriptions__wash_history')
        ).order_by('-date_joined')

        # Optional filters
        search = request.query_params.get('search')
        if search:
            customers = customers.filter(
                Q(phone__icontains=search) | Q(username__icontains=search)
            )

        data = [
            {
                "id": c.id,
                "phone": c.phone,
                "joined": c.date_joined.strftime("%d %b %Y"),
                "subscriptions": c.subscription_count,
                "active_subs": c.active_subscription_count,
                "total_washes": c.total_washes,
                "is_active": c.is_active
            }
            for c in customers[:100]   # limit for safety
        ]

        return Response({
            "count": len(data),
            "customers": data
        })

class AdminCustomerDetailView(APIView):
    """
    Super admin के लिए किसी एक customer की पूरी डिटेल्स लौटाता है:
    - Customer basic info
    - All subscriptions (with plan & vehicle details)
    - Active subscription (if any) — separately highlighted
    - Recent wash history
    - Summary stats
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk):
        try:
            customer = User.objects.select_related().get(
                id=pk,
                is_customer=True
            )
        except User.DoesNotExist:
            return Response(
                {"error": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # All subscriptions (latest first)
        subscriptions = Subscription.objects.filter(
            customer=customer
        ).select_related(
            'plan',
            'plan__vehicle_type',
            'plan__vendor'
        ).order_by('-start_date')

        # Active subscription (latest one if multiple — normally should be 0 or 1)
        active_subscription = subscriptions.filter(is_active=True).order_by('-start_date').first()

        # Wash history — last 50 records
        history_qs = WashHistory.objects.filter(
            subscription__customer=customer
        ).select_related(
            'vendor',
            'subscription__plan'
        ).order_by('-wash_time')[:50]

        # Serializers
        customer_data = UserSerializer(customer).data
        subscriptions_data = SubscriptionSerializer(subscriptions, many=True).data
        history_data = [
            {
                "id": h.id,
                "date": h.wash_time.strftime("%d %b %Y, %H:%M"),
                "vendor": h.vendor.center_name if h.vendor else "Unknown Center",
                "vendor_id": h.vendor.id if h.vendor else None,
                "plan": h.subscription.plan.name,
                "vehicle_type": h.subscription.plan.vehicle_type.name if h.subscription.plan.vehicle_type else "N/A",
                "remaining_after_wash": h.subscription.remaining_washes,
                "notes": h.notes[:120] if h.notes else "",
                "location": f"{h.latitude:.5f}, {h.longitude:.5f}" if h.latitude and h.longitude else "N/A"
            }
            for h in history_qs
        ]

        # Active subscription data (if exists)
        active_sub_data = None
        if active_subscription:
            active_sub_data = SubscriptionSerializer(active_subscription).data
            # Extra clarity for frontend
            active_sub_data["vehicle_type_name"] = active_subscription.plan.vehicle_type.name if active_subscription.plan.vehicle_type else None
            active_sub_data["vendor_name"] = active_subscription.plan.vendor.center_name if active_subscription.plan.vendor else None

        return Response({
            "customer": {
                **customer_data,
                "date_joined": customer.date_joined.isoformat() if customer.date_joined else None,
                "last_login": customer.last_login.isoformat() if customer.last_login else None,
            },
            "active_subscription": active_sub_data,
            "subscriptions": subscriptions_data,
            "wash_history": history_data,
            "stats": {
                "total_subscriptions": subscriptions.count(),
                "active_subscriptions_count": subscriptions.filter(is_active=True).count(),
                "lifetime_washes": WashHistory.objects.filter(
                    subscription__customer=customer
                ).count(),  # full count, not just last 50
                "recent_washes_shown": len(history_data),
            }
        }, status=status.HTTP_200_OK)


class AdminCustomerUpdateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def patch(self, request, pk):
        try:
            customer = User.objects.get(id=pk, is_customer=True)
        except User.DoesNotExist:
            return Response({"error": "Customer not found"}, status=404)

        # Allowed fields to update
        allowed_fields = ['is_active', 'phone', 'username']
        for field in allowed_fields:
            if field in request.data:
                if field == 'phone' and request.data['phone'] != customer.phone:
                    if User.objects.filter(phone=request.data['phone']).exclude(id=pk).exists():
                        return Response({"error": "Phone already in use"}, status=400)
                setattr(customer, field, request.data[field])

        customer.save(update_fields=allowed_fields)
        return Response(UserSerializer(customer).data)

class CustomerPlansView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):

        plans = (
            Plan.objects
            .select_related("vehicle_type", "vendor")
            .order_by("price")
        )

        data = []

        for p in plans:

            data.append({
                "id": p.id,
                "name": p.name,
                "price": str(p.price),
                "washes": p.washes,
                "vehicle_type": {
                    "name": p.vehicle_type.name
                },
                "duration_type": p.duration_type,
                "vendor": {
                    "id": p.vendor.id,
                    "center_name": p.vendor.center_name
                }
            })

        return Response(data)

class BuyPlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get("plan_id")
        vehicle_number = request.data.get("vehicle_number")  # ← यहाँ से लेना जरूरी

        if not plan_id:
            return Response({"error": "plan_id is required"}, status=400)

        if not vehicle_number or not str(vehicle_number).strip():
            return Response({"error": "Vehicle number is required"}, status=400)

        vehicle_number = str(vehicle_number).strip().upper()

        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return Response({"error": "Invalid plan"}, status=404)

        sub = Subscription.objects.create(
            customer=request.user,
            plan=plan,
            remaining_washes=plan.washes,
            vehicle_number=vehicle_number,                    # ← यहाँ save करो
            vehicle_number_updated_at=datetime.now()          # ← timestamp
        )

        attach_qr_to_subscription(sub)

        return Response({
            "message": "Subscription activated",
            "subscription_id": sub.id,
            "remaining_washes": sub.remaining_washes,
            "vehicle_number": sub.vehicle_number,
            "subscription": SubscriptionSerializer(sub).data   # पूरा डेटा लौटाओ
        }, status=201)

class CustomerProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response({
            "name": user.name,
            "phone": user.phone,
            "username": user.username,
            "email": user.email or None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "is_customer": user.is_customer,
            "is_vendor": user.is_vendor,
        })

    def post(self, request):  # update के लिए (PUT भी इस्तेमाल कर सकते हो)
        user = request.user
        allowed_fields = ['username', 'email', 'name']  # जो edit करने देना चाहते हो

        for field in allowed_fields:
            if field in request.data:
                if field == 'email' and User.objects.filter(email=request.data[field]).exclude(id=user.id).exists():
                    return Response({"error": "Email already in use"}, status=400)
                setattr(user, field, request.data[field])

        user.save(update_fields=allowed_fields)
        return Response(UserSerializer(user).data)

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "status": "ok",
            "message": "Server is healthy 🚀"
        }, status=status.HTTP_200_OK)
 
class VehicleListCreateView(generics.ListCreateAPIView):
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Vehicle.objects.filter(customer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


class VehicleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Vehicle.objects.filter(customer=self.request.user)