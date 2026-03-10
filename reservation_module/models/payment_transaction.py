# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    appointment_booking_id = fields.Many2one(
        'appointment.booking',
        string='預約',
        ondelete='set null',
        help='關聯的預約記錄',
    )

    def _post_process_after_done(self):
        """Handle post-processing after payment is completed."""
        super()._post_process_after_done()

        # Update linked appointment booking payment status
        for tx in self:
            if tx.appointment_booking_id:
                booking = tx.appointment_booking_id
                booking.write({
                    'payment_status': 'paid',
                    'payment_transaction_id': tx.id,
                })
                # Auto confirm if enabled
                if booking.appointment_type_id.auto_confirm:
                    try:
                        booking.action_confirm()
                    except Exception:
                        # Log but don't fail if confirmation fails
                        pass
