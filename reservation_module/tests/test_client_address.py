# -*- coding: utf-8 -*-
"""Client address of a public booking request (critic GAP 6, sweep 2026-11-07).

``booking_rate_limit_per_ip`` is meant to be "per visitor". Behind the PaaS
chart (cloudflared tunnel -> nginx sidecar -> Odoo) and behind a plain tunnel,
Odoo's ``remote_addr`` is the tunnel pod for every visitor, so keying the limit
on it made it one limit for the whole site. The rules under test live in
``client_address.py`` (pure Python, read them first):

  * a public direct peer is the client, forwarding headers are ignored
  * behind a private hop: CF-Connecting-IP, else X-Forwarded-For from the
    right, else Odoo's own remote_addr, always public addresses only
  * nothing public: no per-address key (the limit is skipped, never shared)
  * IPv6 clients are grouped by /64, garbage header values are ignored

The first classes run on fake WSGI environs and also work without Odoo
(``python -m pytest reservation_module/tests/test_client_address.py``); the
rest drive the controller helper and the booking form.
"""

import importlib.util
import os
import sys
import unittest

try:
    from odoo.tests.common import BaseCase, tagged
except ImportError:  # run on its own with pytest / unittest, no Odoo
    BaseCase = unittest.TestCase

    def tagged(*_tags):
        return lambda cls: cls


def _load_client_address():
    """The module under test, with or without an Odoo runtime (see
    test_timezone_pure.py: the module imports nothing from Odoo)."""
    try:
        from odoo.addons.reservation_module import client_address  # noqa: WPS433
        return client_address
    except ImportError:
        pass
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client_address.py')
    spec = importlib.util.spec_from_file_location('reservation_module_client_address', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client_address = _load_client_address()

# Public addresses (real, globally routable, so not documentation ranges).
CLIENT = '8.8.4.4'
OTHER_CLIENT = '1.1.1.1'
SPOOF = '9.9.9.9'
# Infrastructure hops.
SIDECAR = '127.0.0.1'
TUNNEL = '10.42.3.17'


def make_environ(peer=SIDECAR, cf=None, xff=None, orig_peer=None, **extra):
    """A WSGI environ as Odoo sees it.

    ``orig_peer`` is the TCP peer when Odoo's proxy fix ran (``peer`` is then
    the value the fix put into REMOTE_ADDR, taken from X-Forwarded-For).
    """
    environ = {'REMOTE_ADDR': peer}
    if orig_peer is not None:
        environ['werkzeug.proxy_fix.orig'] = {'REMOTE_ADDR': orig_peer}
    if cf is not None:
        environ['HTTP_CF_CONNECTING_IP'] = cf
    if xff is not None:
        environ['HTTP_X_FORWARDED_FOR'] = xff
    environ.update(extra)
    return environ


def resolve(environ):
    address = client_address.client_address(environ)
    return str(address) if address is not None else None


def group(environ):
    address = client_address.client_address(environ)
    return client_address.address_group(address) if address is not None else None


@tagged('post_install', '-at_install')
class TestDirectPublicPeer(BaseCase):
    """Rule 1: a public TCP peer is the client, headers are not believed."""

    def test_public_peer_is_the_client(self):
        self.assertEqual(resolve(make_environ(peer=CLIENT)), CLIENT)

    def test_forwarding_headers_from_a_public_peer_are_ignored(self):
        environ = make_environ(peer=CLIENT, cf=SPOOF, xff='%s, %s' % (SPOOF, OTHER_CLIENT))
        self.assertEqual(resolve(environ), CLIENT)

    def test_a_visitor_cannot_pick_the_key_by_rotating_headers(self):
        keys = {group(make_environ(peer=CLIENT, cf='%d.%d.%d.%d' % (11, n, n, n), xff='12.%d.0.1' % n))
                for n in range(1, 40)}
        self.assertEqual(keys, {CLIENT})

    def test_proxy_fix_rewrite_does_not_hide_the_real_peer(self):
        # Odoo with proxy_mode: REMOTE_ADDR became the (forged) last X-Forwarded-For entry.
        environ = make_environ(peer=SPOOF, orig_peer=CLIENT, xff=SPOOF, cf=SPOOF,
                               HTTP_X_FORWARDED_HOST='shop.example.com')
        self.assertEqual(resolve(environ), CLIENT)

    def test_ipv4_mapped_public_peer_is_the_ipv4_address(self):
        self.assertEqual(resolve(make_environ(peer='::ffff:%s' % CLIENT)), CLIENT)

    def test_public_ipv6_peer(self):
        self.assertEqual(resolve(make_environ(peer='2606:4700:4700::1111')), '2606:4700:4700::1111')


@tagged('post_install', '-at_install')
class TestBehindPrivateHops(BaseCase):
    """Rule 2: the peer is a tunnel / proxy / sidecar; look at what it forwards."""

    def test_cloudflare_header_is_the_client(self):
        self.assertEqual(resolve(make_environ(peer=TUNNEL, cf=CLIENT)), CLIENT)

    def test_cloudflare_header_beats_forwarded_for(self):
        environ = make_environ(peer=TUNNEL, cf=CLIENT, xff='%s, %s' % (OTHER_CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_forwarded_for_is_read_from_the_right(self):
        # What the chart's nginx sidecar produces behind cloudflared:
        # "<whatever the client sent>, <client as Cloudflare saw it>, <tunnel>".
        environ = make_environ(peer=SIDECAR, xff='%s, %s, %s' % (SPOOF, CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_a_long_client_made_prefix_cannot_win(self):
        prefix = ', '.join('7.7.%d.%d' % (n // 250, n % 250 + 1) for n in range(300))
        environ = make_environ(peer=SIDECAR, xff='%s, %s, %s' % (prefix, CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_same_visitor_same_key_whatever_the_prefix(self):
        keys = {group(make_environ(peer=SIDECAR, xff='%d.0.0.%d, %s, %s' % (20 + n, n, CLIENT, TUNNEL)))
                for n in range(1, 30)}
        self.assertEqual(keys, {CLIENT})

    def test_visitors_behind_the_same_hop_get_different_keys(self):
        first = group(make_environ(peer=SIDECAR, cf=CLIENT, xff='%s, %s' % (CLIENT, TUNNEL)))
        second = group(make_environ(peer=SIDECAR, cf=OTHER_CLIENT, xff='%s, %s' % (OTHER_CLIENT, TUNNEL)))
        self.assertEqual((first, second), (CLIENT, OTHER_CLIENT))

    def test_proxy_fix_rewrote_remote_addr_to_the_tunnel(self):
        # proxy_mode on, X-Forwarded-Host present: REMOTE_ADDR = last entry = tunnel,
        # the sidecar is the TCP peer. The client is still found.
        environ = make_environ(peer=TUNNEL, orig_peer=SIDECAR, xff='%s, %s, %s' % (SPOOF, CLIENT, TUNNEL),
                               HTTP_X_FORWARDED_HOST='shop.example.com')
        self.assertEqual(resolve(environ), CLIENT)

    def test_private_entries_are_skipped_on_the_way(self):
        environ = make_environ(peer=SIDECAR, xff='%s, 192.168.1.9, 10.0.0.4, 100.64.1.1, %s' % (CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_remote_addr_is_the_last_resort(self):
        # Odoo's own value (set by its proxy fix) is public, nothing else is.
        environ = make_environ(peer=CLIENT, orig_peer=SIDECAR)
        self.assertEqual(resolve(environ), CLIENT)

    def test_private_cloudflare_header_is_not_a_client(self):
        environ = make_environ(peer=SIDECAR, cf='10.1.2.3', xff='%s, %s' % (CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_ipv6_loopback_and_unique_local_peers_are_hops(self):
        for peer in ('::1', 'fd00::5', 'fe80::1'):
            self.assertEqual(resolve(make_environ(peer=peer, cf=CLIENT)), CLIENT, peer)

    def test_unknown_peer_counts_as_a_hop(self):
        # A unix socket gives no REMOTE_ADDR or an empty one.
        for peer in (None, '', 'unix'):
            self.assertEqual(resolve(make_environ(peer=peer, cf=CLIENT)), CLIENT, peer)
        self.assertEqual(resolve({'HTTP_CF_CONNECTING_IP': CLIENT}), CLIENT)


@tagged('post_install', '-at_install')
class TestNoPublicAddress(BaseCase):
    """Rule 3: nothing public -> None (the caller skips the per-address limit)."""

    def test_all_private_chain(self):
        environ = make_environ(peer=SIDECAR, xff='10.0.0.1, 192.168.4.4, %s' % TUNNEL)
        self.assertIsNone(client_address.client_address(environ))

    def test_loopback_only(self):
        self.assertIsNone(client_address.client_address(make_environ(peer='127.0.0.1')))
        self.assertIsNone(client_address.client_address(make_environ(peer='::1')))

    def test_special_purpose_ranges_are_not_public(self):
        specials = ['0.0.0.0', '255.255.255.255', '169.254.1.1', '100.64.0.9', '100.127.255.254',
                    '172.16.0.1', '172.31.255.255', '192.168.0.1', '224.0.0.1', '240.0.0.1',
                    '192.0.2.1', '198.51.100.1', '203.0.113.1', '198.18.0.1',
                    '::', '::1', 'fe80::1', 'fc00::1', 'fd12:3456::1', 'ff02::1', '2001:db8::1',
                    '::ffff:10.0.0.1', '::ffff:127.0.0.1']
        for value in specials:
            self.assertIsNone(client_address.client_address(make_environ(peer=SIDECAR, cf=value)), value)
            self.assertIsNone(client_address.client_address(make_environ(peer=SIDECAR, xff=value)), value)
            self.assertIsNone(client_address.client_address(make_environ(peer=value)), value)

    def test_no_headers_behind_a_hop(self):
        self.assertIsNone(client_address.client_address(make_environ(peer=SIDECAR)))
        self.assertIsNone(client_address.client_address({}))


@tagged('post_install', '-at_install')
class TestIPv6Grouping(BaseCase):
    """Rule 4: an IPv6 visitor is a /64, an IPv4 visitor an address."""

    def test_same_64_same_group(self):
        first = group(make_environ(peer='2a01:4f8:1:2:aaaa:bbbb:cccc:dddd'))
        second = group(make_environ(peer='2a01:4f8:1:2::1'))
        self.assertEqual(first, second)
        self.assertEqual(first, '2a01:4f8:1:2::/64')

    def test_different_64_different_group(self):
        first = group(make_environ(peer='2a01:4f8:1:2::1'))
        second = group(make_environ(peer='2a01:4f8:1:3::1'))
        self.assertNotEqual(first, second)

    def test_grouping_applies_behind_a_hop(self):
        keys = {group(make_environ(peer=SIDECAR, cf='2606:4700:4700:%x::1' % n)) for n in range(1, 50)}
        self.assertEqual(len(keys), 49, 'each /64 is its own visitor')
        keys = {group(make_environ(peer=SIDECAR, xff='2606:4700:4700:%x::%x, %s' % (n, n, TUNNEL)))
                for n in range(1, 50)}
        self.assertEqual(len(keys), 49)
        one = {group(make_environ(peer=SIDECAR, cf='2606:4700:4700:1111::%x' % n)) for n in range(1, 50)}
        self.assertEqual(one, {'2606:4700:4700:1111::/64'})

    def test_ipv4_is_not_grouped(self):
        self.assertEqual(group(make_environ(peer='8.8.4.4')), '8.8.4.4')
        self.assertNotEqual(group(make_environ(peer='8.8.4.4')), group(make_environ(peer='8.8.4.5')))

    def test_mapped_and_plain_ipv4_are_one_visitor(self):
        self.assertEqual(group(make_environ(peer=SIDECAR, cf='::ffff:8.8.4.4')),
                         group(make_environ(peer=SIDECAR, cf='8.8.4.4')))

    def test_text_variants_of_one_address_are_one_visitor(self):
        variants = ['2606:4700:4700:0:0:0:0:1111', '2606:4700:4700::1111', '2606:4700:4700::1111',
                    '2606:4700:4700::1111'.upper()]
        self.assertEqual({group(make_environ(peer=SIDECAR, cf=value)) for value in variants},
                         {'2606:4700:4700::/64'})


@tagged('post_install', '-at_install')
class TestGarbageHeaders(BaseCase):
    """Rule 4: values that are not a plain address are ignored."""

    GARBAGE = ['', ' ', 'unknown', 'not-an-ip', '999.1.1.1', '1.2.3', '1.2.3.4.5', '8.8.8.8:443',
               '[2606:4700::1111]:443', '[2606:4700::1111]', '8.8.8.8/32', '2606:4700::1111%eth0',
               'localhost', '0x08.0x08.0x08.0x08', '8.8.8', '08.08.08.08', 'a' * 5000, '8.8.8.8 8.8.4.4',
               '８.８.８.８', '\x00', '8.8.8.8;', "'8.8.8.8'", '"8.8.8.8"', '1' * 400, ',', ',,,']

    def test_garbage_in_either_header_gives_no_address(self):
        for value in self.GARBAGE:
            self.assertIsNone(client_address.client_address(make_environ(peer=SIDECAR, cf=value)), repr(value))
            self.assertIsNone(client_address.client_address(make_environ(peer=SIDECAR, xff=value)), repr(value))
            self.assertIsNone(client_address.client_address(make_environ(peer=value)), repr(value))

    def test_garbage_in_the_cloudflare_header_falls_back_to_forwarded_for(self):
        environ = make_environ(peer=SIDECAR, cf='not-an-ip', xff='%s, %s' % (CLIENT, TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_garbage_entries_are_skipped_not_believed(self):
        environ = make_environ(peer=SIDECAR, xff='%s, unknown, %s, [::1]:80, %s' % (CLIENT, 'garbage', TUNNEL))
        self.assertEqual(resolve(environ), CLIENT)

    def test_comma_list_in_the_cloudflare_header_is_garbage(self):
        # A repeated header reaches WSGI as "a, b": not one address.
        environ = make_environ(peer=SIDECAR, cf='%s, %s' % (SPOOF, CLIENT))
        self.assertIsNone(client_address.client_address(environ))

    def test_non_string_values(self):
        environ = make_environ(peer=SIDECAR)
        environ['HTTP_CF_CONNECTING_IP'] = 134744072
        environ['HTTP_X_FORWARDED_FOR'] = b'8.8.8.8'
        self.assertIsNone(client_address.client_address(environ))
        self.assertIsNone(client_address.client_address(make_environ(peer=134744072)))

    def test_huge_header_is_bounded(self):
        header = ', '.join(['junk'] * 20000) + ', ' + CLIENT + ', ' + TUNNEL
        self.assertEqual(resolve(make_environ(peer=SIDECAR, xff=header)), CLIENT)

    def test_whitespace_and_case_are_tolerated(self):
        self.assertEqual(resolve(make_environ(peer=SIDECAR, cf='  8.8.4.4  ')), CLIENT)
        self.assertEqual(resolve(make_environ(peer=SIDECAR, xff=' 8.8.4.4 ,\t10.0.0.1 ')), CLIENT)
        self.assertEqual(group(make_environ(peer=SIDECAR, cf='2606:4700:4700::ABCD')), '2606:4700:4700::/64')

    def test_unknown_source_marker_is_not_an_address(self):
        self.assertIsNone(client_address.parse_address(client_address.SOURCE_UNKNOWN))
