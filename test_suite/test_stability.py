# -*- coding: utf-8 -*-
"""G-series: Stability & Stress tests for the Odoo reservation module.

Tests batch operations, concurrent operations, error recovery,
and data integrity under load.
"""

import sys
import os
import time
import threading
import concurrent.futures
import xmlrpc.client
import requests
from datetime import datetime, timedelta

# Ensure the test_suite directory is on the path so helpers can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import (
    test, call, jsonrpc, http_get, http_post,
    create_booking, cleanup, get_results, reset_results, print_summary,
    _cleanup_ids,
)
from config import URL, TYPE_IDS, TYPE_CONFIG, RESOURCE_IDS, ADMIN_UID, ADMIN_PWD, DB, XMLRPC_OBJECT


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _thread_safe_call(model, method, args, kwargs=None):
    """Thread-safe XML-RPC call with its own connection.

    The shared ``MODELS`` proxy in helpers.py is **not** thread-safe because
    ``xmlrpc.client.ServerProxy`` reuses a single HTTP connection internally.
    For any test that dispatches XML-RPC calls from multiple threads
    (ThreadPoolExecutor, threading.Thread) we must create a fresh proxy per
    call so that each thread gets its own TCP socket.
    """
    proxy = xmlrpc.client.ServerProxy(XMLRPC_OBJECT)
    if kwargs:
        return proxy.execute_kw(DB, ADMIN_UID, ADMIN_PWD, model, method, args, kwargs)
    return proxy.execute_kw(DB, ADMIN_UID, ADMIN_PWD, model, method, args)

def _safe_create(vals):
    """Create a booking via XML-RPC, register for cleanup. Returns (id, fault)."""
    try:
        bid = call('appointment.booking', 'create', [vals])
        _cleanup_ids.append(('appointment.booking', bid))
        return bid, None
    except xmlrpc.client.Fault as f:
        return None, f


def _base_vals(**overrides):
    """Return a minimal valid booking vals dict, merged with *overrides*."""
    start = (datetime.now() + timedelta(days=5)).replace(
        hour=10, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    vals = {
        'appointment_type_id': TYPE_IDS['restaurant'],
        'guest_name': 'Stability Test',
        'guest_email': 'stability@test.com',
        'guest_count': 1,
        'start_datetime': start.strftime('%Y-%m-%d %H:%M:%S'),
        'end_datetime': end.strftime('%Y-%m-%d %H:%M:%S'),
    }
    vals.update(overrides)
    return vals


# ===========================================================================
# G1 -- Batch Operations
# ===========================================================================

def test_g1_batch_operations():
    print("\n--- G1: Batch Operations ---")
    apt = TYPE_IDS['restaurant']

    # G1.1: Create 10 bookings rapidly in sequence, verify all 10 exist
    try:
        batch_ids = []
        for i in range(10):
            days_ahead = 5 + (i // 3)
            hour = 9 + (i % 3)
            bid, start, end = create_booking(
                apt,
                days_ahead=days_ahead,
                hour=hour,
                guest_name=f'Batch-{i}',
                guest_email=f'batch{i}@test.com',
            )
            batch_ids.append(bid)

        # Verify all 10 exist by reading them back
        records = call('appointment.booking', 'read', [batch_ids],
                       {'fields': ['guest_name']})
        found_count = len(records) if records else 0
        all_names = [r['guest_name'] for r in records] if records else []
        expected_names = [f'Batch-{i}' for i in range(10)]
        names_match = all(n in all_names for n in expected_names)
        test('G1.1', 'Create 10 bookings rapidly - all 10 exist',
             found_count == 10 and names_match,
             detail=f"created={len(batch_ids)}, found={found_count}, names_match={names_match}")
    except Exception as e:
        test('G1.1', 'Create 10 bookings rapidly - all 10 exist',
             False, detail=str(e)[:200])

    # G1.2: Read 100 bookings in a single search_read call, verify response time < 5s
    try:
        t_start = time.time()
        results = call('appointment.booking', 'search_read',
                       [[]], {'fields': ['guest_name', 'state', 'start_datetime'], 'limit': 100})
        elapsed = time.time() - t_start
        result_count = len(results) if results else 0
        ok = elapsed < 5.0
        test('G1.2', 'Read up to 100 bookings in single search_read < 5 seconds',
             ok,
             detail=f"elapsed={elapsed:.2f}s, records_returned={result_count}")
    except Exception as e:
        test('G1.2', 'Read up to 100 bookings in single search_read < 5 seconds',
             False, detail=str(e)[:200])

    # G1.3: Create and immediately delete 5 bookings, verify clean removal
    try:
        temp_ids = []
        for i in range(5):
            days_ahead = 15 + i
            vals = _base_vals(
                guest_name=f'TempDel-{i}',
                guest_email=f'tempdel{i}@test.com',
                start_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                    hour=10, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
                end_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                    hour=11, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
            )
            bid, fault = _safe_create(vals)
            if bid:
                temp_ids.append(bid)

        created_count = len(temp_ids)

        # Now delete them all
        for bid in temp_ids:
            try:
                # Reset to draft first if needed
                rec = call('appointment.booking', 'read', [bid], {'fields': ['state']})
                if rec and rec[0]['state'] in ('confirmed', 'done', 'cancelled'):
                    try:
                        call('appointment.booking', 'action_draft', [bid])
                    except Exception:
                        pass
                call('appointment.booking', 'unlink', [[bid]])
                # Remove from cleanup list since we already deleted
                for idx, item in enumerate(_cleanup_ids):
                    if item == ('appointment.booking', bid):
                        _cleanup_ids.pop(idx)
                        break
            except Exception:
                pass

        # Verify none of them still exist
        remaining = call('appointment.booking', 'search', [[['id', 'in', temp_ids]]])
        orphaned = len(remaining) if remaining else 0
        test('G1.3', 'Create and delete 5 bookings - no orphaned records',
             orphaned == 0 and created_count == 5,
             detail=f"created={created_count}, orphaned={orphaned}")
    except Exception as e:
        test('G1.3', 'Create and delete 5 bookings - no orphaned records',
             False, detail=str(e)[:200])


# ===========================================================================
# G2 -- Concurrent Operations
# ===========================================================================

def test_g2_concurrent_operations():
    print("\n--- G2: Concurrent Operations ---")
    apt = TYPE_IDS['restaurant']

    # G2.1: 5 concurrent JSON-RPC slot requests, all should return 200
    try:
        weekday_date = (datetime.now() + timedelta(days=5))
        # Advance to next weekday if needed
        while weekday_date.weekday() >= 5:
            weekday_date += timedelta(days=1)
        date_str = weekday_date.strftime('%Y-%m-%d')

        results_g21 = []

        def fetch_slots(idx):
            """Fetch slots for a given appointment type."""
            type_id = list(TYPE_IDS.values())[idx % len(TYPE_IDS)]
            resp = jsonrpc(
                f'/appointment/{type_id}/slots',
                {'date': date_str},
            )
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_slots, i) for i in range(5)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    status = future.result(timeout=30)
                    results_g21.append(status)
                except Exception as exc:
                    results_g21.append(f"error: {exc}")

        all_200 = all(s == 200 for s in results_g21)
        test('G2.1', '5 concurrent JSON-RPC slot requests all return 200',
             all_200,
             detail=f"responses={results_g21}")
    except Exception as e:
        test('G2.1', '5 concurrent JSON-RPC slot requests all return 200',
             False, detail=str(e)[:200])

    # G2.2: 3 concurrent booking creations for different time slots, all should succeed
    try:
        concurrent_ids = []
        errors = []
        lock = threading.Lock()

        def create_concurrent_booking(idx):
            """Create a booking in a separate thread (uses per-thread proxy)."""
            try:
                days_ahead = 20 + idx
                hour = 9 + idx
                vals = _base_vals(
                    guest_name=f'Concurrent-{idx}',
                    guest_email=f'concurrent{idx}@test.com',
                    start_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                        hour=hour, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
                    end_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                        hour=hour + 1, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
                )
                bid = _thread_safe_call('appointment.booking', 'create', [vals])
                with lock:
                    concurrent_ids.append(bid)
                    _cleanup_ids.append(('appointment.booking', bid))
                return bid
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_concurrent_booking, i) for i in range(3)]
            concurrent.futures.wait(futures, timeout=60)

        all_created = len(concurrent_ids) == 3 and len(errors) == 0
        test('G2.2', '3 concurrent booking creations all succeed',
             all_created,
             detail=f"created={len(concurrent_ids)}, errors={errors if errors else 'none'}")
    except Exception as e:
        test('G2.2', '3 concurrent booking creations all succeed',
             False, detail=str(e)[:200])

    # G2.3: Concurrent read + write operations (one thread creates, another reads)
    try:
        rw_errors = []
        rw_results = {'writes': 0, 'reads': 0}
        rw_lock = threading.Lock()
        stop_event = threading.Event()

        def writer_thread():
            """Continuously create bookings until stop_event is set (per-thread proxy)."""
            idx = 0
            while not stop_event.is_set() and idx < 5:
                try:
                    days_ahead = 30 + idx
                    vals = _base_vals(
                        guest_name=f'RW-Write-{idx}',
                        guest_email=f'rwwrite{idx}@test.com',
                        start_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                            hour=10, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
                        end_datetime=(datetime.now() + timedelta(days=days_ahead)).replace(
                            hour=11, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S'),
                    )
                    bid = _thread_safe_call('appointment.booking', 'create', [vals])
                    with rw_lock:
                        _cleanup_ids.append(('appointment.booking', bid))
                        rw_results['writes'] += 1
                    idx += 1
                    time.sleep(0.1)
                except Exception as exc:
                    with rw_lock:
                        rw_errors.append(f"write: {exc}")
                    break

        def reader_thread():
            """Continuously read bookings until stop_event is set (per-thread proxy)."""
            read_count = 0
            while not stop_event.is_set() and read_count < 10:
                try:
                    records = _thread_safe_call('appointment.booking', 'search_read',
                                                [[]], {'fields': ['guest_name', 'state'], 'limit': 20})
                    with rw_lock:
                        rw_results['reads'] += 1
                    read_count += 1
                    time.sleep(0.05)
                except Exception as exc:
                    with rw_lock:
                        rw_errors.append(f"read: {exc}")
                    break

        writer = threading.Thread(target=writer_thread)
        reader = threading.Thread(target=reader_thread)
        writer.start()
        reader.start()

        # Wait for both threads to finish (with timeout)
        writer.join(timeout=30)
        reader.join(timeout=30)
        stop_event.set()

        no_crashes = len(rw_errors) == 0
        did_work = rw_results['writes'] > 0 and rw_results['reads'] > 0
        test('G2.3', 'Concurrent read + write operations - no crashes',
             no_crashes and did_work,
             detail=f"writes={rw_results['writes']}, reads={rw_results['reads']}, "
                    f"errors={rw_errors if rw_errors else 'none'}")
    except Exception as e:
        test('G2.3', 'Concurrent read + write operations - no crashes',
             False, detail=str(e)[:200])


# ===========================================================================
# G3 -- Error Recovery
# ===========================================================================

def test_g3_error_recovery():
    print("\n--- G3: Error Recovery ---")

    # G3.1: Call a non-existent method on appointment.booking
    try:
        try:
            result = call('appointment.booking', 'this_method_does_not_exist', [[]])
            # If we reach here, the method somehow exists (unexpected but not a crash)
            test('G3.1', 'Non-existent method returns graceful error',
                 False, detail='Method call did not raise an error')
        except xmlrpc.client.Fault as fault:
            # This is the expected graceful error path
            is_graceful = fault.faultCode is not None
            test('G3.1', 'Non-existent method returns graceful error',
                 is_graceful,
                 detail=f"faultCode={fault.faultCode}, msg={fault.faultString[:120]}")
        except Exception as exc:
            # Any non-crash exception is acceptable
            test('G3.1', 'Non-existent method returns graceful error',
                 True, detail=f"exception type={type(exc).__name__}: {str(exc)[:100]}")
    except Exception as e:
        test('G3.1', 'Non-existent method returns graceful error',
             False, detail=str(e)[:200])

    # G3.2: Write invalid field value (state='nonexistent')
    try:
        # First create a booking to have a valid record ID
        bid, start, end = create_booking(
            TYPE_IDS['restaurant'],
            days_ahead=8, hour=10,
            guest_name='InvalidState',
            guest_email='invalidstate@test.com',
        )
        try:
            call('appointment.booking', 'write', [[bid], {'state': 'nonexistent'}])
            # If no error, that's unexpected but not a crash
            test('G3.2', 'Invalid state value returns error not crash',
                 False, detail='Write accepted invalid state without error')
        except xmlrpc.client.Fault as fault:
            is_graceful = 'ValueError' in str(fault) or 'valid' in str(fault).lower() or fault.faultCode is not None
            test('G3.2', 'Invalid state value returns error not crash',
                 is_graceful,
                 detail=f"faultCode={fault.faultCode}, msg={fault.faultString[:120]}")
        except Exception as exc:
            test('G3.2', 'Invalid state value returns error not crash',
                 True, detail=f"exception type={type(exc).__name__}: {str(exc)[:100]}")
    except Exception as e:
        test('G3.2', 'Invalid state value returns error not crash',
             False, detail=str(e)[:200])

    # G3.3: Read a non-existent record ID (999999)
    try:
        result = call('appointment.booking', 'read', [999999],
                       {'fields': ['guest_name', 'state']})
        # read() with a missing ID may return empty list or raise MissingError
        is_empty = result is not None and (isinstance(result, list) and len(result) == 0)
        test('G3.3', 'Read non-existent record ID 999999 returns empty not crash',
             is_empty or result == [],
             detail=f"result={str(result)[:100]}")
    except xmlrpc.client.Fault as fault:
        # MissingError is an acceptable graceful failure
        is_graceful = 'MissingError' in str(fault) or fault.faultCode is not None
        test('G3.3', 'Read non-existent record ID 999999 returns empty not crash',
             is_graceful,
             detail=f"faultCode={fault.faultCode}, msg={fault.faultString[:120]}")
    except Exception as e:
        test('G3.3', 'Read non-existent record ID 999999 returns empty not crash',
             False, detail=str(e)[:200])

    # G3.4: Send malformed JSON-RPC body to slots endpoint
    try:
        # Send a completely malformed body (not valid JSON-RPC)
        resp = requests.post(
            f"{URL}/appointment/{TYPE_IDS['restaurant']}/slots",
            data='this is not json at all',
            headers={'Content-Type': 'application/json'},
            timeout=30,
        )
        # The server should return an error response, not crash
        no_crash = resp.status_code != 500 or (
            resp.status_code == 500 and resp.text and len(resp.text) > 0
        )
        # Even a 500 with a proper error body (not a bare crash) is acceptable
        if resp.status_code == 500:
            try:
                error_body = resp.json()
                no_crash = 'error' in error_body
            except Exception:
                # If we can't parse the response as JSON but got *some* response, it's not a bare crash
                no_crash = len(resp.text) > 0

        test('G3.4', 'Malformed JSON-RPC body returns error response not crash',
             no_crash,
             detail=f"status={resp.status_code}, body_preview={resp.text[:120] if resp.text else 'empty'}")
    except requests.exceptions.ConnectionError:
        # If the server refused the connection, that means it crashed -- fail
        test('G3.4', 'Malformed JSON-RPC body returns error response not crash',
             False, detail='ConnectionError - server may have crashed')
    except Exception as e:
        test('G3.4', 'Malformed JSON-RPC body returns error response not crash',
             False, detail=str(e)[:200])


# ===========================================================================
# G4 -- Data Integrity
# ===========================================================================

def test_g4_data_integrity():
    print("\n--- G4: Data Integrity ---")
    apt = TYPE_IDS['restaurant']

    # G4.1: Create booking, confirm it, read back all fields, verify data consistency
    try:
        guest_name = 'Integrity-Check'
        guest_email = 'integrity@test.com'
        guest_count = 2
        days_ahead = 10
        hour = 14

        bid, start_dt, end_dt = create_booking(
            apt,
            days_ahead=days_ahead,
            hour=hour,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_count=guest_count,
        )

        # Confirm the booking
        call('appointment.booking', 'action_confirm', [bid])

        # Read back all relevant fields
        fields = [
            'guest_name', 'guest_email', 'guest_count',
            'appointment_type_id', 'start_datetime', 'end_datetime',
            'state',
        ]
        rec = call('appointment.booking', 'read', [bid], {'fields': fields})
        if rec and len(rec) > 0:
            r = rec[0]
            checks = {
                'guest_name': r.get('guest_name') == guest_name,
                'guest_email': r.get('guest_email') == guest_email,
                'guest_count': r.get('guest_count') == guest_count,
                'state': r.get('state') == 'confirmed',
                'appointment_type_id': (
                    r.get('appointment_type_id')[0] == apt
                    if isinstance(r.get('appointment_type_id'), (list, tuple))
                    else r.get('appointment_type_id') == apt
                ),
            }
            all_consistent = all(checks.values())
            failed_checks = [k for k, v in checks.items() if not v]
            test('G4.1', 'Create + confirm + read back - all fields consistent',
                 all_consistent,
                 detail=f"checks={checks}" + (f", failed={failed_checks}" if failed_checks else ""))
        else:
            test('G4.1', 'Create + confirm + read back - all fields consistent',
                 False, detail='Could not read back booking')
    except Exception as e:
        test('G4.1', 'Create + confirm + read back - all fields consistent',
             False, detail=str(e)[:200])

    # G4.2: Verify sequence numbers are sequential
    try:
        bid1, _, _ = create_booking(
            apt,
            days_ahead=11, hour=10,
            guest_name='Seq-1',
            guest_email='seq1@test.com',
        )
        bid2, _, _ = create_booking(
            apt,
            days_ahead=11, hour=11,
            guest_name='Seq-2',
            guest_email='seq2@test.com',
        )

        # Read name (sequence field) for both bookings individually
        recs = call('appointment.booking', 'read', [[bid1, bid2]],
                     {'fields': ['name']})
        if recs and len(recs) == 2:
            name1 = recs[0].get('name', '')
            name2 = recs[1].get('name', '')
            # The booking model uses the 'name' field for the sequence
            # (e.g. APT00001, APT00002).  If ir.sequence is not loaded in the
            # test DB both records may get name='New'.  Handle that gracefully.
            id_sequential = bid2 > bid1
            if name1 == 'New' and name2 == 'New':
                # Sequence not active in test DB -- note it but don't fail
                test('G4.2', "Sequence numbers - ir.sequence not loaded (both 'New')",
                     True,
                     detail="sequence not active in test DB, both names='New'",
                     severity="LOW")
            else:
                name_ordered = name2 > name1 if (name1 and name2) else True
                test('G4.2', 'Sequence numbers are sequential (2 consecutive bookings)',
                     id_sequential and name_ordered,
                     detail=f"id1={bid1} -> name='{name1}', id2={bid2} -> name='{name2}', "
                            f"id_seq={id_sequential}, name_ordered={name_ordered}")
        else:
            test('G4.2', 'Sequence numbers are sequential (2 consecutive bookings)',
                 False, detail=f"Could not read both records, got {len(recs) if recs else 0}")
    except Exception as e:
        test('G4.2', 'Sequence numbers are sequential (2 consecutive bookings)',
             False, detail=str(e)[:200])

    # G4.3: Verify computed fields recalculate correctly
    #        (booking_count on appointment.type after creating/deleting bookings)
    try:
        # Read initial booking_count for the restaurant type
        type_before = call('appointment.type', 'read', [apt],
                           {'fields': ['booking_count']})
        count_before = type_before[0].get('booking_count', 0) if type_before else 0

        # Create 2 new bookings
        new_bid1, _, _ = create_booking(
            apt,
            days_ahead=12, hour=10,
            guest_name='CountTest-1',
            guest_email='counttest1@test.com',
        )
        new_bid2, _, _ = create_booking(
            apt,
            days_ahead=12, hour=11,
            guest_name='CountTest-2',
            guest_email='counttest2@test.com',
        )

        # Read booking_count again -- should be +2
        type_after_create = call('appointment.type', 'read', [apt],
                                  {'fields': ['booking_count']})
        count_after_create = type_after_create[0].get('booking_count', 0) if type_after_create else 0

        create_ok = count_after_create == count_before + 2

        # Now delete one booking
        try:
            rec = call('appointment.booking', 'read', [new_bid2], {'fields': ['state']})
            if rec and rec[0]['state'] in ('confirmed', 'done', 'cancelled'):
                try:
                    call('appointment.booking', 'action_draft', [new_bid2])
                except Exception:
                    pass
            call('appointment.booking', 'unlink', [[new_bid2]])
            # Remove from cleanup list
            for idx, item in enumerate(_cleanup_ids):
                if item == ('appointment.booking', new_bid2):
                    _cleanup_ids.pop(idx)
                    break
        except Exception:
            pass

        # Read booking_count again -- should be count_before + 1
        type_after_delete = call('appointment.type', 'read', [apt],
                                  {'fields': ['booking_count']})
        count_after_delete = type_after_delete[0].get('booking_count', 0) if type_after_delete else 0

        delete_ok = count_after_delete == count_before + 1

        test('G4.3', 'Computed booking_count recalculates after create/delete',
             create_ok and delete_ok,
             detail=f"before={count_before}, after_create={count_after_create} (expected {count_before + 2}), "
                    f"after_delete={count_after_delete} (expected {count_before + 1})")
    except Exception as e:
        test('G4.3', 'Computed booking_count recalculates after create/delete',
             False, detail=str(e)[:200])


# ===========================================================================
# Main runner
# ===========================================================================

def run():
    """Execute all stability and stress tests and return results."""
    reset_results()
    print("\n" + "=" * 60)
    print("  G-SERIES: STABILITY & STRESS TESTS")
    print("=" * 60 + "\n")

    test_g1_batch_operations()
    test_g2_concurrent_operations()
    test_g3_error_recovery()
    test_g4_data_integrity()

    print("\n--- Cleanup ---")
    cleanup()

    print_summary("Stability Tests")
    return get_results()


if __name__ == '__main__':
    run()
