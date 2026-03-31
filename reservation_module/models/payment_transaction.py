# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    appointment_booking_id = fields.Many2one(
        'appointment.booking',
        string='Booking',
        ondelete='set null',
        help='Related booking record',
    )

    def _post_process_after_done(self):
        """Handle post-processing after payment is completed.

        Supports two payment flows:
        1. Direct booking transaction (legacy): appointment_booking_id is set directly.
        2. Sales order flow: SO is linked to booking via sale_order_id.
           Odoo's sale module handles invoice creation; we update the booking status.
        """
        super()._post_process_after_done()

        Booking = self.env['appointment.booking'].sudo()

        for tx in self:
            # Flow 1: Direct booking transaction (backward compat)
            if tx.appointment_booking_id:
                booking = tx.appointment_booking_id
                booking.write({
                    'payment_status': 'paid',
                    'payment_transaction_id': tx.id,
                })
                if booking.appointment_type_id.auto_confirm:
                    try:
                        booking.action_confirm()
                    except Exception:
                        _logger.exception(
                            "Failed to auto-confirm booking %s after payment tx %s",
                            booking.name, tx.reference,
                        )

            # Flow 2: Sales order linked booking
            if hasattr(tx, 'sale_order_ids'):
                for so in tx.sale_order_ids:
                    bookings = Booking.search([
                        ('sale_order_id', '=', so.id),
                        ('payment_status', '=', 'pending'),
                    ])
                    for booking in bookings:
                        booking.write({
                            'payment_status': 'paid',
                            'payment_transaction_id': tx.id,
                        })
                        if booking.appointment_type_id.auto_confirm:
                            try:
                                booking.action_confirm()
                            except Exception:
                                _logger.exception(
                                    "Failed to auto-confirm booking %s after SO %s payment tx %s",
                                    booking.name, so.name, tx.reference,
                                )
