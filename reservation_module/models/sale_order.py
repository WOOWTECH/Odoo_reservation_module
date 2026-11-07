# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# Context key set by the booking code itself when it adds, removes or binds
# the sale order lines of a booking (see appointment.booking).
BOOKING_LINE_EDIT_CTX = 'reservation_booking_line_edit'


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
        """Override: SO 簽回不自動確認預約。

        預約只在實際付款後才確認（由 payment_transaction._post_process 處理）。
        SO 簽回只代表客戶同意報價，不代表已付款。
        """
        return super().action_confirm()

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


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # The lines a booking added to its order (section + one line per payment
    # product). The booking is paid only when these very lines are invoiced
    # and paid (appointment.booking._compute_payment_status); in cart mode the
    # same order may also hold other products and other bookings.
    appointment_booking_id = fields.Many2one(
        'appointment.booking', string='Booking', index='btree_not_null',
        copy=False, readonly=True, ondelete='set null')
    # Quantity the booking needs on this line (guests, or 1).
    appointment_booking_qty = fields.Float(
        'Booking Quantity', copy=False, readonly=True, digits='Product Unit of Measure')

    def _booking_line_edit_allowed(self):
        """Customers (public/portal visitors, even through the sudo website
        cart) cannot change the lines of a booking; staff and the booking code
        itself can."""
        return self.env.context.get(BOOKING_LINE_EDIT_CTX) or self.env.user._is_internal()

    @api.model_create_multi
    def create(self, vals_list):
        if not self._booking_line_edit_allowed():
            for vals in vals_list:
                vals.pop('appointment_booking_id', None)
                vals.pop('appointment_booking_qty', None)
        return super().create(vals_list)

    def write(self, vals):
        booking_lines = self.filtered('appointment_booking_id')
        if booking_lines and not self._booking_line_edit_allowed():
            locked = {'appointment_booking_id', 'appointment_booking_qty', 'order_id',
                      'product_id', 'product_uom', 'display_type'}
            if locked & set(vals):
                raise UserError(_(
                    'This line belongs to a booking. Cancel the booking to remove it from the order.'))
            if 'product_uom_qty' in vals:
                for line in booking_lines.filtered(lambda l: not l.display_type):
                    if float_compare(vals['product_uom_qty'] or 0.0, line.appointment_booking_qty,
                                     precision_rounding=line.product_uom.rounding or 0.01) < 0:
                        raise UserError(_(
                            'The quantity of booking %(booking)s cannot be lowered here. '
                            'Cancel the booking and book again to change it.',
                            booking=line.appointment_booking_id.sudo().name))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_booking_line(self):
        if self._booking_line_edit_allowed():
            return
        # The cart page drops lines of archived products by itself: let it, the
        # booking simply stays unpaid then.
        if self.filtered(lambda l: l.appointment_booking_id
                         and (l.display_type or l.product_id.active)):
            raise UserError(_(
                'This line belongs to a booking. Cancel the booking to remove it from the order.'))
