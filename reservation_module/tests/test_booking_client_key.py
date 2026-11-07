# -*- coding: utf-8 -*-
"""The per-address booking limit through the controller (critic GAP 6).

``test_client_address.py`` pins the address rules on fake environs; this file
checks what the controller does with them: the stored key, the limit that is
skipped without a public address, and the limit behind a private hop (the test
server is reached over loopback, so a hop with CF-Connecting-IP /
X-Forwarded-For headers is exactly the PaaS chart's situation).
"""

import hashlib
import hmac
import re
from datetime import timedelta
from unittest.mock import patch

from odoo.addons.website.tools import MockRequest
from odoo.http import request
from odoo.tests.common import HttpCase, TransactionCase, tagged
from odoo.tools import config

from ..client_address import SOURCE_UNKNOWN
from ..controllers.main import AppointmentController
from .test_booking_rules import RulesCommon, RulesHttpCommon

TOO_MANY = 'Too many booking attempts'
CLIENT = '8.8.4.4'
OTHER_CLIENT = '1.1.1.1'
HEX_KEY = re.compile(r'^[0-9a-f]{40}$')


def via_proxy(address, hop='10.42.0.9'):
    """Headers of a request from ``address`` through Cloudflare, a tunnel and
    the chart's nginx sidecar (the test server itself is the last hop)."""
    return {'CF-Connecting-IP': address, 'X-Forwarded-For': '%s, %s' % (address, hop)}


@tagged('post_install', '-at_install')
class TestBookingClientKey(TransactionCase):
    """AppointmentController._booking_client_key on fake requests."""

    def _key(self, remote_addr='127.0.0.1', **environ):
        with MockRequest(self.env, remote_addr=remote_addr, environ_base=environ):
            return AppointmentController()._booking_client_key()

    def test_no_public_address_gives_no_key(self):
        self.assertFalse(self._key('127.0.0.1'))
        self.assertFalse(self._key('10.42.3.17', HTTP_X_FORWARDED_FOR='10.0.0.1, 192.168.4.4'))
        self.assertFalse(self._key('10.42.3.17', HTTP_CF_CONNECTING_IP='not-an-ip'))

    def test_the_key_is_a_keyed_hash_of_the_address(self):
        key = self._key(CLIENT)
        self.assertRegex(key, HEX_KEY)
        self.assertNotIn(CLIENT, key)
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        self.assertEqual(key, hmac.new(secret.encode(), ('booking-client:' + CLIENT).encode(),
                                       hashlib.sha256).hexdigest()[:40])
        self.env['ir.config_parameter'].sudo().set_param('database.secret', secret + '-rotated')
        self.assertNotEqual(self._key(CLIENT), key, 'the key depends on the database secret')

    def test_a_public_peer_is_not_overridden_by_headers(self):
        plain = self._key(CLIENT)
        self.assertEqual(
            self._key(CLIENT, HTTP_X_FORWARDED_FOR=OTHER_CLIENT, HTTP_CF_CONNECTING_IP='9.9.9.9'), plain)
        # Odoo's proxy fix put the forged last X-Forwarded-For entry into REMOTE_ADDR.
        self.assertEqual(
            self._key(OTHER_CLIENT, HTTP_X_FORWARDED_FOR=OTHER_CLIENT,
                      **{'werkzeug.proxy_fix.orig': {'REMOTE_ADDR': CLIENT}}), plain)

    def test_behind_a_hop_the_forwarded_address_is_the_client(self):
        plain = self._key(CLIENT)
        self.assertEqual(self._key('127.0.0.1', HTTP_CF_CONNECTING_IP=CLIENT), plain)
        self.assertEqual(
            self._key('127.0.0.1', HTTP_X_FORWARDED_FOR='9.9.9.9, %s, 10.42.3.17' % CLIENT), plain)
        self.assertEqual(
            self._key('10.42.3.17', HTTP_X_FORWARDED_FOR='9.9.9.9, %s, 10.42.3.17' % CLIENT,
                      HTTP_X_FORWARDED_HOST='shop.example.com',
                      **{'werkzeug.proxy_fix.orig': {'REMOTE_ADDR': '127.0.0.1'}}), plain)
        self.assertNotEqual(self._key('127.0.0.1', HTTP_CF_CONNECTING_IP=OTHER_CLIENT), plain)

    def test_ipv6_visitors_share_their_64(self):
        first = self._key('127.0.0.1', HTTP_CF_CONNECTING_IP='2606:4700:4700:1111::1')
        self.assertRegex(first, HEX_KEY)
        self.assertEqual(self._key('127.0.0.1', HTTP_CF_CONNECTING_IP='2606:4700:4700:1111:a:b:c:d'), first)
        self.assertEqual(self._key('2606:4700:4700:1111::99'), first)
        self.assertNotEqual(self._key('127.0.0.1', HTTP_CF_CONNECTING_IP='2606:4700:4700:2222::1'), first)


@tagged('post_install', '-at_install')
class TestAddressLimitFunction(RulesCommon, TransactionCase):
    """AppointmentController._booking_rate_limit_error on stored bookings."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.booking_rate_limit_per_ip', '1')

    def _error(self, client_key, email='someone@example.com'):
        with MockRequest(self.env):
            return AppointmentController()._booking_rate_limit_error(
                self.appointment_type, email, False, client_key)

    def _stored(self, key, count):
        for index in range(count):
            self._booking(self.appointment_type, self._wall(3, 8 + index), state='draft',
                          guest_email='stored%d@example.com' % index, client_ip_hash=key)

    def test_a_known_key_is_limited(self):
        self._stored('a' * 40, 1)
        self.assertIn(TOO_MANY, self._error('a' * 40))
        self.assertFalse(self._error('b' * 40))

    def test_unknown_origin_is_never_a_shared_key(self):
        self._stored(SOURCE_UNKNOWN, 3)
        self.assertFalse(self._error(False))
        self.assertFalse(self._error(SOURCE_UNKNOWN), 'the marker is not a key even if it is passed in')

    def test_unknown_origin_still_counts_for_the_type_cap(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.booking_rate_limit_per_type', '3')
        self._stored(SOURCE_UNKNOWN, 3)
        self.assertIn(TOO_MANY, self._error(False))

    def test_old_bookings_do_not_count(self):
        self._stored('a' * 40, 1)
        self.env.cr.execute(
            "UPDATE appointment_booking SET create_date = %s WHERE client_ip_hash = %s",
            [self.env.cr.now() - timedelta(hours=2), 'a' * 40])
        self.env.invalidate_all()
        self.assertFalse(self._error('a' * 40))


@tagged('post_install', '-at_install')
class TestAddressLimitOverHttp(RulesHttpCommon, HttpCase):
    """The booking form behind a private hop, as in the PaaS chart."""

    def setUp(self):
        super().setUp()
        self.appointment_type = self._setup_appointment_type()
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '2')

    def _hour(self, index):
        return self._wall(3, 8 + index)

    def _book(self, index, headers, email=None):
        return self._post(self.appointment_type, self._hour(index), headers=headers,
                          guest_email=email or 'visitor%d@example.com' % index)

    def test_visitors_behind_the_same_hop_have_their_own_limit(self):
        for index in range(3):
            response = self._book(index, via_proxy(CLIENT))
        self.assertIn(TOO_MANY, response.text, 'the third booking of one visitor is refused')
        response = self._book(3, via_proxy(OTHER_CLIENT))
        self.assertNotIn(TOO_MANY, response.text, 'another visitor is not locked out by the first')
        bookings = self._bookings(self.appointment_type)
        self.assertEqual(len(bookings), 3)
        self.assertEqual(len(bookings.filtered(lambda b: b.guest_email == 'visitor3@example.com')), 1)

    def test_behind_odoo_proxy_mode_as_in_the_paas_chart(self):
        # The chart runs Odoo with proxy_mode = True behind an nginx sidecar that
        # sends X-Forwarded-Host and appends the previous hop to X-Forwarded-For.
        # Odoo's proxy fix then puts the LAST entry (the tunnel) into
        # remote_addr and the sidecar stays the TCP peer: the client is still
        # the right-most public entry, whatever the visitor wrote before it.
        host = self.base_url().split('//', 1)[1]
        seen = []
        original = AppointmentController._booking_client_key

        def spy(controller):
            environ = request.httprequest.environ
            seen.append((environ.get('REMOTE_ADDR'), (environ.get('werkzeug.proxy_fix.orig') or {}).get('REMOTE_ADDR')))
            return original(controller)

        with patch.dict(config.options, {'proxy_mode': True}), \
                patch.object(AppointmentController, '_booking_client_key', spy):
            for index, prefix in enumerate(['7.7.7.1', '7.7.7.2', '7.7.7.3']):
                response = self._book(index, {
                    'X-Forwarded-Host': host,
                    'X-Forwarded-For': '%s, %s, 10.42.0.9' % (prefix, CLIENT)})
            self.assertIn(TOO_MANY, response.text, 'the visitor is not the tunnel and not the forged prefix')
            other = self._book(3, {'X-Forwarded-Host': host,
                                   'X-Forwarded-For': '7.7.7.1, %s, 10.42.0.9' % OTHER_CLIENT})
            self.assertNotIn(TOO_MANY, other.text, 'another visitor behind the same tunnel is not locked out')
        self.assertEqual(len(self._bookings(self.appointment_type)), 3)
        # Odoo's proxy fix really ran: remote_addr is the tunnel, the TCP peer is kept aside.
        self.assertEqual(set(seen), {('10.42.0.9', '127.0.0.1')})

    def test_cloudflare_header_alone_identifies_the_visitor(self):
        for index in range(3):
            response = self._book(index, {'CF-Connecting-IP': CLIENT})
        self.assertIn(TOO_MANY, response.text)
        self.assertNotIn(TOO_MANY, self._book(3, {'CF-Connecting-IP': OTHER_CLIENT}).text)

    def test_forwarded_for_prefix_cannot_reset_the_limit(self):
        for index, prefix in enumerate(['7.7.7.1', '7.7.7.2', '7.7.7.3']):
            response = self._book(index, {'X-Forwarded-For': '%s, %s, 10.42.0.9' % (prefix, CLIENT)})
        self.assertIn(TOO_MANY, response.text)
        self.assertEqual(len(self._bookings(self.appointment_type)), 2)

    def test_forwarded_for_identifies_the_visitor_when_there_is_no_cloudflare_header(self):
        for index in range(3):
            self._book(index, {'X-Forwarded-For': '%s, 10.42.0.9' % CLIENT})
        self.assertEqual(len(self._bookings(self.appointment_type)), 2)
        response = self._book(3, {'X-Forwarded-For': '%s, 10.42.0.9' % OTHER_CLIENT})
        self.assertNotIn(TOO_MANY, response.text)

    def test_ipv6_visitor_is_limited_by_the_64(self):
        for index, host in enumerate(['1', '2', '3']):
            response = self._book(index, {'CF-Connecting-IP': '2606:4700:4700:1111::%s' % host})
        self.assertIn(TOO_MANY, response.text, 'three addresses of one /64 are one visitor')
        other = self._book(3, {'CF-Connecting-IP': '2606:4700:4700:2222::1'})
        self.assertNotIn(TOO_MANY, other.text)

    def test_without_a_public_address_the_per_address_limit_is_not_applied(self):
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '1')
        for index, headers in enumerate([None, {}, {'X-Forwarded-For': '10.0.0.5, 192.168.1.7'},
                                         {'CF-Connecting-IP': 'garbage'}]):
            response = self._book(index, headers)
            self.assertNotIn(TOO_MANY, response.text, 'booking %d' % index)
        bookings = self._bookings(self.appointment_type)
        self.assertEqual(len(bookings), 4)
        self.assertEqual(set(bookings.mapped('client_ip_hash')), {SOURCE_UNKNOWN},
                         'still marked as made through the public form')

    def test_unknown_origin_bookings_still_hit_the_other_limits(self):
        self.ICP.set_param('reservation_module.booking_rate_limit_per_type', '2')
        for index in range(3):
            response = self._book(index, None)
        self.assertIn(TOO_MANY, response.text, 'the per-type cap is site wide and counts them')
        self.assertEqual(len(self._bookings(self.appointment_type)), 2)

    def test_per_address_limit_can_be_switched_off(self):
        self.ICP.set_param('reservation_module.booking_rate_limit_per_ip', '0')
        for index in range(4):
            self.assertNotIn(TOO_MANY, self._book(index, via_proxy(CLIENT)).text)
        self.assertEqual(len(self._bookings(self.appointment_type)), 4)

    def test_stored_key_is_the_keyed_hash_not_the_address(self):
        self._book(0, via_proxy(CLIENT))
        self._book(1, via_proxy(OTHER_CLIENT))
        first, second = self._bookings(self.appointment_type).sorted('id')
        secret = self.ICP.get_param('database.secret') or ''
        for booking, address in ((first, CLIENT), (second, OTHER_CLIENT)):
            expected = hmac.new(secret.encode(), ('booking-client:' + address).encode(),
                                hashlib.sha256).hexdigest()[:40]
            self.assertEqual(booking.client_ip_hash, expected)
            self.assertNotIn(address, booking.client_ip_hash)
