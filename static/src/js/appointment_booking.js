/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { _t } from "@web/core/l10n/translation";

/**
 * Appointment Reservation Widget
 * Handles the appointment booking reservation on the frontend
 */
publicWidget.registry.AppointmentReservation = publicWidget.Widget.extend({
    selector: '#appointment-reservation',

    start: function () {
        this._super.apply(this, arguments);
        this.appointmentTypeId = this.el.dataset.appointmentTypeId;
        this.resourceId = this.el.dataset.resourceId || null;
        this.staffId = this.el.dataset.staffId || null;
        this.startDate = new Date(this.el.dataset.startDate);
        this.endDate = new Date(this.el.dataset.endDate);
        this.currentDate = new Date(this.startDate);
        this.selectedDate = null;

        this._renderReservation();
    },

    _renderReservation: function () {
        const reservationHTML = this._generateReservationHTML(this.currentDate);
        this.el.innerHTML = reservationHTML;

        // Add event listeners to navigation
        const prevBtn = this.el.querySelector('.reservation-prev');
        const nextBtn = this.el.querySelector('.reservation-next');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                this.currentDate.setMonth(this.currentDate.getMonth() - 1);
                this._renderReservation();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                this.currentDate.setMonth(this.currentDate.getMonth() + 1);
                this._renderReservation();
            });
        }

        // Add event listeners to dates
        const dateCells = this.el.querySelectorAll('.reservation-day:not(.disabled)');
        dateCells.forEach((cell) => {
            cell.addEventListener('click', () => {
                const date = cell.dataset.date;
                this._selectDate(date);
            });
        });
    },

    _generateReservationHTML: function (date) {
        const year = date.getFullYear();
        const month = date.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const monthNames = [_t('January'), _t('February'), _t('March'), _t('April'), _t('May'), _t('June'),
                           _t('July'), _t('August'), _t('September'), _t('October'), _t('November'), _t('December')];
        const dayNames = [_t('Sun'), _t('Mon'), _t('Tue'), _t('Wed'), _t('Thu'), _t('Fri'), _t('Sat')];

        let html = `
            <div class="reservation-header d-flex justify-content-between align-items-center mb-3">
                <button type="button" class="btn btn-outline-secondary reservation-prev">
                    <i class="fa fa-chevron-left"></i>
                </button>
                <h5 class="mb-0">${monthNames[month]} ${year}</h5>
                <button type="button" class="btn btn-outline-secondary reservation-next">
                    <i class="fa fa-chevron-right"></i>
                </button>
            </div>
            <div class="reservation-grid">
                <div class="row text-center mb-2">
        `;

        // Day headers
        dayNames.forEach((day) => {
            html += `<div class="col"><strong>${day}</strong></div>`;
        });
        html += '</div><div class="row">';

        // Empty cells for days before the first day of the month
        for (let i = 0; i < firstDay.getDay(); i++) {
            html += '<div class="col p-2"></div>';
        }

        // Date cells
        for (let day = 1; day <= lastDay.getDate(); day++) {
            const cellDate = new Date(year, month, day);
            const dateStr = this._formatDate(cellDate);
            const isPast = cellDate < today;
            const isBeyondRange = cellDate > this.endDate;
            const isDisabled = isPast || isBeyondRange;
            const isSelected = this.selectedDate === dateStr;

            let cellClass = 'reservation-day';
            if (isDisabled) cellClass += ' disabled';
            if (isSelected) cellClass += ' selected';

            html += `
                <div class="col p-1">
                    <div class="${cellClass}" data-date="${dateStr}">
                        ${day}
                    </div>
                </div>
            `;

            // New row after Saturday
            if ((firstDay.getDay() + day) % 7 === 0 && day < lastDay.getDate()) {
                html += '</div><div class="row">';
            }
        }

        // Fill remaining cells
        const remainingCells = 7 - ((firstDay.getDay() + lastDay.getDate()) % 7);
        if (remainingCells < 7) {
            for (let i = 0; i < remainingCells; i++) {
                html += '<div class="col p-2"></div>';
            }
        }

        html += '</div></div>';
        return html;
    },

    _selectDate: function (dateStr) {
        this.selectedDate = dateStr;
        this._renderReservation();
        this._loadSlots(dateStr);
    },

    _loadSlots: function (dateStr) {
        const slotsContainer = document.getElementById('slots-container');
        const availableSlots = document.getElementById('available-slots');

        if (!slotsContainer || !availableSlots) return;

        // Show loading
        slotsContainer.innerHTML = `
            <div class="col-12 text-center py-4">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
                <p class="mt-2">${_t("Loading available times...")}</p>
            </div>
        `;
        availableSlots.style.display = 'block';

        // Fetch slots from server
        fetch(`/appointment/${this.appointmentTypeId}/slots`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    date: dateStr,
                    resource_id: this.resourceId,
                    staff_id: this.staffId,
                },
            }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.result && data.result.slots) {
                this._renderSlots(data.result.slots);
            } else if (data.result && data.result.error) {
                slotsContainer.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-danger">${data.result.error}</div>
                    </div>
                `;
            } else {
                this._renderSlots([]);
            }
        })
        .catch(error => {
            console.error('Error loading slots:', error);
            slotsContainer.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-danger">${_t("Error loading available times. Please try again.")}</div>
                </div>
            `;
        });
    },

    _renderSlots: function (slots) {
        const slotsContainer = document.getElementById('slots-container');
        if (!slotsContainer) return;

        if (slots.length === 0) {
            slotsContainer.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-info">${_t("No available times for this date.")}</div>
                </div>
            `;
            return;
        }

        let html = '';
        slots.forEach((slot) => {
            const bookUrl = `/appointment/${this.appointmentTypeId}/book?start_datetime=${encodeURIComponent(slot.start)}`;
            const resourceParam = this.resourceId ? `&resource_id=${this.resourceId}` : '';
            const staffParam = this.staffId ? `&staff_id=${this.staffId}` : '';

            html += `
                <div class="col-auto mb-2">
                    <a href="${bookUrl}${resourceParam}${staffParam}" class="time-slot text-decoration-none">
                        <div class="slot-time">${slot.start_time} - ${slot.end_time}</div>
                        <div class="slot-availability">${slot.available} ${_t("available")}</div>
                    </a>
                </div>
            `;
        });

        slotsContainer.innerHTML = html;
    },

    _formatDate: function (date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },
});

/**
 * Form Validation Widget
 */
publicWidget.registry.AppointmentFormValidation = publicWidget.Widget.extend({
    selector: '.needs-validation',
    events: {
        'submit': '_onSubmit',
    },

    _onSubmit: function (ev) {
        if (!this.el.checkValidity()) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.el.classList.add('was-validated');
    },
});

export default publicWidget.registry;
