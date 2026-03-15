"""
vendors/utils.py
Vendor specific helper functions
"""

import logging
from datetime import date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_today_wash_count(vendor_id: int) -> int:
    """Placeholder - real में WashHistory model से query करनी चाहिए"""
    # Example:
    # return WashHistory.objects.filter(
    #     vendor_id=vendor_id,
    #     wash_time__date=date.today()
    # ).count()
    return 8  # dummy


def get_vendor_earnings_estimate(vendor_id: int, rate_per_wash: int = 120) -> int:
    """Dummy earnings calculation"""
    total_washes = 450  # should come from history
    return total_washes * rate_per_wash