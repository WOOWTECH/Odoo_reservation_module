/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";

export class BookingCalendarController extends CalendarController {
    onClickAddButton() {
        this.editRecord({}, {}, false);
    }
}

BookingCalendarController.template = "reservation_module.BookingCalendarController";

export const bookingCalendarView = {
    ...calendarView,
    Controller: BookingCalendarController,
};

registry.category("views").add("booking_calendar", bookingCalendarView);
