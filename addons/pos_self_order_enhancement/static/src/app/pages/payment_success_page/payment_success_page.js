/** @odoo-module */

import { Component } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";

/**
 * Payment Success Page
 * Displays after successful payment with option to order again
 */
export class PaymentSuccessPage extends Component {
    static template = "pos_self_order_enhancement.PaymentSuccessPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
    }

    /**
     * Get the last completed order reference
     */
    get orderReference() {
        try {
            const order = this.selfOrder.currentOrder;
            return order?.pos_reference ||
                   order?.tracking_number ||
                   order?.name ||
                   '';
        } catch (e) {
            return '';
        }
    }

    /**
     * Get the payment amount
     */
    get paymentAmount() {
        try {
            return this.selfOrder.currentOrder?.amount_total || 0;
        } catch (e) {
            return 0;
        }
    }

    /**
     * Format currency for display
     */
    formatCurrency(amount) {
        try {
            const currency = this.selfOrder.currency;
            if (!currency) {
                return `NT$ ${amount.toFixed(0)}`;
            }
            return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
        } catch (e) {
            return `NT$ ${amount}`;
        }
    }

    /**
     * Start a new order (Order Again)
     */
    orderAgain() {
        try {
            // Reset current order state to start fresh
            this.selfOrder.selectedOrderUuid = null;

            // Navigate back to landing page
            this.router.navigate("landing");
        } catch (e) {
            console.error("Error starting new order:", e);
            // Fallback: just navigate to landing
            this.router.navigate("landing");
        }
    }
}
