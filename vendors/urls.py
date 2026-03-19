from django.urls import path
from . import views

urlpatterns = [
    # Vendor खुद के लिए (पहले जैसे ही)
    path('register/', views.VendorRegisterView.as_view(), name='vendor-register'),
    path('profile/',  views.VendorProfileView.as_view(),  name='vendor-profile'),
    path('scan/',     views.ScanQRAndDeductView.as_view(), name='scan-qr'),
    path('dashboard/', views.VendorDashboardView.as_view(), name='vendor-dashboard'),
    path('today-washes/', views.TodayWashesView.as_view(), name='today-washes'),
    path("login/", views.VendorLoginView.as_view(), name="vendor-login"),
    path(
    "admin/subscriptions/",
    views.AdminSubscriptionListView.as_view(),
    name="admin-subscriptions"
    ),
    # vendors/urls.py
    path('wallet/', views.VendorWalletView.as_view(), name='vendor-wallet'),
    # vendors/urls.py
    path('history/', views.VendorWashHistoryView.as_view(), name='vendor-wash-history'),
    path(
    "admin/subscriptions/create/",
    views.AdminCreateSubscriptionView.as_view(),
    name="admin-create-subscription"
    ),
    path('admin/generate-vendor-code/', views.AdminGenerateVendorCodeView.as_view(), name='admin-generate-vendor-code'),

    # Admin only endpoints (prefix admin/)
    path('admin/vendors/', views.AdminVendorListView.as_view(), name='admin-vendor-list'),
    path('admin/vendors/<int:pk>/', views.AdminVendorDetailView.as_view(), name='admin-vendor-detail'),
    path('admin/vendors/<int:pk>/approve/', views.AdminApproveVendorView.as_view(), name='admin-approve-vendor'),
    path('admin/vendors/<int:pk>/reject/', views.AdminRejectVendorView.as_view(), name='admin-reject-vendor'),
    path('admin/vendors/create/', views.AdminCreateVendorView.as_view(), name='admin-create-vendor'),
]