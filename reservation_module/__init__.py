# -*- coding: utf-8 -*-

from . import models
from . import controllers


def _post_init_hook(env):
    """Migrate booking_type data to new boolean fields"""
    env.cr.execute("""
        UPDATE appointment_type
        SET assign_staff = TRUE, allow_customer_choose_staff = TRUE
        WHERE booking_type = 'user' OR booking_type IS NULL;
    """)
    env.cr.execute("""
        UPDATE appointment_type
        SET assign_location = TRUE, allow_customer_choose_location = TRUE
        WHERE booking_type = 'resource';
    """)
