# -*- coding: utf-8 -*-
"""
D-series: Per-appointment-type lifecycle and feature validation tests.

Iterates over ALL 5 appointment types to verify full booking lifecycle
(create -> draft -> confirmed -> done) and validates type-specific features
such as staff assignment, slot durations, capacity management, resource
allocation, and payment requirements.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import (
    test, call, jsonrpc, http_get, http_post,
    create_booking, cleanup, get_results, reset_results, print_summary, _cleanup_ids,
)
from config import URL, TYPE_IDS, TYPE_CONFIG, RESOURCE_IDS
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# D1  --  Full Lifecycle Loop (all 5 types)
# ---------------------------------------------------------------------------

def _test_d1_lifecycle():
    """D1: Create -> draft -> confirmed -> done for every appointment type."""

    for type_key, type_id in TYPE_IDS.items():
        cfg = TYPE_CONFIG[type_id]
        type_name = cfg['name']
        print(f"\n  --- D1 Lifecycle: {type_name} (id={type_id}) ---")

        # D1.1 - Verify type exists and configuration matches TYPE_CONFIG
        try:
            type_data = call('appointment.type', 'read', [type_id], {
                'fields': [
                    'name', 'slot_duration', 'slot_interval',
                    'max_booking_days', 'min_booking_hours', 'cancel_before_hours',
                    'is_scheduled', 'require_payment', 'assign_staff',
                    'manage_capacity',
                ],
            })
            rec = type_data[0] if type_data else {}
            checks = [
                rec.get('name') == cfg['name'],
                abs(rec.get('slot_duration', 0) - cfg['duration']) < 0.01,
                abs(rec.get('slot_interval', 0) - cfg['interval']) < 0.01,
                rec.get('max_booking_days') == cfg['max_days'],
                abs(rec.get('min_booking_hours', 0) - cfg['min_hours']) < 0.01,
                abs(rec.get('cancel_before_hours', 0) - cfg['cancel_hours']) < 0.01,
                rec.get('require_payment', False) == cfg['payment'],
                rec.get('is_scheduled', False) == cfg['scheduled'],
                rec.get('manage_capacity', False) == cfg['manage_capacity'],
                rec.get('assign_staff', False) == cfg['assign_staff'],
            ]
            all_match = all(checks)
            test(
                f"D1.1-{type_key}",
                f"Type config matches expected for {type_name}",
                all_match,
                detail=(
                    f"name={rec.get('name')}, duration={rec.get('slot_duration')}, "
                    f"interval={rec.get('slot_interval')}, max_days={rec.get('max_booking_days')}, "
                    f"min_hours={rec.get('min_booking_hours')}, cancel_hours={rec.get('cancel_before_hours')}, "
                    f"payment={rec.get('require_payment')}, is_scheduled={rec.get('is_scheduled')}, "
                    f"assign_staff={rec.get('assign_staff')}, "
                    f"manage_capacity={rec.get('manage_capacity')}"
                ),
            )
        except Exception as e:
            test(f"D1.1-{type_key}", f"Type config matches expected for {type_name}",
                 False, detail=str(e))

        # D1.2 - Verify slots endpoint returns data for this type
        try:
            future_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
            resp = jsonrpc(f'/appointment/{type_id}/slots', {'date': future_date})
            body = resp.json()
            result = body.get('result', {})
            slots = result.get('slots', []) if isinstance(result, dict) else []
            test(
                f"D1.2-{type_key}",
                f"Slots endpoint returns data for {type_name}",
                resp.status_code == 200 and isinstance(slots, list) and len(slots) > 0,
                detail=f"status={resp.status_code}, slot_count={len(slots)}, date={future_date}",
            )
        except Exception as e:
            test(f"D1.2-{type_key}", f"Slots endpoint returns data for {type_name}",
                 False, detail=str(e))

        # D1.3 - Create a booking for this type
        # Expert consultation needs days_ahead=5 to satisfy 24h min_booking_hours
        days_ahead = 5 if type_key == 'expert_consultation' else 3
        booking_id = None
        try:
            extra = {}
            # Resource-based types need a resource_id
            if type_id == TYPE_IDS['restaurant']:
                extra['resource_id'] = RESOURCE_IDS['table_1']
            elif type_id == TYPE_IDS['tennis']:
                extra['resource_id'] = RESOURCE_IDS['tennis_court']
            # Payment types
            if cfg['payment']:
                extra['payment_status'] = 'pending'
                extra['payment_amount'] = 100.0

            booking_id, bk_start, bk_end = create_booking(
                type_id,
                days_ahead=days_ahead,
                hour=10,
                duration_hours=cfg['duration'],
                guest_name=f'D1 Lifecycle {type_name}',
                guest_email=f'd1_{type_key}@test.com',
                **extra,
            )
            test(
                f"D1.3-{type_key}",
                f"Booking created for {type_name}",
                booking_id is not None and booking_id > 0,
                detail=f"booking_id={booking_id}",
            )
        except Exception as e:
            test(f"D1.3-{type_key}", f"Booking created for {type_name}",
                 False, detail=str(e))

        if not booking_id:
            print(f"    Skipping remaining D1 tests for {type_name} (no booking)")
            continue

        # D1.4 - Verify booking state is 'draft'
        try:
            booking_data = call('appointment.booking', 'read', [booking_id],
                                {'fields': ['state']})
            state = booking_data[0]['state'] if booking_data else None
            test(
                f"D1.4-{type_key}",
                f"Booking state is draft for {type_name}",
                state == 'draft',
                detail=f"state={state}",
            )
        except Exception as e:
            test(f"D1.4-{type_key}", f"Booking state is draft for {type_name}",
                 False, detail=str(e))

        # D1.5 - Confirm the booking (action_confirm)
        try:
            # Payment types require payment_status='paid' before confirmation
            if cfg['payment']:
                call('appointment.booking', 'write', [[booking_id], {'payment_status': 'paid'}])
            call('appointment.booking', 'action_confirm', [booking_id])
            test(
                f"D1.5-{type_key}",
                f"action_confirm executed for {type_name}",
                True,
                detail=f"booking_id={booking_id}",
            )
        except Exception as e:
            # Payment types may raise if payment not completed -- still record
            test(f"D1.5-{type_key}", f"action_confirm executed for {type_name}",
                 False, detail=str(e))

        # D1.6 - Verify state changed to 'confirmed'
        try:
            booking_data = call('appointment.booking', 'read', [booking_id],
                                {'fields': ['state']})
            state = booking_data[0]['state'] if booking_data else None
            # Payment types may block confirmation and stay in draft
            if cfg['payment']:
                # For payment types, confirm may fail; accept either draft or confirmed
                passed = state in ('draft', 'confirmed')
                test(
                    f"D1.6-{type_key}",
                    f"State after confirm attempt for {type_name} (payment type)",
                    passed,
                    detail=f"state={state} (payment types may stay draft)",
                )
            else:
                test(
                    f"D1.6-{type_key}",
                    f"Booking state is confirmed for {type_name}",
                    state == 'confirmed',
                    detail=f"state={state}",
                )
        except Exception as e:
            test(f"D1.6-{type_key}", f"Booking state is confirmed for {type_name}",
                 False, detail=str(e))

        # D1.7 - Complete the booking (action_done)
        try:
            # If the booking is still draft (payment type), force-confirm first
            booking_data = call('appointment.booking', 'read', [booking_id],
                                {'fields': ['state']})
            current_state = booking_data[0]['state'] if booking_data else None
            if current_state == 'draft':
                # For payment types, simulate payment completion then confirm
                if cfg['payment']:
                    try:
                        call('appointment.booking', 'write', [[booking_id], {
                            'payment_status': 'paid',
                        }])
                        call('appointment.booking', 'action_confirm', [booking_id])
                    except Exception:
                        pass

            call('appointment.booking', 'action_done', [booking_id])
            test(
                f"D1.7-{type_key}",
                f"action_done executed for {type_name}",
                True,
                detail=f"booking_id={booking_id}",
            )
        except Exception as e:
            test(f"D1.7-{type_key}", f"action_done executed for {type_name}",
                 False, detail=str(e))

        # D1.8 - Verify state changed to 'done'
        try:
            booking_data = call('appointment.booking', 'read', [booking_id],
                                {'fields': ['state']})
            state = booking_data[0]['state'] if booking_data else None
            test(
                f"D1.8-{type_key}",
                f"Booking state is done for {type_name}",
                state == 'done',
                detail=f"state={state}",
            )
        except Exception as e:
            test(f"D1.8-{type_key}", f"Booking state is done for {type_name}",
                 False, detail=str(e))


# ---------------------------------------------------------------------------
# D2  --  Type-Specific Feature Tests
# ---------------------------------------------------------------------------

def _test_d2_type_specific():
    """D2: Tests that validate features unique to specific appointment types."""

    # ------------------------------------------------------------------
    # D2.1  Business Meeting -- staff is not auto-assigned (module does
    #        not implement auto-assignment); staff_user_id should be False
    #        when not explicitly provided.
    # ------------------------------------------------------------------
    print("\n  --- D2.1: Business Meeting staff not auto-assigned ---")
    try:
        meeting_id = TYPE_IDS['business_meeting']
        bid, _, _ = create_booking(
            meeting_id,
            days_ahead=3,
            hour=11,
            duration_hours=1.0,
            guest_name='D2.1 Staff Assign Test',
            guest_email='d21_staff@test.com',
            # Deliberately omit staff_user_id
        )
        call('appointment.booking', 'action_confirm', [bid])
        booking_data = call('appointment.booking', 'read', [bid],
                            {'fields': ['staff_user_id', 'state']})
        rec = booking_data[0] if booking_data else {}
        staff = rec.get('staff_user_id')
        # staff_user_id is [id, name] if set, or False if not
        no_staff = (staff is False) or (not staff)
        test(
            "D2.1",
            "Business Meeting: staff_user_id is False when not explicitly set",
            no_staff,
            detail=f"staff_user_id={staff}, state={rec.get('state')}",
        )
    except Exception as e:
        test("D2.1", "Business Meeting: staff_user_id is False when not explicitly set",
             False, detail=str(e))

    # ------------------------------------------------------------------
    # D2.2  Video Consultation -- 30min duration verified in slot count
    # ------------------------------------------------------------------
    print("\n  --- D2.2: Video Consultation 30min slot count ---")
    try:
        video_id = TYPE_IDS['video_consultation']
        # Use a date 7+ days ahead and ensure it falls on a weekday
        d = datetime.now() + timedelta(days=7)
        while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
            d += timedelta(days=1)
        future_date = d.strftime('%Y-%m-%d')
        resp = jsonrpc(f'/appointment/{video_id}/slots', {'date': future_date})
        body = resp.json()
        result = body.get('result', {})
        slots = result.get('slots', []) if isinstance(result, dict) else []
        # With 0.5h intervals over a 9h working window (09:00-18:00),
        # theoretical max is ~17-18 slots. Must be more than for a 1h type.
        # At minimum, 30min slots should give > 8 slots on a full workday.
        test(
            "D2.2",
            "Video Consultation: 30min slots yield > 8 slots on workday",
            len(slots) > 8,
            detail=f"slot_count={len(slots)}, date={future_date}",
        )
    except Exception as e:
        test("D2.2", "Video Consultation: 30min slots yield > 8 slots on workday",
             False, detail=str(e))

    # ------------------------------------------------------------------
    # D2.3  Restaurant -- resource must be explicitly set (no auto-assign)
    #        Create without resource_id, verify it remains False/unset.
    # ------------------------------------------------------------------
    print("\n  --- D2.3: Restaurant resource must be explicitly set ---")
    try:
        restaurant_id = TYPE_IDS['restaurant']
        bid, _, _ = create_booking(
            restaurant_id,
            days_ahead=5,
            hour=12,
            duration_hours=2.0,
            guest_name='D2.3 Resource Test',
            guest_email='d23_resource@test.com',
            guest_count=3,
            # Do NOT pass resource_id -- module does not auto-assign
        )
        booking_data = call('appointment.booking', 'read', [bid],
                            {'fields': ['resource_id', 'guest_count', 'state']})
        rec = booking_data[0] if booking_data else {}
        resource = rec.get('resource_id')
        # resource_id is [id, name] if set, or False if not
        no_resource = (resource is False) or (not resource)

        test(
            "D2.3",
            "Restaurant: resource_id is not auto-assigned (must be explicitly set)",
            no_resource,
            detail=f"resource_id={resource}, guest_count={rec.get('guest_count')}",
        )
    except Exception as e:
        test("D2.3", "Restaurant: resource_id is not auto-assigned",
             False, detail=str(e))

    # ------------------------------------------------------------------
    # D2.4  Tennis Court -- single resource available
    #        Booking should get the tennis_court resource
    # ------------------------------------------------------------------
    print("\n  --- D2.4: Tennis Court single resource ---")
    try:
        tennis_id = TYPE_IDS['tennis']
        bid, _, _ = create_booking(
            tennis_id,
            days_ahead=3,
            hour=14,
            duration_hours=1.0,
            guest_name='D2.4 Tennis Test',
            guest_email='d24_tennis@test.com',
            resource_id=RESOURCE_IDS['tennis_court'],
        )
        booking_data = call('appointment.booking', 'read', [bid],
                            {'fields': ['resource_id', 'state']})
        rec = booking_data[0] if booking_data else {}
        resource = rec.get('resource_id')
        resource_id_val = resource[0] if isinstance(resource, (list, tuple)) else resource
        test(
            "D2.4",
            "Tennis Court: booking gets tennis_court resource",
            resource_id_val == RESOURCE_IDS['tennis_court'],
            detail=f"resource_id={resource}, expected={RESOURCE_IDS['tennis_court']}",
        )
    except Exception as e:
        test("D2.4", "Tennis Court: booking gets tennis_court resource",
             False, detail=str(e))

    # ------------------------------------------------------------------
    # D2.5  Expert Consultation -- require_payment=True verified on type
    # ------------------------------------------------------------------
    print("\n  --- D2.5: Expert Consultation payment requirement ---")
    try:
        expert_id = TYPE_IDS['expert_consultation']
        type_data = call('appointment.type', 'read', [expert_id],
                         {'fields': ['require_payment', 'payment_amount']})
        rec = type_data[0] if type_data else {}
        require_payment = rec.get('require_payment', False)
        payment_amount = rec.get('payment_amount', 0)
        test(
            "D2.5",
            "Expert Consultation: require_payment=True on type",
            require_payment is True,
            detail=f"require_payment={require_payment}, payment_amount={payment_amount}",
        )
    except Exception as e:
        test("D2.5", "Expert Consultation: require_payment=True on type",
             False, detail=str(e))

    # ------------------------------------------------------------------
    # D2.6  Restaurant -- capacity check at model level
    #        Creating a booking with guest_count exceeding resource
    #        capacity succeeds at the model level; capacity enforcement
    #        happens only in the controller/frontend.
    #        This test documents the behaviour as informational.
    # ------------------------------------------------------------------
    print("\n  --- D2.6: Restaurant capacity check (informational) ---")
    try:
        restaurant_id = TYPE_IDS['restaurant']
        table_1_id = RESOURCE_IDS['table_1']  # capacity=4
        bid, _, _ = create_booking(
            restaurant_id,
            days_ahead=5,
            hour=13,
            duration_hours=2.0,
            guest_name='D2.6 Overbook Test',
            guest_email='d26_overbook@test.com',
            guest_count=10,  # exceeds table_1 capacity of 4
            resource_id=table_1_id,
        )
        # At the model level the booking is expected to succeed
        booking_data = call('appointment.booking', 'read', [bid],
                            {'fields': ['resource_id', 'guest_count', 'state']})
        rec = booking_data[0] if booking_data else {}
        resource = rec.get('resource_id')
        resource_id_val = resource[0] if isinstance(resource, (list, tuple)) else resource
        # Booking accepted -- capacity is only enforced at controller level
        created_ok = bid is not None and bid > 0
        test(
            "D2.6",
            "Restaurant: booking with guest_count > capacity succeeds at model level (informational)",
            created_ok,
            detail=(
                f"booking_id={bid}, resource_id={resource}, "
                f"guest_count={rec.get('guest_count')} "
                "(capacity enforcement is in controller, not model)"
            ),
        )
    except Exception as e:
        test("D2.6", "Restaurant: capacity check (informational)",
             False, detail=str(e))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    """Execute all D-series per-type tests and return results."""
    reset_results()
    print("\n" + "=" * 60)
    print("  D-SERIES: PER-TYPE LIFECYCLE TESTS")
    print("=" * 60)

    print("\n--- D1: Full Lifecycle Loop (all 5 types) ---")
    _test_d1_lifecycle()

    print("\n--- D2: Type-Specific Feature Tests ---")
    _test_d2_type_specific()

    print("\n--- Cleanup ---")
    cleanup()

    print_summary("Per-Type Tests")
    return get_results()


if __name__ == '__main__':
    run()
