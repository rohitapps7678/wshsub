from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction, models
from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta, datetime
from django.contrib.auth import authenticate
import secrets
from django.contrib.auth.hashers import make_password
from dateutil.relativedelta import relativedelta

from customers.models import Subscription, WashHistory, User, Plan, VehicleType
from customers.utils import validate_qr_and_get_subscription, deduct_wash_and_create_history
from .models import Vendor
from .serializers import (
    VendorRegisterSerializer, VendorSerializer,
    AdminVendorCreateSerializer, WashHistoryVendorSerializer
)
from .permissions import IsVendor, IsSuperAdmin


# पहले से मौजूद views (vendor side) — इन्हें छुआ नहीं
class VendorRegisterView(APIView):
    def post(self, request):
        serializer = VendorRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data, status=status.HTTP_201_CREATED)


class VendorProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile
        serializer = VendorSerializer(vendor)
        return Response(serializer.data)


class ScanQRAndDeductView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    @transaction.atomic
    def post(self, request):
        qr_string = request.data.get('qr_string')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if not qr_string:
            return Response({"error": "qr_string is required"}, status=400)

        subscription = validate_qr_and_get_subscription(qr_string)
        if not subscription:
            return Response({"error": "Invalid QR or no washes left"}, status=400)

        vendor = request.user.vendor_profile
        result = deduct_wash_and_create_history(
            sub=subscription,
            vendor_id=vendor.id,
            lat=latitude,
            lon=longitude,
            notes=f"Scanned by {vendor.center_name} (ID: {vendor.id})"
        )

        if not result['success']:
            return Response(result, status=400)

        return Response({
            "success": True,
            "message": "Wash recorded",
            "customer_phone": result['customer_phone'],
            "remaining_washes": result['remaining'],
            "plan_name": result['plan_name'],
            "wash_time": timezone.now().isoformat(),
            "vendor_center": vendor.center_name
        }, status=200)


class VendorDashboardView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # आज का डेटा
        today_washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=today_start,
            wash_time__lt=today_end
        ).count()

        # कुल washes (all time)
        total_washes = WashHistory.objects.filter(vendor=vendor).count()

        # इस महीने का डेटा (monthly earnings & progress)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        monthly_washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=month_start
        ).count()

        # पिछले 4 महीनों का summary (bar chart के लिए)
        monthly_history = []
        current = now

        for i in range(4):
            # हर महीने की शुरुआत
            month_start_loop = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end_loop = (month_start_loop + timedelta(days=32)).replace(day=1)

            count = WashHistory.objects.filter(
                vendor=vendor,
                wash_time__gte=month_start_loop,
                wash_time__lt=month_end_loop
            ).count()

            monthly_history.append({
                "month": month_start_loop.strftime("%b"),  # Jan, Feb, ...
                "washes": count,
                "earnings": count * 120,
            })

            # पिछले महीने पर जाएं
            current = month_start_loop - timedelta(days=1)

        # list को reverse करें → oldest → newest (chart में left to right)
        monthly_history.reverse()

        # Response data (स्क्रीनशॉट से मैच करने के लिए)
        WASH_RATE = 120  # अगर अलग model/config से आना है तो वहाँ से लें

        data = {
            "center_name": vendor.center_name or "My Center",
            "is_approved": vendor.is_approved,
            "is_active": vendor.is_active,

            # Today section
            "today_washes": today_washes,
            "today_earnings": today_washes * WASH_RATE,

            # All time
            "total_washes": total_washes,
            "total_earnings_estimated": total_washes * WASH_RATE,

            # Monthly progress (current month)
            "monthly_washes_completed": monthly_washes,
            "monthly_target_washes": 500,           # ← यहाँ config, setting या vendor model से ला सकते हो
            "monthly_earnings": monthly_washes * WASH_RATE,

            # Last few months for chart
            "monthly_history": monthly_history,

            # Extra info (optional)
            "location": {
                "latitude": vendor.latitude,
                "longitude": vendor.longitude,
            } if vendor.latitude and vendor.longitude else None,
            "registered_on": vendor.created_at.isoformat(),
        }

        return Response(data, status=status.HTTP_200_OK)

# vendors/views.py

class VendorWashHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile

        # optional query params for filtering/pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))

        queryset = WashHistory.objects.filter(vendor=vendor).select_related(
            'subscription__customer',
            'subscription__plan',
            'subscription__vehicle'
        ).order_by('-wash_time')

        total_count = queryset.count()

        # simple pagination
        start = (page - 1) * limit
        end = start + limit
        items = queryset[start:end]

        serializer = WashHistoryVendorSerializer(items, many=True)

        return Response({
            "count": total_count,
            "page": page,
            "limit": limit,
            "has_more": end < total_count,
            "history": serializer.data
        })

class VendorWalletView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile
        WASH_RATE = 120  # बाद में config से लें या dynamic करें

        now = timezone.now()

        # आज की earning
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=today_start
        ).count()
        today_earnings = today_washes * WASH_RATE

        # इस महीने
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=month_start
        ).count()
        this_month_earnings = this_month_washes * WASH_RATE

        # पिछले महीने
        last_month_start = (month_start - relativedelta(months=1))
        last_month_end = month_start
        last_month_washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=last_month_start,
            wash_time__lt=last_month_end
        ).count()
        last_month_earnings = last_month_washes * WASH_RATE

        # कुल अब तक
        total_washes = WashHistory.objects.filter(vendor=vendor).count()
        total_earnings = total_washes * WASH_RATE

        return Response({
            "today": {
                "washes": today_washes,
                "earnings": today_earnings,
            },
            "this_month": {
                "washes": this_month_washes,
                "earnings": this_month_earnings,
            },
            "last_month": {
                "washes": last_month_washes,
                "earnings": last_month_earnings,
            },
            "all_time": {
                "washes": total_washes,
                "earnings": total_earnings,
            },
            "currency": "INR",
            # अगर wallet model है तो यहाँ balance, pending, withdrawn आदि ऐड कर सकते हैं
            # "available_balance": ...,
            # "pending_payout": ...,
        })

class TodayWashesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        vendor = request.user.vendor_profile
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        washes = WashHistory.objects.filter(
            vendor=vendor,
            wash_time__gte=today_start,
            wash_time__lt=today_end
        ).select_related('subscription__customer', 'subscription__plan').order_by('-wash_time')[:50]

        data = [
            {
                "wash_id": w.id,
                "time": w.wash_time.strftime("%H:%M %d-%b-%Y"),
                "customer_phone": w.subscription.customer.phone,
                "plan": w.subscription.plan.name,
                "remaining_after_wash": w.subscription.remaining_washes,
                "location": f"{w.latitude or 'N/A'}, {w.longitude or 'N/A'}",
                "notes": w.notes[:100]
            }
            for w in washes
        ]

        return Response({
            "today_date": today_start.strftime("%d %b %Y"),
            "total_today_washes": len(data),
            "washes": data
        })


# ────────────────────────────────────────────────
#           ADMIN ONLY ENDPOINTS (नया हिस्सा)
# ────────────────────────────────────────────────


class AdminVendorListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        today = timezone.now().date()

        vendors = Vendor.objects.annotate(
            total_washes=Count('washhistory'),
            today_washes=Count(
                'washhistory',
                filter=models.Q(washhistory__wash_time__date=today)
            )
        ).select_related('user').order_by('-created_at')

        # Optional filter by status
        status_filter = request.query_params.get('status')
        if status_filter == 'pending':
            vendors = vendors.filter(is_approved=False)
        elif status_filter == 'approved':
            vendors = vendors.filter(is_approved=True)

        serializer = VendorSerializer(vendors, many=True)
        return Response({
            "count": vendors.count(),
            "vendors": serializer.data
        })


class AdminVendorDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk):
        try:
            vendor = Vendor.objects.annotate(
                total_washes=Count('washhistory'),
                today_washes=Count(
                    'washhistory',
                    filter=models.Q(washhistory__wash_time__date=timezone.now().date())
                )
            ).select_related('user').get(pk=pk)

            serializer = VendorSerializer(vendor)
            return Response(serializer.data)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendor not found"}, status=404)


class AdminApproveVendorView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        try:
            vendor = Vendor.objects.get(pk=pk)
            if vendor.is_approved:
                return Response({"message": "Already approved"}, status=400)
            
            vendor.is_approved = True
            vendor.is_active = True
            vendor.save()
            
            return Response({"message": "Vendor approved successfully"})
        except Vendor.DoesNotExist:
            return Response({"error": "Vendor not found"}, status=404)


class AdminRejectVendorView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        try:
            vendor = Vendor.objects.get(pk=pk)
            if not vendor.is_approved:
                return Response({"message": "Already not approved / rejected"}, status=400)
            
            vendor.is_approved = False
            vendor.is_active = False
            vendor.save()
            
            return Response({"message": "Vendor rejected / deactivated"})
        except Vendor.DoesNotExist:
            return Response({"error": "Vendor not found"}, status=404)


class AdminCreateVendorView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request):

        serializer = AdminVendorCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        phone = serializer.validated_data['phone']
        password = serializer.validated_data['password']

        if User.objects.filter(phone=phone).exists():
            return Response({"error": "Phone number already registered"}, status=400)

        user = User.objects.create(
            phone=phone,
            username=phone,
            password=make_password(password),
            is_vendor=True,
            is_customer=False
        )

        vendor = Vendor.objects.create(
            user=user,
            center_name=serializer.validated_data['center_name'],
            address=serializer.validated_data.get('address', ''),
            latitude=serializer.validated_data.get('latitude'),
            longitude=serializer.validated_data.get('longitude'),
            is_approved=True,
            is_active=True
        )

        return Response({
            "message": "Vendor created successfully",
            "vendor": VendorSerializer(vendor).data
        }, status=201)

class VendorLoginView(APIView):

    def post(self, request):

        phone = request.data.get("phone")
        password = request.data.get("password")

        user = authenticate(username=phone, password=password)

        if not user:
            return Response({"error":"Invalid credentials"}, status=400)

        if not user.is_vendor:
            return Response({"error":"Not a vendor account"}, status=400)

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "phone": user.phone,
                "is_vendor": user.is_vendor,
                "is_approved": user.vendor_profile.is_approved
            }
        })

class AdminSubscriptionListView(APIView):

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):

        plans = (
            Plan.objects
            .select_related("vendor", "vehicle_type")
            .order_by("-created_at")
        )

        data = []

        for p in plans:

            data.append({

                "id": p.id,

                "vendor_id": p.vendor.id if p.vendor else None,

                "vendor_name": p.vendor.center_name if p.vendor else "-",

                "plan_name": p.name,

                "vehicle_type": p.vehicle_type.name,

                "price": float(p.price),

                "washes": p.washes,

                "duration_type": p.duration_type,

                "created_at": p.created_at

            })

        return Response({
            "count": plans.count(),
            "plans": data
        })

class AdminCreateSubscriptionView(APIView):

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):

        name = request.data.get("name")
        price = request.data.get("price")
        washes = request.data.get("washes")
        duration_type = request.data.get("duration_type")
        vehicle_type = request.data.get("vehicle_type")
        vendor_id = request.data.get("vendor_id")

        vehicle, _ = VehicleType.objects.get_or_create(
            name=vehicle_type
        )

        vendor = Vendor.objects.get(id=vendor_id)

        plan = Plan.objects.create(
            vendor=vendor,
            name=name,
            price=price,
            washes=washes,
            duration_type=duration_type,
            vehicle_type=vehicle
        )

        return Response({
            "message": "Subscription created successfully",
            "plan_id": plan.id
        })

class AdminGenerateVendorCodeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        center_name_hint = request.data.get("center_name", "Pending Vendor")

        code = secrets.token_hex(10).upper()

        # एक temporary user बनाएं (phone और username बाद में अपडेट होगा)
        temp_user = User.objects.create(
            phone=f"t_{secrets.token_hex(5)}",  # unique temporary phone
            username=f"temp_vendor_{secrets.token_hex(4)}",
            is_vendor=True,
            is_active=False,  # अभी inactive
            # password नहीं सेट कर रहे क्योंकि बाद में vendor सेट करेगा
        )

        vendor = Vendor.objects.create(
            user=temp_user,  # ← यहाँ user assign जरूरी है
            center_name=center_name_hint,
            registration_code=code,
            registration_code_created_at=timezone.now(),
            registration_code_used=False,
            is_approved=False,
            is_active=False,
        )

        return Response({
            "message": "Registration code generated successfully",
            "registration_code": code,
            "vendor_id": vendor.id,
            "temp_phone_hint": temp_user.phone,  # optional debug
            "valid_until": (timezone.now() + timezone.timedelta(hours=72)).isoformat(),
            "instructions": "इस code को vendor को भेजें। वे registration में इस्तेमाल करेंगे।"
        }, status=status.HTTP_201_CREATED)