# -*- coding: utf-8 -*-

import logging

import psycopg2

from odoo import api, fields, models, _
from odoo.exceptions import UserError

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
        """Payment-required bookings still waiting for this transaction.

        Only the orders' own bookings: a row of another customer pointing at
        the order (written before 18.0.3.2.2) must not refuse the order's
        payment because its own slot is gone.
        """
        bookings = self.env['appointment.booking'].sudo()
        for tx in self:
            bookings |= tx.appointment_booking_id.sudo()
            if 'sale_order_ids' in tx._fields:
                for order in tx.sale_order_ids:
                    bookings |= order._get_own_bookings()
        return bookings.filtered(lambda b: b.state in ('draft', 'pending_payment'))

    def _check_bookings_payable(self):
        """Refuse a payment that would pay a booking a second time.

        * the booking's own pay page: the booking must still be open for
          payment (not cancelled or finished) and not paid yet;
        * a payment of an order: none of the bookings whose lines are in the
          order may be paid already (a paid booking's lines normally leave the
          cart, see appointment.booking _settle_order_after_own_payment; if
          they could not, the cart must not charge them again).
        """
        for tx in self:
            if tx.appointment_booking_id:
                tx.appointment_booking_id.sudo()._check_open_for_payment()
            if 'sale_order_ids' not in tx._fields:
                continue
            for order in tx.sale_order_ids:
                for booking in order._get_own_bookings():
                    if (booking.sale_order_id == order and booking._get_payment_lines()
                            and booking._is_covered_by_payment()):
                        raise UserError(_(
                            'Booking %(booking)s in order %(order)s has already been paid, so the order '
                            'cannot be paid again. Please contact support.',
                            booking=booking.name, order=order.name))

    @api.model_create_multi
    def create(self, vals_list):
        """Refuse to take a payment for a booking whose slot is gone, or that
        is paid already.

        Covers every core payment route (/shop/payment/transaction,
        /my/orders/<id>/transaction, ...): the booking's slot is re-checked
        under the conflict guard and its hold renewed for the payment window.

        The transaction and the checks are one savepoint. The checks run after
        the row exists (they need it to find the bookings it pays), so a
        refusal under a race (the slot sold, the booking paid, between the
        page and this call) would otherwise leave a draft transaction behind
        whenever the caller catches the refusal and goes on, as the pay
        page's route does: an orphan that the booking's transaction list, the
        provider reference and the cancel-time money search would all see.
        """
        with self.env.cr.savepoint():
            txs = super().create(vals_list)
            for tx in txs:
                if tx.operation in ('refund', 'validation'):
                    continue
                tx._check_bookings_payable()
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

        # Handle payment failures (webhook-triggered). Only an order's own
        # booking: the failure mail goes to the guest's address and links to
        # the order with its access token. The one still to pay is found by
        # the status worked out now, not the stored one.
        for tx in self.filtered(lambda t: t.state in ('error', 'cancel')):
            booking = tx.appointment_booking_id
            if not booking and hasattr(tx, 'sale_order_ids'):
                for so in tx.sale_order_ids:
                    booking = so._get_own_bookings().filtered(
                        lambda b: b._get_live_payment_status() == 'pending')[:1]
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
                if booking.state == 'cancelled':
                    # Paid after the booking was cancelled (a payment started
                    # earlier, e.g. a transfer): staff must refund it.
                    booking._flag_paid_cancellation(tx)
                else:
                    # Its lines must not be payable a second time from the cart.
                    booking._settle_order_after_own_payment(tx)

            # Flow 2: Sales order linked booking
            if hasattr(tx, 'sale_order_ids'):
                for so in tx.sale_order_ids:
                    # A booking cancelled while this payment was on its way
                    # (a transfer): its lines are still in the order, so the
                    # money is in and nobody has given it back.
                    for booking in so._get_own_bookings().filtered(
                            lambda b: b.state == 'cancelled' and b._order_holds_booking_lines(so)):
                        booking._flag_paid_cancellation(tx)
                    # By state, not payment_status: once the sale module has
                    # reconciled the invoice the status is already 'paid', and
                    # searching 'pending' silently skipped the confirmation.
                    # Only the order's own bookings, and only those whose own
                    # lines this payment pays: paying for something else in a
                    # shared cart must neither hold nor confirm (nor flag) a
                    # booking.
                    bookings = so._get_own_bookings().filtered(
                        lambda b: b.state in ('draft', 'pending_payment') and b._is_paid_by(tx))
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
