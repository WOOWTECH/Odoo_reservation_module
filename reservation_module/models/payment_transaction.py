# -*- coding: utf-8 -*-

import logging

import psycopg2

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
    # Set once the booking side has handled this transaction's failure, so the
    # return page and the webhook together report one failed tx only once.
    appointment_failure_notified = fields.Boolean(
        'Booking Failure Handled', copy=False, readonly=True)

    def _get_held_bookings(self):
        """Payment-required bookings still waiting for this transaction."""
        Booking = self.env['appointment.booking'].sudo()
        bookings = Booking.browse()
        for tx in self:
            bookings |= tx.appointment_booking_id.sudo()
            if 'sale_order_ids' in tx._fields and tx.sale_order_ids:
                bookings |= Booking.search([('sale_order_id', 'in', tx.sale_order_ids.ids)])
        return bookings.filtered(lambda b: b.state in ('draft', 'pending_payment'))

    @api.model_create_multi
    def create(self, vals_list):
        """Refuse to take a payment for a booking whose slot is gone.

        Covers every core payment route (/shop/payment/transaction,
        /my/orders/<id>/transaction, ...): the booking's slot is re-checked
        under the conflict guard and its hold renewed for the payment window.
        """
        txs = super().create(vals_list)
        for tx in txs:
            if tx.operation in ('refund', 'validation'):
                continue
            tx._get_held_bookings()._ensure_payment_hold()
        return txs

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
            if (booking and booking.state in ('draft', 'pending_payment')
                    and booking.appointment_type_id.require_payment):
                booking._handle_payment_failure(
                    error_message=tx.state_message or tx.state,
                    transaction=tx,
                )

        # Payment started but not settled yet (e.g. wire transfer): keep the
        # slot longer than the short payment window, but only for bookings
        # whose own lines this payment pays (not for a cheap other item of a
        # shared cart).
        for tx in self.filtered(lambda t: t.state in ('pending', 'authorized')):
            tx._get_held_bookings().filtered(
                lambda b: b._tx_covers_booking(tx))._hold_for_pending_payment()

        for tx in self.filtered(lambda t: t.state == 'done'):
            # Flow 1: Direct booking transaction (backward compat)
            if tx.appointment_booking_id:
                booking = tx.appointment_booking_id.sudo()
                booking.write({
                    'payment_transaction_id': tx.id,
                })
                booking._confirm_after_payment(tx)

            # Flow 2: Sales order linked booking
            if hasattr(tx, 'sale_order_ids'):
                for so in tx.sale_order_ids:
                    # By state, not payment_status: once the sale module has
                    # reconciled the invoice the status is already 'paid', and
                    # searching 'pending' silently skipped the confirmation.
                    bookings = Booking.search([
                        ('sale_order_id', '=', so.id),
                        ('state', 'in', ('draft', 'pending_payment')),
                    ])
                    # Only bookings whose own lines this payment pays: paying
                    # for something else in a shared cart must neither hold
                    # nor confirm (nor flag) a booking.
                    bookings = bookings.filtered(lambda b: b._is_paid_by(tx))
                    if not bookings:
                        continue

                    # Ensure invoice is created (safety net — sale module
                    # may already have done this if sale.automatic_invoice
                    # is enabled)
                    try:
                        with self.env.cr.savepoint():
                            if not so.invoice_ids:
                                so.sudo()._create_invoices()
                                for invoice in so.invoice_ids.filtered(
                                    lambda inv: inv.state == 'draft'
                                ):
                                    invoice.sudo().action_post()
                    except Exception as error:
                        if isinstance(error, psycopg2.Error):
                            raise  # concurrency errors belong to Odoo's retry loop
                        _logger.exception(
                            "Failed to create/post invoice for SO %s",
                            so.name,
                        )

                    for booking in bookings:
                        booking.write({
                            'payment_transaction_id': tx.id,
                        })
                        booking._confirm_after_payment(tx)
