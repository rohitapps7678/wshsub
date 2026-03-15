# customers/utils.py
"""
Utility functions for customers app:
- QR code generation and attachment
- Wash deduction with history logging (atomic)
- Haversine distance calculation
- Nearby vendors finder (simple loop-based)
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image
from io import BytesIO
from math import radians, sin, cos, sqrt, atan2

from .models import Subscription, WashHistory
from vendors.models import Vendor

logger = logging.getLogger(__name__)


def generate_qr_code(data: str) -> Tuple[ContentFile, str]:
    """
    QR कोड इमेज जेनरेट करता है और ContentFile के रूप में लौटाता है
    """
    try:
        qr = qrcode.QRCode(
            version=10,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        filename = f"qr_{uuid.uuid4().hex[:12]}.png"
        return ContentFile(buffer.getvalue(), name=filename), data

    except Exception as e:
        logger.error(f"QR generation failed: {e}", exc_info=True)
        raise


def attach_qr_to_subscription(sub: Subscription) -> None:
    """
    Subscription में QR स्ट्रिंग बनाता है और इमेज attach करता है
    """
    if not sub.qr_string:
        sub.qr_string = str(uuid.uuid4())
        sub.save(update_fields=['qr_string'])

    qr_file, _ = generate_qr_code(sub.qr_string)
    sub.qr_image.save(f"sub_{sub.id}.png", qr_file, save=True)
    logger.info(f"QR attached to subscription {sub.id}")


@transaction.atomic
def deduct_wash_and_create_history(
    sub: Subscription,
    vendor_id: int,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    notes: str = ""
) -> Dict[str, Any]:
    """
    एक वॉश घटाता है + WashHistory रिकॉर्ड बनाता है (atomic तरीके से)
    """
    if sub.remaining_washes < 1:
        return {"success": False, "message": "No washes remaining", "remaining": 0}

    sub.remaining_washes -= 1
    if sub.remaining_washes == 0:
        sub.is_active = False
    sub.save(update_fields=['remaining_washes', 'is_active'])

    vendor = None
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        logger.warning(f"Vendor {vendor_id} not found during wash deduction")

    WashHistory.objects.create(
        subscription=sub,
        vendor=vendor,
        latitude=lat,
        longitude=lon,
        notes=notes
    )

    logger.info(
        f"Wash deducted | Sub:{sub.id} | Remaining:{sub.remaining_washes} | Vendor:{vendor_id}"
    )

    return {
        "success": True,
        "message": "Wash recorded",
        "remaining": sub.remaining_washes,
        "customer_phone": sub.customer.phone,
        "plan_name": sub.plan.name
    }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    दो GPS पॉइंट्स के बीच दूरी (किलोमीटर में) - Haversine फॉर्मूला
    """
    R = 6371.0  # पृथ्वी की औसत त्रिज्या (km)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return round(distance, 2)


def get_nearby_vendors(
    lat: float,
    lon: float,
    max_km: float = 15.0,
    limit: int = 8
) -> List[Dict]:
    """
    ग्राहक के लोकेशन से पास के अप्रूव्ड वेंडर्स लौटाता है
    (GeoDjango/PostGIS इस्तेमाल करने पर बेहतर परफॉर्मेंस मिलेगी)
    """
    vendors = Vendor.objects.filter(is_approved=True, is_active=True)
    results = []

    for v in vendors:
        if v.latitude is None or v.longitude is None:
            continue

        dist = haversine_distance(lat, lon, v.latitude, v.longitude)

        if dist <= max_km:
            results.append({
                "id": v.id,
                "center_name": v.center_name,
                "distance_km": dist,
                "latitude": v.latitude,
                "longitude": v.longitude,
                # optional: "address": v.address, अगर मॉडल में है
            })

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]

def validate_qr_and_get_subscription(
    qr_string: str,
    min_remaining_washes: int = 1
) -> Optional[Subscription]:
    try:
        return Subscription.objects.select_related('customer', 'plan').get(
            qr_string=qr_string,
            is_active=True,
            remaining_washes__gte=min_remaining_washes
        )
    except Subscription.DoesNotExist:
        logger.warning(f"Invalid QR: {qr_string[:12]}...")
        return None
    except Exception as e:
        logger.error(f"QR validation failed: {e}")
        return None