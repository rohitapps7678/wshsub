from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('register/', views.CustomerRegisterView.as_view(), name='customer-register'),
    path('login/',    views.CustomerLoginView.as_view(),    name='customer-login'),

    # Plans & Subscription
    path('vehicle-types/', views.VehicleTypeListView.as_view(), name='vehicle-types'),
    path('my-subscription/', views.MyActiveSubscriptionView.as_view(), name='my-subscription'),
    path('nearby-centers/',  views.NearbyWashingCentersView.as_view(), name='nearby-centers'),
    path('buy-subscription/', views.BuySubscriptionView.as_view(), name='buy-subscription'),
    path(
        "plans/",
        views.CustomerPlansView.as_view(),
        name="customer-plans"
    ),
    path(
    "buy-plan/",
    views.BuyPlanView.as_view(),
    name="buy-plan"
    ),
    path('profile/', views.CustomerProfileView.as_view(), name='customer-profile'),
    path('profile/update/', views.CustomerProfileView.as_view(), name='customer-profile-update'),  # optional अगर अलग चाहो

    # Other customer views
    path('my-qr/', views.MyQRView.as_view(), name='my-qr'),
    path('history/', views.WashHistoryView.as_view(), name='wash-history'),

    # ─── Admin Only ─────────────────────────────────────
    path('admin/customers/', views.AdminCustomerListView.as_view(), name='admin-customer-list'),
    path('admin/customers/<int:pk>/', views.AdminCustomerDetailView.as_view(), name='admin-customer-detail'),
    path('admin/customers/<int:pk>/update/', views.AdminCustomerUpdateView.as_view(), name='admin-customer-update'),
]