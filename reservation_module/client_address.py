# -*- coding: utf-8 -*-
"""Public client address of a booking-form request (for the per-address limit).

This module imports nothing from Odoo so the rules can be unit-tested with
fake WSGI environs (see tests/test_client_address.py).

Why not ``request.httprequest.remote_addr``
-------------------------------------------
Odoo rewrites ``remote_addr`` from ``X-Forwarded-For`` only with ``proxy_mode``
on *and* an ``X-Forwarded-Host`` header, and then takes the last entry, which
is the hop in front of Odoo. Behind the PaaS chart (cloudflared tunnel ->
nginx sidecar -> Odoo) and behind a plain tunnel that is the tunnel pod, the
same private address for every visitor: a limit "per client address" keyed on
it would be one limit for the whole site and lock real customers out.

Rules (``client_address``)
--------------------------
1. The *direct peer* is the TCP peer of the connection Odoo accepted, read
   from before Odoo's proxy fix (``werkzeug.proxy_fix.orig``) when it ran,
   else ``REMOTE_ADDR``. A **public** direct peer is the client. Forwarding
   headers are ignored: anyone can send them to a server they reach directly.
2. A direct peer that is not public (private, loopback, link-local, CGNAT,
   reserved ... or not an address at all, as on a unix socket) is an
   infrastructure hop (tunnel, proxy, sidecar), the only place a trustworthy
   forwarding header can come from. Then, in this order:

   a. ``CF-Connecting-IP`` (set by the Cloudflare edge, which overwrites what
      a client sends) when it is a valid public address;
   b. ``X-Forwarded-For`` read from the **right**: each hop appends the peer
      it saw, so the right-most public entry is the client as the first trusted
      hop saw it, and whatever a client put to the left of it cannot win;
   c. Odoo's own ``remote_addr`` (``REMOTE_ADDR``) when it is public.
3. Nothing public found: ``None``. The caller then applies no per-address
   limit, because folding all such visitors into one key would be the
   site-wide limit this module avoids.
4. Values that are not a plain address (ports, brackets, zone ids, names,
   ``unknown``, garbage, over-long text) are ignored, an IPv4-mapped IPv6
   address counts as its IPv4 address, and IPv6 clients are grouped by /64
   (``address_group``): one subscriber normally owns a whole /64 and can use
   any address in it.

Limits: a deployment whose first hop in front of Odoo has a *public* address
(for example a Cloudflare record proxied straight to a public origin, or a
public load balancer) is seen as the client; such a site should set
``reservation_module.booking_rate_limit_per_ip`` to 0. Behind a proxy that is
not Cloudflare, the proxy should drop a client-sent ``CF-Connecting-IP``.
``X-Real-IP``, ``Forwarded`` and ``True-Client-IP`` are not read: the chart's
nginx sidecar sets ``X-Real-IP`` to the previous hop, and the front proxies in
use do not send the others. A /64 is shared by everyone behind it, and a
subscriber with a bigger prefix can rotate through /64s: this is a throttle
next to the per-mailbox, per-partner and per-type limits, not an identity.
"""

import ipaddress
from collections.abc import Mapping

__all__ = [
    'SOURCE_UNKNOWN',
    'address_group',
    'client_address',
    'direct_peer',
    'is_public_address',
    'parse_address',
]

# Stored in appointment.booking.client_ip_hash for a public-form booking whose
# client address is unknown. The column also marks "made through the public
# form" (mail cap, per-type cap), so it cannot stay empty, but it must never
# be a shared key of the per-address limit: the limit skips this value.
SOURCE_UNKNOWN = 'unknown'

# A textual IPv6 address is at most 45 characters (IPv4-mapped, full quad).
_MAX_ADDRESS_LENGTH = 45
# Only the right-most entries of X-Forwarded-For are examined: real chains
# have a few hops, and a long client-made prefix must cost nothing.
_MAX_FORWARDED_ENTRIES = 32


def parse_address(value):
    """``value`` as an ``ipaddress`` object, or None if it is not one.

    Only a plain address text is accepted. An IPv4-mapped IPv6 address
    (``::ffff:203.0.113.7``, how a dual-stack server reports an IPv4 peer)
    is returned as the IPv4 address.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > _MAX_ADDRESS_LENGTH or '%' in text:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_public_address(address):
    """Whether ``address`` is a globally routable unicast address.

    False for private ranges, loopback, link-local, CGNAT (100.64.0.0/10),
    documentation and other special-purpose ranges, multicast, reserved and
    the unspecified address.
    """
    return bool(
        address.is_global
        and not (address.is_multicast or address.is_reserved or address.is_unspecified
                 or address.is_loopback or address.is_link_local))


def direct_peer(environ):
    """Raw text of the TCP peer, from before Odoo's proxy fix when it ran."""
    original = environ.get('werkzeug.proxy_fix.orig')
    if isinstance(original, Mapping) and 'REMOTE_ADDR' in original:
        return original['REMOTE_ADDR']
    return environ.get('REMOTE_ADDR')


def _public(value):
    address = parse_address(value)
    return address if address is not None and is_public_address(address) else None


def client_address(environ):
    """The public address of the client behind ``environ``, or None.

    ``environ`` is the WSGI environ (``request.httprequest.environ``); see the
    module docstring for the rules.
    """
    peer = _public(direct_peer(environ))
    if peer is not None:
        return peer

    # The direct peer is an infrastructure hop (or unknown).
    address = _public(environ.get('HTTP_CF_CONNECTING_IP'))
    if address is not None:
        return address

    forwarded = environ.get('HTTP_X_FORWARDED_FOR')
    if isinstance(forwarded, str):
        for item in reversed(forwarded.rsplit(',', _MAX_FORWARDED_ENTRIES - 1)):
            address = _public(item)
            if address is not None:
                return address

    return _public(environ.get('REMOTE_ADDR'))


def address_group(address):
    """What visitors share a limit with: the IPv4 address, or the IPv6 /64."""
    if address.version == 6:
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return str(address)
