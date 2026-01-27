/** @odoo-module */

import { selfOrderIndex } from "@pos_self_order/app/self_order_index";
import { PaymentPage } from "./pages/payment_page/payment_page";
import { PaymentSuccessPage } from "./pages/payment_success_page/payment_success_page";

/**
 * Override selfOrderIndex components to register custom page components.
 * This makes PaymentPage and PaymentSuccessPage available in the router.
 *
 * Note: We override the existing PaymentPage with our custom implementation
 * that supports both online payment and counter payment for mobile mode.
 */

// Directly override the static components property
selfOrderIndex.components = {
    ...selfOrderIndex.components,
    PaymentPage,
    PaymentSuccessPage,
};
