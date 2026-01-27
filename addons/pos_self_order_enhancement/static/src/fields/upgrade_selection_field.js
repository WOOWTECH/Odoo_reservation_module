/** @odoo-module */

import { registry } from "@web/core/registry";
import { selectionField, SelectionField } from "@web/views/fields/selection/selection_field";

/**
 * Override UpgradeSelectionField to remove Enterprise version check.
 * This allows Community version to use "Pay per Order" (整單結) feature
 * without showing the upgrade dialog.
 */
export class UpgradeSelectionFieldCommunity extends SelectionField {
    setup() {
        super.setup();
    }

    async onChange(newValue) {
        // Bypass Enterprise check - directly call parent onChange
        super.onChange(...arguments);
    }
}

export const upgradeSelectionFieldCommunity = {
    ...selectionField,
    component: UpgradeSelectionFieldCommunity,
    additionalClasses: [...(selectionField.additionalClasses || []), "o_field_selection"],
};

// Override the upgrade_selection widget
registry.category("fields").add("upgrade_selection", upgradeSelectionFieldCommunity, { force: true });
