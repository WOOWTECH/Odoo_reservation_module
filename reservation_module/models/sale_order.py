# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


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
