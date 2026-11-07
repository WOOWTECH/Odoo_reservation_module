# -*- coding: utf-8 -*-
"""權限收緊的回歸測試（18.0.3.2.2）。

  * portal／public 不能經 ORM（call_kw）直接建立預約
  * 員工內部欄位（internal_notes 等）portal 擁有者讀不到
  * 線上預約的 Discuss 會議室是成員制，其他 portal 使用者讀不到也加不進去
  * 預約的 calendar.event 與參加者列只有主辦人、參加者、預約管理員看得到；
    標題、描述不含訪客姓名與聯絡資料
  * 預約表單只顯示屬於該預約類型名單的員工／場地名稱
  * 18.0.3.2.2 migration 把既有會議室與 event 收緊，可重跑
"""

import importlib.util
import re
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.modules.module import get_module_path
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_timezone import TimezoneCommon


def _load_migration_3_2_2():
    path = get_module_path('reservation_module') + '/migrations/18.0.3.2.2/post-migrate.py'
    spec = importlib.util.spec_from_file_location('reservation_module_mig_3_2_2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AclCommon:

    @classmethod
    def _user(cls, login, group_xmlids, name=None):
        return cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': name or login,
            'login': login,
            'email': f'{login}@example.com',
            'groups_id': [(6, 0, [cls.env.ref(x).id for x in group_xmlids])],
        })

    @classmethod
    def _setup_acl_fixtures(cls):
        cls.portal_user = cls._user('acl_portal_guest', ['base.group_portal'], name='Alice Guest')
        cls.other_portal = cls._user('acl_portal_other', ['base.group_portal'])
        cls.employee = cls._user('acl_employee', ['base.group_user'])
        cls.staff = cls._user('acl_staff', ['reservation_module.group_appointment_user'])
        cls.appt_user = cls._user('acl_appt_user', ['reservation_module.group_appointment_user'])
        cls.manager = cls._user('acl_manager', ['reservation_module.group_appointment_manager'])
        cls.public_user = cls.env.ref('base.public_user')
        cls.appointment_type = cls.env['appointment.type'].create({
            'name': 'ACL Consult',
            'slot_duration': 1.0,
            'max_booking_days': 30,
            'min_booking_hours': 0,
            'auto_confirm': False,
            'require_payment': False,
            'is_published': True,
            'location_type': 'online',
            'staff_user_ids': [(4, cls.staff.id)],
        })

    def _booking_vals(self, **extra):
        start = fields.Datetime.now().replace(microsecond=0) + timedelta(days=2)
        vals = {
            'appointment_type_id': self.appointment_type.id,
            'guest_name': 'Alice Guest',
            'guest_email': 'alice.guest@example.com',
            'guest_phone': '+886912345678',
            'notes': 'Allergic to latex',
            'partner_id': self.portal_user.partner_id.id,
            'staff_user_id': self.staff.id,
            'start_datetime': start,
            'end_datetime': start + timedelta(hours=1),
        }
        vals.update(extra)
        return vals

    def _booking(self, **extra):
        return self.env['appointment.booking'].create(self._booking_vals(**extra))


@tagged('post_install', '-at_install')
class TestBookingCreateAcl(AclCommon, TransactionCase):
    """ae9d5f582106：portal／public 不能用 ORM 建出 confirmed 預約。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_acl_fixtures()

    def test_portal_cannot_create_confirmed_booking(self):
        Booking = self.env['appointment.booking'].with_user(self.portal_user)
        with self.assertRaises(AccessError):
            Booking.create(self._booking_vals(name='X-1', state='confirmed', guest_count=50))

    def test_public_cannot_create_booking(self):
        Booking = self.env['appointment.booking'].with_user(self.public_user)
        with self.assertRaises(AccessError):
            Booking.create(self._booking_vals(name='X-2', partner_id=False))

    def test_acl_rows_grant_no_create_to_portal_or_public(self):
        model = self.env['ir.model']._get('appointment.booking')
        rows = self.env['ir.model.access'].search([
            ('model_id', '=', model.id),
            ('group_id', 'in', [self.env.ref('base.group_portal').id,
                                self.env.ref('base.group_public').id]),
        ])
        self.assertTrue(rows)
        self.assertFalse(any(rows.mapped('perm_create')))
        self.assertFalse(any(rows.mapped('perm_write')))
        self.assertFalse(any(rows.mapped('perm_unlink')))

    def test_portal_still_reads_own_booking(self):
        booking = self._booking()
        found = self.env['appointment.booking'].with_user(self.portal_user).search([])
        self.assertEqual(found, booking)

    def test_appointment_user_can_still_create(self):
        booking = self.env['appointment.booking'].with_user(self.appt_user).create(
            self._booking_vals(staff_user_id=self.appt_user.id))
        self.assertEqual(booking.state, 'draft')
        self.assertNotEqual(booking.name, 'New')


@tagged('post_install', '-at_install')
class TestBookingInternalFields(AclCommon, TransactionCase):
    """19d40a392b21：internal_notes 等員工欄位不回傳給 portal 擁有者。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_acl_fixtures()

    def test_portal_owner_cannot_read_internal_fields(self):
        booking = self._booking(internal_notes='VIP complaint, refund pending')
        as_portal = booking.with_user(self.portal_user)
        for fname in ('internal_notes', 'payment_failure_count', 'reminder_sent', 'access_token'):
            self.env.invalidate_all()
            with self.assertRaises(AccessError, msg=fname):
                as_portal.read([fname])
        # read() without explicit fields only returns the accessible ones
        readable = as_portal.check_field_access_rights('read', None)
        for fname in ('internal_notes', 'payment_failure_count', 'reminder_sent', 'access_token'):
            self.assertNotIn(fname, readable)
        self.env.invalidate_all()
        data = as_portal.read(['guest_name', 'state', 'notes'])[0]
        self.assertEqual(data['guest_name'], 'Alice Guest')

    def test_staff_reads_internal_notes(self):
        booking = self._booking(internal_notes='call back later')
        self.env.invalidate_all()
        self.assertEqual(
            booking.with_user(self.staff).read(['internal_notes'])[0]['internal_notes'],
            'call back later')

    def test_payment_failure_counter_still_works_under_sudo(self):
        booking = self._booking()
        booking.sudo()._handle_payment_failure('declined')
        self.assertEqual(booking.sudo().payment_failure_count, 1)


@tagged('post_install', '-at_install')
class TestBookingDiscussChannel(AclCommon, TransactionCase):
    """7e55b34147b1：線上預約會議室是成員制。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_acl_fixtures()

    def _confirm_with_discuss(self, booking):
        Booking = type(self.env['appointment.booking'])
        with patch.object(Booking, '_portal_discuss_installed', return_value=True):
            booking.action_confirm()
        return booking.discuss_channel_id

    def test_channel_is_members_only(self):
        booking = self._booking()
        channel = self._confirm_with_discuss(booking.with_user(self.public_user).sudo())
        self.assertTrue(channel)
        self.assertEqual(channel.channel_type, 'group')
        self.assertFalse(channel.group_public_id)
        self.assertEqual(
            set(channel.channel_member_ids.partner_id.ids),
            {self.staff.partner_id.id, self.portal_user.partner_id.id})

        Channel = self.env['discuss.channel']
        self.env.invalidate_all()
        self.assertFalse(Channel.with_user(self.other_portal).search([('id', '=', channel.id)]))
        with self.assertRaises(AccessError):
            channel.with_user(self.other_portal).check_access('read')
        with self.assertRaises(AccessError):
            self.env['discuss.channel.member'].with_user(self.other_portal).create({
                'channel_id': channel.id, 'partner_id': self.other_portal.partner_id.id})
        # employees who are not members do not see it either
        self.assertFalse(Channel.with_user(self.employee).search([('id', '=', channel.id)]))
        # guest and staff keep access
        self.assertEqual(Channel.with_user(self.portal_user).search([('id', '=', channel.id)]), channel)
        self.assertEqual(Channel.with_user(self.staff).search([('id', '=', channel.id)]), channel)

    def test_public_user_never_joins_channel(self):
        booking = self._booking(staff_user_id=False)
        channel = self._confirm_with_discuss(booking.with_user(self.public_user).sudo())
        self.assertNotIn(self.public_user.partner_id, channel.channel_member_ids.partner_id)
        self.assertEqual(channel.channel_member_ids.partner_id, self.portal_user.partner_id)

    def test_outsider_portal_confirmer_is_not_member(self):
        booking = self._booking()
        channel = self._confirm_with_discuss(booking.with_user(self.other_portal).sudo())
        self.assertNotIn(self.other_portal.partner_id, channel.channel_member_ids.partner_id)

    def test_cancel_archives_channel_for_non_member_staff(self):
        booking = self._booking(staff_user_id=self.appt_user.id)
        channel = self._confirm_with_discuss(booking)
        booking.write({'staff_user_id': self.staff.id})
        # a manager who is not in the room cancels from the backend
        booking.with_user(self.manager).action_cancel()
        self.assertFalse(channel.active)

    def test_soft_coupling_detects_both_module_names(self):
        Module = self.env['ir.module.module'].sudo()
        records = {}
        for name in ('cs_portal_discuss', 'woow_odoo_portal_discuss'):
            records[name] = Module.search([('name', '=', name)]) or Module.create(
                {'name': name, 'state': 'uninstalled'})
        Booking = self.env['appointment.booking']
        for installed in ('cs_portal_discuss', 'woow_odoo_portal_discuss'):
            for name, rec in records.items():
                rec.state = 'installed' if name == installed else 'uninstalled'
            self.assertTrue(Booking._portal_discuss_installed(), installed)
        for rec in records.values():
            rec.state = 'uninstalled'
        self.assertFalse(Booking._portal_discuss_installed())

    def test_portal_discussions_lists_room_for_members(self):
        """woow_odoo_portal_discuss 的 /my/discussions 以成員身分列出 group 頻道。"""
        if not self.env['ir.module.module'].search_count([
                ('name', '=', 'woow_odoo_portal_discuss'), ('state', '=', 'installed')]):
            self.skipTest('woow_odoo_portal_discuss not installed')
        booking = self._booking()
        channel = self._confirm_with_discuss(booking.with_user(self.public_user).sudo())
        Channel = self.env['discuss.channel']
        listing_domain = [
            ('channel_member_ids', 'any', [('partner_id', '=', self.portal_user.partner_id.id),
                                           ('is_pinned', '=', True)]),
            ('channel_type', 'in', ('chat', 'group')),
        ]
        self.assertIn(channel, Channel.with_user(self.portal_user).search(listing_domain))


@tagged('post_install', '-at_install')
class TestBookingCalendarPrivacy(AclCommon, TransactionCase):
    """7069da4039f2：預約 event 不讓其他員工看到訪客資料。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_acl_fixtures()
        cls.appointment_type.location_type = 'physical'

    def _read_event(self, event, user):
        self.env.invalidate_all()
        return event.with_user(user).read(['name', 'description', 'partner_ids'])[0]

    def test_event_hidden_from_other_employees(self):
        booking = self._booking()
        booking.action_confirm()
        event = booking.calendar_event_id
        self.assertEqual(event.privacy, 'private')
        self.assertTrue(event.is_appointment_booking)
        for user in (self.employee, self.appt_user):
            self.env.invalidate_all()
            Event = self.env['calendar.event'].with_user(user)
            self.assertFalse(Event.search([('id', '=', event.id)]), user.login)
            with self.assertRaises(AccessError):
                event.with_user(user).read(['name', 'description', 'partner_ids'])
            self.env.invalidate_all()
            with self.assertRaises(AccessError):
                event.with_user(user).write({'name': 'hijacked'})
            with self.assertRaises(AccessError):
                event.with_user(user).unlink()

    def test_no_search_oracle_on_guest_or_type(self):
        """員工不能用名稱／參加者／時間搜尋推出某訪客何時有預約。"""
        booking = self._booking()
        booking.action_confirm()
        guest = self.portal_user.partner_id
        for user in (self.employee, self.appt_user):
            self.env.invalidate_all()
            Event = self.env['calendar.event'].with_user(user)
            for domain in (
                [('name', 'ilike', 'Alice')],
                [('name', 'ilike', 'ACL Consult')],
                [('name', 'ilike', booking.name)],
                [('partner_ids', 'in', guest.ids)],
                [('attendee_ids.common_name', 'ilike', 'Alice')],
                [('start', '=', booking.start_datetime)],
            ):
                self.assertEqual(Event.search_count(domain), 0, (user.login, domain))
            Partner = self.env['res.partner'].with_user(user)
            self.assertFalse(Partner.browse(guest.id).meeting_ids, user.login)
            self.assertEqual(Partner.browse(guest.id).meeting_count, 0, user.login)
            self.assertFalse(Partner.search([
                ('id', '=', guest.id), ('meeting_ids.start', '=', booking.start_datetime)]))

    def test_attendee_rows_hidden_from_other_employees(self):
        booking = self._booking()
        booking.action_confirm()
        event = booking.calendar_event_id
        attendee = event.attendee_ids.filtered(lambda a: a.partner_id == self.portal_user.partner_id)
        self.assertTrue(attendee)
        for user in (self.employee, self.appt_user):
            self.env.invalidate_all()
            Attendee = self.env['calendar.attendee'].with_user(user)
            self.assertEqual(Attendee.search_read(
                [('event_id', '=', event.id)], ['common_name', 'email', 'phone']), [], user.login)
            self.assertFalse(Attendee.search([('common_name', 'ilike', 'Alice')]), user.login)
            with self.assertRaises(AccessError):
                attendee.with_user(user).read(['common_name', 'email', 'phone'])
            self.env.invalidate_all()
            with self.assertRaises(AccessError):
                attendee.with_user(user).write({'state': 'declined'})
            with self.assertRaises(AccessError):
                attendee.with_user(user).unlink()
        self.env.invalidate_all()
        self.assertEqual(attendee.state, 'needsAction')

    def test_organizer_and_manager_see_details(self):
        booking = self._booking()
        booking.action_confirm()
        event = booking.calendar_event_id
        for user in (self.staff, self.manager):
            data = self._read_event(event, user)
            self.assertEqual(data['name'], 'ACL Consult - %s' % booking.name, user.login)
            self.assertIn(booking.name, data['description'], user.login)
            self.assertEqual(data['partner_ids'], self.portal_user.partner_id.ids, user.login)
            self.env.invalidate_all()
            rows = self.env['calendar.attendee'].with_user(user).search_read(
                [('event_id', '=', event.id)], ['common_name', 'email'])
            self.assertEqual([(r['common_name'], r['email']) for r in rows],
                             [('Alice Guest', 'acl_portal_guest@example.com')], user.login)
            self.assertEqual(self.env['calendar.event'].with_user(user).search_count(
                [('partner_ids', 'in', self.portal_user.partner_id.ids)]), 1, user.login)

    def test_attendee_guest_sees_own_event(self):
        """訪客本身是內部使用者時，仍看得到自己的 event 與參加者列。"""
        booking = self._booking(partner_id=self.employee.partner_id.id)
        booking.action_confirm()
        event = booking.calendar_event_id
        self.env.invalidate_all()
        self.assertEqual(
            self.env['calendar.event'].with_user(self.employee).search([('id', '=', event.id)]), event)
        self.assertTrue(self.env['calendar.attendee'].with_user(self.employee).search(
            [('event_id', '=', event.id)]))

    def test_title_has_no_guest_name(self):
        booking = self._booking()
        booking.action_confirm()
        self.assertNotIn('Alice', booking.calendar_event_id.name)

    def test_other_private_events_keep_core_behaviour(self):
        """不是預約建立的 event 不受影響：其他員工照 core 看到 Busy 與參加者列。"""
        other = self._user('acl_colleague', ['base.group_user'])
        event = self.env['calendar.event'].with_user(other).create({
            'name': 'Dentist',
            'start': fields.Datetime.now() + timedelta(days=1),
            'stop': fields.Datetime.now() + timedelta(days=1, hours=1),
            'privacy': 'private',
            'partner_ids': [(6, 0, [other.partner_id.id])],
        })
        self.env.invalidate_all()
        data = self._read_event(event, self.employee)
        self.assertEqual(data['name'], 'Busy')
        self.env.invalidate_all()
        self.assertTrue(self.env['calendar.attendee'].with_user(self.employee).search(
            [('event_id', '=', event.id)]))

    def test_staff_reassignment_moves_event_organizer(self):
        other_staff = self._user('acl_staff_two', ['reservation_module.group_appointment_user'])
        self.appointment_type.staff_user_ids = [(4, other_staff.id)]
        booking = self._booking()
        booking.action_confirm()
        event = booking.calendar_event_id
        booking.staff_user_id = other_staff
        self.assertEqual(event.user_id, other_staff)
        self.env.invalidate_all()
        self.assertEqual(
            self.env['calendar.event'].with_user(other_staff).search([('id', '=', event.id)]), event)
        self.assertFalse(
            self.env['calendar.event'].with_user(self.staff).search([('id', '=', event.id)]))

    def test_description_has_no_guest_contact_details(self):
        booking = self._booking()
        booking.action_confirm()
        description = booking.sudo().calendar_event_id.description or ''
        for secret in ('alice.guest@example.com', '912345678', 'latex'):
            self.assertNotIn(secret, description)

    def test_anonymous_confirmation_has_no_public_organizer(self):
        booking = self._booking(staff_user_id=False)
        booking.with_user(self.public_user).sudo().action_confirm()
        event = booking.sudo().calendar_event_id
        self.assertTrue(event)
        self.assertFalse(event.user_id)
        self.assertEqual(event.privacy, 'private')

    def test_backend_creator_confirms_and_cancels(self):
        """建立者不是主辦人時仍能確認、改時間、取消（event 由系統代為維護）。"""
        booking = self.env['appointment.booking'].with_user(self.appt_user).create(
            self._booking_vals())
        booking.action_confirm()
        event = booking.sudo().calendar_event_id
        self.assertEqual(event.user_id, self.staff)
        new_start = booking.start_datetime + timedelta(hours=2)
        booking.write({'start_datetime': new_start, 'end_datetime': new_start + timedelta(hours=1)})
        self.assertEqual(event.sudo().start, new_start)
        booking.action_cancel()
        self.assertFalse(event.exists())


@tagged('post_install', '-at_install')
class TestMigration3_2_2(AclCommon, TransactionCase):
    """既有資料的收緊與可重跑。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_acl_fixtures()
        cls.mig = _load_migration_3_2_2()

    def test_legacy_channel_made_members_only(self):
        booking = self._booking()
        portal_group = self.env.ref('base.group_portal')
        channel = self.env['discuss.channel'].sudo().create({
            'name': 'legacy room',
            'channel_type': 'channel',
            'group_public_id': portal_group.id,
            'channel_member_ids': [(0, 0, {'partner_id': pid}) for pid in (
                self.staff.partner_id.id, self.portal_user.partner_id.id,
                self.other_portal.partner_id.id, self.public_user.partner_id.id)],
        })
        booking.discuss_channel_id = channel
        self.env.flush_all()

        converted, removed = self.mig._migrate_discuss_channels(self.env.cr)
        self.assertEqual(converted, 1)
        self.assertEqual(removed, 2)
        self.env.invalidate_all()
        self.assertEqual(channel.channel_type, 'group')
        self.assertFalse(channel.group_public_id)
        members = channel.channel_member_ids.partner_id
        self.assertIn(self.staff.partner_id, members)
        self.assertIn(self.portal_user.partner_id, members)
        self.assertNotIn(self.other_portal.partner_id, members)
        self.assertNotIn(self.public_user.partner_id, members)
        self.assertFalse(
            self.env['discuss.channel'].with_user(self.other_portal).search([('id', '=', channel.id)]))

        self.assertEqual(self.mig._migrate_discuss_channels(self.env.cr), (0, 0))

    def test_legacy_event_made_private(self):
        # Bring any booking event already in the database to the target
        # state first, so the counts below only see this test's event.
        self.mig._migrate_calendar_events(self.env)
        booking = self._booking()
        event = self.env['calendar.event'].sudo().create({
            'name': 'ACL Consult - Alice Guest',
            'start': booking.start_datetime,
            'stop': booking.end_datetime,
            'user_id': self.staff.id,
            'description': 'Guest: Alice Guest\nEmail: alice.guest@example.com\nPhone: +886912345678',
        })
        booking.calendar_event_id = event
        self.env.flush_all()

        self.assertTrue(self.env['calendar.event'].with_user(self.employee).search(
            [('name', 'ilike', 'Alice')]))
        self.assertEqual(self.mig._migrate_calendar_events(self.env), 1)
        self.assertEqual(event.privacy, 'private')
        self.assertTrue(event.is_appointment_booking)
        self.assertEqual(event.name, 'ACL Consult - %s' % booking.name)
        self.env.invalidate_all()
        self.assertFalse(self.env['calendar.event'].with_user(self.employee).search(
            [('id', '=', event.id)]))
        self.assertNotIn('alice.guest@example.com', event.description or '')
        self.assertIn(booking.name, event.description or '')
        self.assertEqual(self.mig._migrate_calendar_events(self.env), 0)


@tagged('post_install', '-at_install')
class TestBookFormRosterNames(TimezoneCommon, HttpCase):
    """4c2649c2216d：預約表單不顯示名單外的使用者／場地名稱。"""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'reservation_module.require_authenticated_booking', 'False')
        self.roster_staff = self.env['res.users'].create({
            'name': 'Rosterstaff Visibleperson', 'login': 'roster_staff_visible'})
        self.outsider = self.env['res.users'].create({
            'name': 'Zzhidden Outsideruser', 'login': 'zz_hidden_outsider'})
        self.roster_room = self.env['resource.resource'].create({
            'name': 'Rosterroom Visibleplace', 'resource_type': 'material', 'capacity': 3})
        self.other_room = self.env['resource.resource'].create({
            'name': 'Zzhidden Otherroom', 'resource_type': 'material'})
        self.appointment_type = self._setup_appointment_type(
            assign_staff=True, assign_location=True,
            staff_user_ids=[(6, 0, [self.roster_staff.id])],
            resource_ids=[(6, 0, [self.roster_room.id])],
        )
        self.env['appointment.type'].create({
            'name': 'Other Type', 'slot_duration': 1.0, 'is_published': True,
            'resource_ids': [(6, 0, [self.other_room.id])], 'assign_location': True,
        })
        start = (fields.Datetime.now() + timedelta(days=3)).replace(
            hour=3, minute=0, second=0, microsecond=0)
        self.start = start.strftime('%Y-%m-%d %H:%M:%S')
        self.book_url = '/appointment/%d/book' % self.appointment_type.id

    def _get(self, staff_id, resource_id):
        return self.url_open('%s?start_datetime=%s&staff_id=%s&resource_id=%s' % (
            self.book_url, self.start.replace(' ', '%20'), staff_id, resource_id))

    def test_outsider_ids_are_not_rendered(self):
        page = self._get(self.outsider.id, self.other_room.id)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('Zzhidden Outsideruser', page.text)
        self.assertNotIn('Zzhidden Otherroom', page.text)
        self.assertNotIn('name="staff_id" value="%d"' % self.outsider.id, page.text)

    def test_unknown_ids_do_not_error(self):
        page = self._get(987654321, 987654321)
        self.assertEqual(page.status_code, 200)

    def test_roster_ids_still_rendered(self):
        page = self._get(self.roster_staff.id, self.roster_room.id)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Rosterstaff Visibleperson', page.text)
        self.assertIn('Rosterroom Visibleplace', page.text)

    def _csrf(self):
        page = self._get(self.roster_staff.id, self.roster_room.id)
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text) or re.search(
            r'value="([^"]+)"[^>]*name="csrf_token"', page.text)
        self.assertTrue(match)
        return match.group(1)

    def _post_guests(self, resource, guest_count):
        return self.url_open(self.book_url, data={
            'csrf_token': self._csrf(),
            'start_datetime': self.start,
            'staff_id': str(self.roster_staff.id),
            'resource_id': str(resource.id),
            'guest_name': 'Capacity Probe',
            'guest_email': 'probe@example.com',
            'guest_count': str(guest_count),
        })

    def test_guest_limit_ignores_off_roster_resource_capacity(self):
        """名單外場地的容量不會出現在錯誤訊息裡。"""
        self.other_room.capacity = 1
        response = self._post_guests(self.other_room, 2)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Maximum 1 guests allowed', response.text)

    def test_guest_limit_uses_roster_resource_capacity(self):
        response = self._post_guests(self.roster_room, 5)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Maximum 3 guests allowed', response.text)

    def test_error_render_drops_outsider_ids(self):
        page = self._get(self.roster_staff.id, self.roster_room.id)
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text) or re.search(
            r'value="([^"]+)"[^>]*name="csrf_token"', page.text)
        self.assertTrue(match)
        response = self.url_open(self.book_url, data={
            'csrf_token': match.group(1),
            'start_datetime': self.start,
            'staff_id': str(self.outsider.id),
            'resource_id': str(self.other_room.id),
            'guest_name': '',  # missing required field -> error re-render
            'guest_email': 'roster@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Please fill in all required fields', response.text)
        self.assertNotIn('Zzhidden Outsideruser', response.text)
        self.assertNotIn('Zzhidden Otherroom', response.text)
