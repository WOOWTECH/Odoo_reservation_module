/** @odoo-module */

import { ConfirmationPage } from "@pos_self_order/app/pages/confirmation_page/confirmation_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch ConfirmationPage to support both payment modes:
 *
 * 1. "Pay per Meal" (meal) mode:
 *    - After order submission, redirect to payment page
 *    - Supports online payment or counter payment
 *
 * 2. "Pay per Order" (each) mode:
 *    - After order submission, show "Back to Home" and "My Orders" buttons
 *    - Allow customers to continue ordering or go to checkout later
 */
patch(ConfirmationPage.prototype, {
    /**
     * Check if the POS is configured for "Pay per Meal" mode.
     * @returns {boolean}
     */
    get isPayPerMeal() {
        try {
            return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
        } catch (e) {
            return false;
        }
    },

    /**
     * Check if the POS is configured for "Pay per Order" mode.
     * @returns {boolean}
     */
    get isPayPerOrder() {
        try {
            return this.selfOrder?.config?.self_ordering_pay_after === 'each';
        } catch (e) {
            return false;
        }
    },

    /**
     * Check if we should show the "Pay per Meal" UI (redirect to payment).
     * Only show when:
     * - Mode is "meal" (pay per meal)
     * - Order is not yet paid
     * - In mobile mode (not kiosk)
     * @returns {boolean}
     */
    get showPayPerMealUI() {
        try {
            if (!this.isPayPerMeal) {
                return false;
            }
            const order = this.confirmedOrder;
            if (!order || !order.id) {
                return false;
            }
            const isPaid = order.state === 'paid';
            const isMobile = this.selfOrder?.config?.self_ordering_mode === 'mobile';
            return !isPaid && isMobile;
        } catch (e) {
            return false;
        }
    },

    /**
     * Check if we should show the "Pay per Order" UI.
     * Only show when:
     * - Mode is "each" (pay per order)
     * - Order is not yet paid
     * - In mobile mode (not kiosk)
     * @returns {boolean}
     */
    get showPayPerOrderUI() {
        try {
            if (!this.isPayPerOrder) {
                return false;
            }
            const order = this.confirmedOrder;
            if (!order || !order.id) {
                return false;
            }
            const isPaid = order.state === 'paid';
            const isMobile = this.selfOrder?.config?.self_ordering_mode === 'mobile';
            return !isPaid && isMobile;
        } catch (e) {
            return false;
        }
    },

    /**
     * Navigate to payment page (for Pay per Meal mode).
     */
    goToPayment() {
        this.router.navigate("payment");
    },

    /**
     * Navigate back to landing page.
     */
    goToLanding() {
        this.router.navigate("landing");
    },

    /**
     * Navigate to order history page for checkout.
     */
    goToMyOrders() {
        this.router.navigate("order_history");
    },
});
