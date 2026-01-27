/** @odoo-module */

import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch LandingPage to add "Continue Ordering" button.
 *
 * Business Logic:
 * - When customer has an existing unpaid order, show "Continue Ordering" button
 * - Button appears below "My Order" button with the same style
 * - Clicking navigates directly to product list to add more items
 * - Only shown in mobile mode with pay_after="each" configuration
 */
patch(LandingPage.prototype, {
    /**
     * Navigate to product list to continue adding items to existing order.
     */
    continueOrdering() {
        // Get the current draft order
        const orders = this.draftOrder;
        if (orders && orders.length > 0) {
            // Set the selected order UUID to the first draft order
            const order = orders[0];
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }
        }
        // Navigate to product list page
        this.router.navigate("product_list");
    },

    /**
     * Check if the "Continue Ordering" button should be displayed.
     * Only show when:
     * - Customer has existing unpaid/draft orders
     * - In mobile mode (not kiosk)
     * - pay_after is set to "each"
     */
    get showContinueOrderingBtn() {
        try {
            // Safety check for selfOrder and config
            if (!this.selfOrder || !this.selfOrder.config) {
                return false;
            }

            // Check configuration: mobile mode with pay_after="each"
            const isMobile = this.selfOrder.config.self_ordering_mode === "mobile";
            const payAfterEach = this.selfOrder.config.self_ordering_pay_after === "each";

            if (!isMobile || !payAfterEach) {
                return false;
            }

            // Check if there are draft orders
            const orders = this.draftOrder;
            if (!orders || orders.length === 0) {
                return false;
            }

            // Check if any order has been submitted to server (has tracking_number or pos_reference)
            const hasSubmittedOrder = orders.some(order =>
                order.id && (order.tracking_number || order.pos_reference)
            );

            return hasSubmittedOrder;
        } catch (e) {
            console.error("showContinueOrderingBtn error:", e);
            return false;
        }
    },
});
