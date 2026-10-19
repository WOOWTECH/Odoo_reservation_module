# -*- coding: utf-8 -*-
"""Pure helpers for public booking identity input.

This module deliberately has no Odoo imports so its input rules can be checked
with offline tests. The controller supplies Odoo's phone-validation formatter
and its ``UserError`` class.
"""

import re
import unicodedata


_E164_RE = re.compile(r'^\+[1-9][0-9]{1,14}$')
_ALLOWED_PHONE_INPUT_RE = re.compile(r'^\+?[0-9() -]+$')


def normalize_booking_phone(value, country_code, country_phone_code, formatter, user_error):
    """Return ASCII E.164 or ``None`` for invalid public booking input.

    NFKC converts full-width keypad input first. Common local separators
    (spaces, ``-``, and parentheses) are left for Odoo's country-aware parser;
    punctuation-only values and malformed plus signs are rejected before it.
    ``formatter`` follows Odoo 18's ``phone_format`` signature exactly.
    """
    if not isinstance(value, str):
        return None

    raw = unicodedata.normalize('NFKC', value).strip()
    if not raw or not _ALLOWED_PHONE_INPUT_RE.fullmatch(raw):
        return None
    if raw.count('+') > 1 or ('+' in raw and not raw.startswith('+')):
        return None
    if not any('0' <= char <= '9' for char in raw):
        return None

    try:
        formatted = formatter(
            raw,
            country_code,
            country_phone_code,
            force_format='E164',
            raise_exception=True,
        )
    except user_error:
        return None

    # E.164 storage must not retain Unicode digits even if a formatter returns
    # a lookalike string.
    formatted = (formatted or '').strip()
    return formatted if _E164_RE.fullmatch(formatted) else None


def resolve_single_active_assignment(is_assigned, selected_id, active_ids):
    """Keep a single active roster member server-fixed.

    ``selected_id`` may come from a slot URL/form. It is accepted only when it
    is active and in the configured roster. For exactly one active member,
    omission is resolved to that member and a different submitted ID is
    rejected, so the conflict check cannot be bypassed.
    """
    active_ids = set(active_ids)
    if selected_id and selected_id not in active_ids:
        return None, 'not_available'
    if is_assigned and len(active_ids) == 1:
        only_id = next(iter(active_ids))
        if selected_id and selected_id != only_id:
            return None, 'not_available'
        return only_id, None
    return selected_id or None, None
