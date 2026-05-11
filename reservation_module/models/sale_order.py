# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    booking_ids = fields.One2many(
        'appointment.booking',
        'sale_order_id',
        string='Bookings',
    )
    booking_count = fields.Integer(
        'Booking Count',
        compute='_compute_booking_count',
    )

    @api.depends('booking_ids')
    def _compute_booking_count(self):
        for order in self:
            order.booking_count = len(order.booking_ids)

    def action_confirm(self):
        """Override to auto-confirm linked bookings when SO is confirmed.

        When a customer signs the quotation (SO → sale), linked bookings
        with auto_confirm enabled are automatically confirmed. The
        payment_status compute field already treats SO state='sale' as
        'paid', so action_confirm's payment gate will pass.
        """
        res = super().action_confirm()
        for order in self:
            for booking in order.booking_ids:
                if booking.state in ('draft', 'pending_payment') \
                        and booking.appointment_type_id.auto_confirm:
                    try:
                        booking.action_confirm()
                    except Exception:
                        _logger.warning(
                            "Failed to auto-confirm booking %s on SO %s confirm",
                            booking.name, order.name,
                        )
        return res

    def action_view_bookings(self):
        """Open bookings linked to this sales order"""
        self.ensure_one()
        bookings = self.booking_ids
        if len(bookings) == 1:
            return {
                'name': _('Booking'),
                'type': 'ir.actions.act_window',
                'res_model': 'appointment.booking',
                'view_mode': 'form',
                'res_id': bookings.id,
            }
        return {
            'name': _('Bookings'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.booking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bookings.ids)],
        }
