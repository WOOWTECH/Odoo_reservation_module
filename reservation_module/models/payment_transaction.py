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

    def _post_process(self):
        """Override of `payment` to update booking status after payment.

        Supports two payment flows:
        1. Direct booking transaction (legacy): appointment_booking_id is set directly.
        2. Sales order flow: SO is linked to booking via sale_order_id.
           Odoo's sale module handles SO confirmation and invoice creation
           via its own _post_process override; we update the booking status
           and create invoices if the sale module didn't (safety net).
        """
        # Let parent (sale module, base payment) do their work first.
        super()._post_process()

        Booking = self.env['appointment.booking'].sudo()

        # Handle payment failures (webhook-triggered)
        for tx in self.filtered(lambda t: t.state in ('error', 'cancel')):
            booking = tx.appointment_booking_id
            if not booking and hasattr(tx, 'sale_order_ids'):
                for so in tx.sale_order_ids:
                    booking = Booking.search([
                        ('sale_order_id', '=', so.id),
                        ('payment_status', '=', 'pending'),
                    ], limit=1)
                    if booking:
                        break
            if booking:
                booking._handle_payment_failure(
                    error_message=tx.state_message or tx.state
                )

        for tx in self.filtered(lambda t: t.state == 'done'):
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
                    if not bookings:
                        continue

                    # Ensure invoice is created (safety net — sale module
                    # may already have done this if sale.automatic_invoice
                    # is enabled)
                    try:
                        if not so.invoice_ids:
                            so.sudo()._create_invoices()
                            for invoice in so.invoice_ids.filtered(
                                lambda inv: inv.state == 'draft'
                            ):
                                invoice.sudo().action_post()
                    except Exception:
                        _logger.exception(
                            "Failed to create/post invoice for SO %s",
                            so.name,
                        )

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
                                    "Failed to auto-confirm booking %s "
                                    "after SO %s payment tx %s",
                                    booking.name, so.name, tx.reference,
                                )
