# Reservation Module - User Guide

## What This Module Does

The **Reservation Module** is a custom Odoo 18 module that adds a complete appointment booking and reservation system to your Odoo instance. It allows businesses to:

- Create different types of appointments (meetings, consultations, table reservations, resource bookings)
- Let customers self-book through a public website
- Manage resources (rooms, tables, courts) and staff availability
- Collect custom questions during booking
- Accept online payments for paid appointments
- Send automatic email confirmations, cancellations, and reminders
- View all bookings in calendar, list, and kanban views

The module works both as a **backend management tool** (for staff/managers in the Odoo interface) and as a **public-facing website** (for customers to browse and book appointments).

---

## Table of Contents

1. [Installation](#1-installation)
2. [Initial Configuration](#2-initial-configuration)
3. [Creating Appointment Types](#3-creating-appointment-types)
4. [Managing Resources](#4-managing-resources)
5. [Setting Up Availability](#5-setting-up-availability)
6. [Adding Custom Questions](#6-adding-custom-questions)
7. [Payment Setup](#7-payment-setup)
8. [Publishing to Website](#8-publishing-to-website)
9. [The Customer Booking Flow](#9-the-customer-booking-flow)
10. [Managing Bookings](#10-managing-bookings)
11. [Calendar Views](#11-calendar-views)
12. [Security & User Roles](#12-security--user-roles)
13. [Email Notifications](#13-email-notifications)
14. [Demo Data](#14-demo-data)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Installation

### Prerequisites

- Odoo 18 Community or Enterprise edition
- Python 3.10+
- The following Odoo modules must be installed:
  - `base`
  - `mail`
  - `calendar`
  - `resource`
  - `website`
  - `payment` (only if you need online payments)

### Step-by-Step Installation

1. **Copy the module folder** into your Odoo addons directory:
   ```
   Copy the `reservation_module/` folder into your Odoo addons path
   (e.g., /opt/odoo/addons/ or your custom addons directory)
   ```

2. **Update the addons path** in your Odoo configuration file (`odoo.conf`) if needed:
   ```
   addons_path = /opt/odoo/addons,/path/to/your/custom/addons
   ```

3. **Restart the Odoo server**:
   ```
   sudo systemctl restart odoo
   ```

4. **Activate Developer Mode** in Odoo:
   - Go to **Settings**
   - Scroll down and click **Activate the developer mode**

5. **Update the Apps List**:
   - Go to **Apps** menu
   - Click **Update Apps List** (in the top menu or search bar area)
   - Confirm the update

6. **Install the module**:
   - In the **Apps** menu, search for `reservation` or `appointment`
   - Find **"Reservation Module"** (technical name: `reservation_module`)
   - Click **Install**

7. After installation, you will see a new menu item called **"Appointment Management"** (預約管理) in the top navigation bar.

---

## 2. Initial Configuration

After installation, the module is ready to use. Here is what to configure first:

### Check Your User Timezone

1. Go to **Settings > Users & Companies > Users**
2. Select your user (e.g., Administrator)
3. Click the **Preferences** tab
4. Verify the **Timezone** is correct (e.g., Asia/Taipei)
5. This affects how time slots are displayed to customers

> **Note:** In Odoo 18, timezone is a per-user setting found in User Preferences, not in General Settings or Company settings.

### Understand User Roles

The module creates two security groups:

| Role | Who Should Have It | What They Can Do |
|------|-------------------|------------------|
| **Appointment User** | All internal staff | View appointment types, view/create bookings assigned to them |
| **Appointment Manager** | Admins, booking managers | Full control: create/edit/delete all types, bookings, and settings |

To assign roles:
1. Go to **Settings > Users & Companies > Users**
2. Select a user
3. Under the **Other** section or custom groups, assign **Appointment User** or **Appointment Manager**

---

## 3. Creating Appointment Types

Appointment types are the core of the module. Each type defines a specific kind of booking customers can make.

### Navigate to Appointment Types

1. Click **Appointment Management** in the top menu
2. Click **Appointment Types** (預約類型)

### Create a New Appointment Type

1. Click **New**
2. Fill in the basic information:

#### Basic Information Tab

| Field | Description | Example |
|-------|-------------|---------|
| **Name** | The display name customers will see | "1-Hour Consultation" |
| **Category** | The type of appointment | Options: Meeting, Video Call, Table Reservation, Resource Booking, Paid Consultation, Paid Seat |
| **Active** | Whether this type is available | Check to enable |
| **Published** | Whether it shows on the website | Check to show publicly |
| **Slot Duration** | Length of each appointment in hours | 1.0 = 1 hour, 0.5 = 30 minutes |
| **Timezone** | Timezone for scheduling | e.g., Asia/Taipei |

#### Booking Type & Assignment

| Field | Description |
|-------|-------------|
| **Booking Type** | **User** = staff-based (customers book with a person), **Resource** = resource-based (customers book a room/table/court) |
| **Assignment Method** | **Automatic** = system picks the best available staff/resource, **Customer Choice** = customer selects which staff/resource |

#### Location Tab

| Field | Description |
|-------|-------------|
| **Location Type** | **Online** or **Physical** |
| **Video Link** | URL for video meetings (if online) |
| **Location** | Select a contact/partner as the physical address |

#### Scheduling Options (in Options Tab)

| Field | Description | Default |
|-------|-------------|---------|
| **Max Booking Days** | How many days in advance customers can book | 30 |
| **Min Booking Hours** | Minimum advance notice (in hours) | 1.0 |
| **Cancel Before Hours** | Deadline before appointment to allow cancellation | 1.0 |
| **Auto Confirm** | Automatically confirm bookings (vs. manual approval) | Yes |
| **Slot Interval** | Time gap between available start times | 1.0 hour |

#### Capacity Settings (in Options Tab)

| Field | Description |
|-------|-------------|
| **Manage Capacity** | Enable if one slot can serve multiple guests (e.g., a table) |
| **Max Concurrent Bookings** | How many bookings can overlap in one time slot |

### Preset Categories Explained

| Category | Best For | Example |
|----------|----------|---------|
| **Meeting** | In-person meetings with staff | Business consultation |
| **Video Call** | Remote meetings | Online therapy session |
| **Table Reservation** | Restaurant/cafe bookings | Dinner reservation |
| **Resource Booking** | Facility/equipment rental | Tennis court, meeting room |
| **Paid Consultation** | Paid professional services | Legal consultation |
| **Paid Seat** | Event seating with payment | Workshop seat |

---

## 4. Managing Resources

Resources represent physical things that can be booked: rooms, tables, courts, equipment, etc.

### Add Resources

1. When editing an Appointment Type, go to the **Availability** tab
2. In the **Resources** section, click **Add a line**
3. Select existing resources or create new ones

### Create a New Resource

When adding a resource, click **Create and edit** to set up a new resource:

| Field | Description | Example |
|-------|-------------|---------|
| **Name** | Resource name | "Meeting Room A" |
| **Capacity** | How many people it holds | 10 |
| **Icon** | Font Awesome icon class | "fa-building" |
| **Image** | Photo of the resource | Upload a photo |

### Assign Staff Users

For staff-based appointment types:
1. In the **Availability** tab, find the **Staff** section
2. Click **Add a line** to assign users who can handle this appointment type

---

## 5. Setting Up Availability

Availability defines when appointments can be booked.

### Weekly Recurring Schedule

1. Open an Appointment Type
2. Go to the **Availability** tab
3. Set **Schedule Type** to **Recurring**
4. In the availability grid, add rows for each working period:

| Field | Description |
|-------|-------------|
| **Day of Week** | Monday through Sunday |
| **From** | Start time (e.g., 9.0 = 9:00 AM) |
| **To** | End time (e.g., 17.0 = 5:00 PM) |
| **Resource** | (Optional) Specific resource this applies to |
| **Staff** | (Optional) Specific staff member this applies to |

**Example: A restaurant open for dinner on weekdays and all day on weekends:**

| Day | From | To |
|-----|------|----|
| Monday | 18.0 | 22.0 |
| Tuesday | 18.0 | 22.0 |
| Wednesday | 18.0 | 22.0 |
| Thursday | 18.0 | 22.0 |
| Friday | 18.0 | 22.0 |
| Saturday | 12.0 | 23.0 |
| Sunday | 12.0 | 21.0 |

### Tips

- Time uses 24-hour decimal format: 9:30 AM = 9.5, 2:00 PM = 14.0
- You can add multiple rows for the same day (e.g., morning and afternoon sessions with a lunch break)
- If you assign a resource or staff member to a row, that availability only applies to them
- Leave resource/staff blank for the availability to apply to all

---

## 6. Adding Custom Questions

You can collect additional information from customers during booking.

### Add Questions

1. Open an Appointment Type
2. Go to the **Questions** tab
3. Click **Add a line**

### Question Fields

| Field | Description |
|-------|-------------|
| **Question Text** | The question displayed to the customer |
| **Type** | text, textarea, select, radio, checkbox, date, datetime, number, email, phone |
| **Required** | Whether the customer must answer |
| **Placeholder** | Hint text inside the input field |
| **Help Text** | Additional explanation shown below the question |

### Question Types Explained

| Type | Use For | Example |
|------|---------|---------|
| **text** | Short text answer | "Your company name" |
| **textarea** | Long text answer | "Describe your project needs" |
| **select** | Dropdown with one choice | "Experience level" (Beginner/Intermediate/Advanced) |
| **radio** | Radio buttons, one choice | "Preferred meeting type" |
| **checkbox** | Multiple selections allowed | "Dietary requirements" (Vegetarian, Vegan, Gluten-free) |
| **date** | Date picker | "Preferred alternative date" |
| **number** | Numeric input | "Number of additional guests" |
| **email** | Email input with validation | "Additional contact email" |
| **phone** | Phone number input | "Emergency contact number" |

### Adding Options (for select, radio, checkbox types)

1. After creating a select/radio/checkbox question, click on the question line
2. In the **Options** section, click **Add a line**
3. Enter each option name (e.g., "Vegetarian", "Vegan", "Gluten-free")

---

## 7. Payment Setup

For paid appointment types (consultations, reserved seats), you can require online payment.

### Prerequisites

1. Install and configure the **Payment** module in Odoo
2. Set up at least one payment provider (e.g., Stripe, PayPal)
   - Go to **Invoicing/Accounting > Configuration > Payment Providers**
   - Enable and configure your preferred provider

### Enable Payment for an Appointment Type

1. Open the Appointment Type
2. Go to the **Options** tab
3. Find the **Payment** section:

| Field | Description |
|-------|-------------|
| **Require Payment** | Check to require payment before confirmation |
| **Payment Amount** | The price to charge |
| **Payment Per Person** | If checked, the amount is multiplied by guest count |
| **Payment Product** | Link to a product record (for invoicing/accounting) |
| **Currency** | Currency for the payment |

### How Payment Works

1. Customer completes the booking form
2. They are redirected to a payment page
3. They select a payment method and pay
4. On successful payment:
   - The booking is automatically confirmed
   - Payment status changes to "Paid"
   - A confirmation email is sent
5. If payment fails, the booking stays in "Draft" with payment status "Pending"

---

## 8. Publishing to Website

### Make an Appointment Type Visible

1. Open the Appointment Type
2. Ensure **Published** (is_published) is checked
3. The appointment will appear on your website at: `https://your-domain.com/appointment`

### Website URLs

| URL | What It Shows |
|-----|---------------|
| `/appointment` | List of all published appointment types |
| `/appointment/<id>` | Details page for a specific appointment type |
| `/appointment/<id>/schedule` | Calendar and slot selection page |
| `/appointment/<id>/book` | Booking form |

### Sharing Links

1. Open an Appointment Type
2. Click the **Share** button in the form header
3. Copy the generated URL to share with customers

---

## 9. The Customer Booking Flow

Here is what your customers experience step by step:

### Step 1: Browse Available Appointments

- Customer visits `/appointment` on your website
- They see a grid of cards, each showing an appointment type with its name, duration, and icon/image

### Step 2: Select an Appointment Type

- Customer clicks on an appointment type card
- They see the description, location info, and a "Book Now" button

### Step 3: Choose Date and Time

- Customer sees a **calendar** showing the current month
- Available dates are highlighted; unavailable dates are grayed out
- They click a date to see available time slots
- If the appointment type uses **Customer Choice** assignment:
  - They can select which resource or staff member they want
- They click on an available time slot

### Step 4: Fill in Booking Details

- Customer enters their information:
  - **Name** (required)
  - **Email** (required)
  - **Phone** (optional)
  - **Number of Guests** (if capacity is managed)
  - **Notes** (optional)
- They answer any custom questions set up for this appointment type
- They click **Confirm Booking**

### Step 5: Payment (if required)

- If the appointment type requires payment, the customer is redirected to a payment page
- They select a payment method and complete the transaction

### Step 6: Confirmation

- Customer sees a confirmation page with:
  - Booking reference number (e.g., APT00001)
  - Date, time, and duration
  - Location or video link
  - A link to view or manage their booking
- A confirmation email is also sent to the customer's email address

### Step 7: Managing Their Booking

- Customer can access their booking via the link in the confirmation email
- From there they can:
  - View booking details
  - Cancel the booking (if within the cancellation deadline)

---

## 10. Managing Bookings

### View All Bookings

1. Go to **Appointment Management > All Bookings** (所有預約)
2. You will see bookings in a list view with key information

### Booking Status Flow

```
Draft → Confirmed → Done
  ↓         ↓
  └→ Cancelled ←┘
```

| Status | Meaning |
|--------|---------|
| **Draft** | Newly created, not yet confirmed |
| **Confirmed** | Approved and scheduled |
| **Done** | Appointment completed |
| **Cancelled** | Booking was cancelled |

### Actions on a Booking

Open any booking to see its details and perform actions:

| Button | What It Does | When Available |
|--------|-------------|----------------|
| **Confirm** | Confirms the booking and creates a calendar event | When in Draft status |
| **Mark Done** | Marks the appointment as completed | When in Confirmed status |
| **Cancel** | Cancels the booking | When in Draft or Confirmed status |
| **Reset to Draft** | Returns a cancelled booking to draft | When in Cancelled status |

### Booking Details

Each booking record contains:

- **Booking Reference**: Auto-generated (APT00001, APT00002, etc.)
- **Appointment Type**: Which type of appointment
- **Date & Time**: Start and end datetime
- **Duration**: Calculated automatically
- **Guest Info**: Name, email, phone, guest count
- **Resource/Staff**: Assigned resource or staff member
- **Payment Status**: Not Required / Pending / Paid / Refunded
- **Answers Tab**: Customer responses to custom questions
- **Notes Tab**: Customer notes and internal staff notes
- **Chatter**: Full message history and activity tracking

### Filter and Search Bookings

Use the search bar and filters to find bookings:

- **Quick Filters**: Today, This Week, Upcoming
- **Status Filters**: Draft, Confirmed, Done, Cancelled
- **Group By**: Appointment Type, Status, Date, Resource, Staff

---

## 11. Calendar Views

The module provides several calendar views for visual scheduling:

### All Bookings Calendar

1. Go to **Appointment Management > All Bookings**
2. Switch to **Calendar View** (click the calendar icon in the top-right view switcher)
3. Bookings are color-coded by appointment type

### Resource Calendar

1. Go to **Appointment Management > Resource Bookings** (資源預約)
2. View bookings organized by resource
3. Color-coded by resource for easy identification

### Staff Calendar

1. Go to **Appointment Management > Staff Bookings** (員工預約)
2. View bookings organized by staff member
3. Color-coded by staff for easy identification

### Calendar Features

- **Day/Week/Month views**: Toggle between views using the buttons at the top
- **Click to create**: Click on an empty time slot to create a new booking
- **Drag to reschedule**: Drag a booking to a different time (requires edit permission)
- **Click to view**: Click any booking to see its details

---

## 12. Security & User Roles

### Role Permissions Summary

| Action | Public (Website) | Appointment User | Appointment Manager |
|--------|-------------------|------------------|---------------------|
| View published appointment types | Yes | Yes | Yes |
| View all appointment types | No | Yes | Yes |
| Create/edit/delete appointment types | No | No | Yes |
| View own bookings | Via access token | Yes | Yes |
| View all bookings | No | Only their own or assigned | Yes |
| Create bookings | Yes (via website) | Yes | Yes |
| Confirm/cancel bookings | No | Own bookings | All bookings |
| Delete bookings | No | No | Yes |
| Access Reports & Settings menus | No | No | Yes |

### Access Token

- When a customer books via the website, they receive an **access token** in their confirmation link
- This token allows them to view and manage their specific booking without logging in
- Tokens are unique and secure

---

## 13. Email Notifications

The module sends automatic emails at key points:

| Event | Email Sent | Recipient |
|-------|-----------|-----------|
| Booking Confirmed | Confirmation email with details | Customer (guest_email) |
| Booking Cancelled | Cancellation notice | Customer (guest_email) |
| Booking Reminder | Reminder before appointment | Customer (guest_email) |

### Email Content

Confirmation emails include:
- Booking reference number
- Appointment type name
- Date and time
- Location or video link
- A link to view/manage the booking

### Customizing Emails

Managers can customize email templates:
1. Go to **Settings > Technical > Email > Templates**
2. Search for "appointment" or "booking"
3. Edit the templates:
   - `Booking Confirmed` (email_template_booking_confirmed)
   - `Booking Cancelled` (email_template_booking_cancelled)
   - `Booking Reminder` (email_template_booking_reminder)

---

## 14. Demo Data

When you install the module, demo data is automatically loaded (if demo data is enabled in your Odoo instance). This includes:

### Demo Resources

| Resource | Capacity | Type |
|----------|----------|------|
| Meeting Room A | 10 | Room |
| Meeting Room B | 6 | Room |
| Table 1 - Waterfront | 4 | Table |
| Table 2 - Garden View | 6 | Table |
| Table 3 - Private Room | 8 | Table |
| Tennis Court | 4 | Court |

### Demo Appointment Types

| Name | Category | Duration | Payment |
|------|----------|----------|---------|
| Business Meeting | Meeting | 1 hour | Free |
| Video Consultation | Video Call | 30 min | Free |
| Table Booking | Table Reservation | 2 hours | Free |
| Tennis Court | Resource Booking | 1 hour | Free |
| Expert Consultation | Paid Consultation | 1 hour | $100 |

These demo records help you understand how the module works. You can modify or delete them as needed.

---

## 15. Troubleshooting

### Common Issues

**Q: I installed the module but don't see the menu.**
- Make sure you are logged in as a user with the **Appointment User** or **Appointment Manager** role
- Try clearing your browser cache and refreshing the page

**Q: Customers can't see any appointment types on the website.**
- Check that the appointment type has **Published** checked
- Verify that the **Website** module is installed
- Make sure availability is configured (no availability = no slots = nothing to book)

**Q: No time slots are showing up for customers.**
- Verify that **Availability** rows are set up in the appointment type
- Check that the booking date is within the **Max Booking Days** range
- Ensure the booking time respects the **Min Booking Hours** advance notice
- If using resources/staff, make sure they are assigned to the appointment type

**Q: Payments are not working.**
- Ensure the **Payment** module is installed
- Configure at least one payment provider (Settings > Payment Providers)
- Enable the payment provider and set it to "Production" or "Test" mode
- Check that the appointment type has **Require Payment** enabled and an **Amount** set

**Q: Emails are not being sent.**
- Check your Odoo outgoing mail server configuration (Settings > Technical > Outgoing Mail Servers)
- Verify that the email templates exist and are active
- Check the mail queue (Settings > Technical > Emails > Emails) for errors

**Q: Calendar events are not created when confirming bookings.**
- Ensure the **Calendar** module is installed
- The calendar event is created automatically when a booking is confirmed

**Q: I need to change the language.**
- The module supports English, Traditional Chinese (zh_TW), and Simplified Chinese (zh_CN)
- Go to **Settings > Translations > Load a Translation** and select your language
- The module will automatically use the user's language preference

---

## Quick Reference

### Key URLs

| URL | Description |
|-----|-------------|
| `/appointment` | Public appointment listing page |
| `/appointment/<id>` | Specific appointment type page |
| `/appointment/<id>/schedule` | Slot selection calendar |
| `/appointment/<id>/book` | Booking form |

### Booking Reference Format

All bookings get an auto-generated reference: **APT00001**, **APT00002**, etc.

### Time Format

- Internal times use 24-hour decimal: `9.5` = 9:30 AM, `14.0` = 2:00 PM, `17.5` = 5:30 PM
- Website displays times in the appointment type's configured timezone

### Module Technical Details

| Property | Value |
|----------|-------|
| Technical Name | `reservation_module` |
| Version | Odoo 18 |
| Dependencies | base, mail, calendar, resource, website, payment |
| License | LGPL-3 |
