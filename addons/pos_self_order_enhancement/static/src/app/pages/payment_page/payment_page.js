/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";

/**
 * Custom Payment Page for Pay-per-Meal mode
 * Handles both online payment and counter payment scenarios
 */
export class PaymentPage extends Component {
    static template = "pos_self_order_enhancement.PaymentPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
        this.state = useState({
            loading: false,
            error: null,
        });
    }

    /**
     * Get the current order
     */
    get currentOrder() {
        return this.selfOrder.currentOrder;
    }

    /**
     * Get order lines for display
     */
    get orderLines() {
        try {
            return this.currentOrder?.lines || [];
        } catch (e) {
            return [];
        }
    }

    /**
     * Get order total amount
     */
    get totalAmount() {
        try {
            return this.currentOrder?.amount_total || 0;
        } catch (e) {
            return 0;
        }
    }

    /**
     * Get order reference/number
     */
    get orderReference() {
        try {
            return this.currentOrder?.pos_reference ||
                   this.currentOrder?.tracking_number ||
                   this.currentOrder?.name ||
                   '';
        } catch (e) {
            return '';
        }
    }

    /**
     * Check if online payment methods are available
     */
    get hasOnlinePayment() {
        try {
            // Check for configured online payment method
            const onlinePaymentMethodId = this.selfOrder.config.self_ordering_online_payment_method_id;
            return onlinePaymentMethodId && onlinePaymentMethodId.length > 0;
        } catch (e) {
            return false;
        }
    }

    /**
     * Get available online payment methods
     */
    get onlinePaymentMethods() {
        try {
            const allMethods = this.selfOrder.models["pos.payment.method"].getAll();
            // Filter to only online payment capable methods
            return allMethods.filter(method => {
                return method.is_online_payment ||
                       ["adyen", "stripe"].includes(method.use_payment_terminal);
            });
        } catch (e) {
            return [];
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
     * Go back to previous page
     */
    goBack() {
        this.router.navigate("cart");
    }

    /**
     * Handle online payment selection
     */
    async selectOnlinePayment(paymentMethodId) {
        this.state.loading = true;
        this.state.error = null;

        try {
            // Process online payment through Odoo's payment flow
            await this.selfOrder.processOnlinePayment(paymentMethodId);
            // Navigation will be handled by the payment service
        } catch (error) {
            console.error("Online payment error:", error);
            this.state.error = "付款處理失敗，請重試";
            this.state.loading = false;
        }
    }

    /**
     * Handle counter payment confirmation
     * Customer confirms they have paid at counter
     */
    async confirmCounterPayment() {
        this.state.loading = true;
        this.state.error = null;

        try {
            // Mark the order as payment confirmed (for counter payment flow)
            // The actual payment will be handled by staff at POS

            // Navigate to success page
            this.router.navigate("payment_success");
        } catch (error) {
            console.error("Counter payment confirmation error:", error);
            this.state.error = "確認失敗，請重試";
            this.state.loading = false;
        }
    }
}
