# -*- coding: utf-8 -*-
"""Playwright E2E Test Runner — reservation_module v18.0.1.5.0

Orchestrates all P1-P10 test modules, aggregates results,
and produces a GO/NO-GO verdict.

Usage:
    python3 pw_runner.py                    # Run all modules
    python3 pw_runner.py --module P1        # Run single module
    python3 pw_runner.py --module P1,P4,P8  # Run specific modules
"""

import sys
import os
import time
import argparse
import traceback

# Add test_suite_pw to path
sys.path.insert(0, os.path.dirname(__file__))

# Import test modules
import test_P1_listing
import test_P2_detail
import test_P3_schedule
import test_P4_booking
import test_P5_confirm
import test_P6_cancel
import test_P7_payment
import test_P8_integration
import test_P9_validation
import test_P10_edge

MODULES = {
    'P1': ('Listing Page', test_P1_listing),
    'P2': ('Detail Page', test_P2_detail),
    'P3': ('Schedule/Calendar', test_P3_schedule),
    'P4': ('Booking Form', test_P4_booking),
    'P5': ('Confirmation', test_P5_confirm),
    'P6': ('Cancellation', test_P6_cancel),
    'P7': ('Payment Flow', test_P7_payment),
    'P8': ('Integration', test_P8_integration),
    'P9': ('Validation', test_P9_validation),
    'P10': ('Edge Cases', test_P10_edge),
}


def run_module(key, name, mod):
    """Run a single test module and return its results."""
    print(f'\n{"="*70}')
    print(f'  MODULE {key}: {name}')
    print(f'{"="*70}')
    t0 = time.time()
    try:
        results = mod.run()
    except Exception as e:
        print(f'  [CRASH] Module {key} crashed: {e}')
        traceback.print_exc()
        results = [{
            'id': f'{key}.CRASH',
            'name': f'Module {key} crashed',
            'passed': False,
            'detail': str(e),
            'severity': 'CRITICAL',
        }]
    elapsed = time.time() - t0
    passed = sum(1 for r in results if r['passed'])
    failed = sum(1 for r in results if not r['passed'])
    print(f'  --- {key} Summary: {passed}/{len(results)} PASS, {failed} FAIL ({elapsed:.1f}s)')
    return results, elapsed


def print_report(all_results, elapsed_total, module_times):
    """Print the final report with GO/NO-GO verdict."""
    total = len(all_results)
    passed = sum(1 for r in all_results if r['passed'])
    failed = sum(1 for r in all_results if not r['passed'])
    failures = [r for r in all_results if not r['passed']]

    # Severity breakdown
    sev_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for f in failures:
        sev = f.get('severity', 'MEDIUM')
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    print(f'\n{"#"*70}')
    print(f'  PLAYWRIGHT E2E TEST REPORT — reservation_module v18.0.1.5.0')
    print(f'{"#"*70}')
    print(f'\n  Total: {total} | Pass: {passed} | Fail: {failed} | Rate: {passed/total*100:.1f}%')
    print(f'  Time: {elapsed_total:.1f}s')
    print()

    # Module breakdown
    print(f'  {"Module":<12} {"Tests":>6} {"Pass":>6} {"Fail":>6} {"Time":>8}')
    print(f'  {"-"*42}')
    idx = 0
    for key, (name, _mod) in MODULES.items():
        if key not in module_times:
            continue
        mod_results = [r for r in all_results if r['id'].startswith(key[1:]) or r['id'].startswith(f'{key}.') or r['id'].startswith(f'P{key[1:]}.')]
        # Fallback: count by position
        if not mod_results:
            mod_results = all_results[idx:idx+50]  # rough slice
        mp = sum(1 for r in mod_results if r['passed'])
        mf = sum(1 for r in mod_results if not r['passed'])
        mt = module_times[key]
        print(f'  {key:<12} {mp+mf:>6} {mp:>6} {mf:>6} {mt:>7.1f}s')
        idx += len(mod_results)

    # Severity breakdown
    print(f'\n  Severity Breakdown:')
    for sev in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'):
        count = sev_counts.get(sev, 0)
        marker = ' <<<' if count > 0 and sev in ('CRITICAL', 'HIGH') else ''
        print(f'    {sev:<10} {count:>3}{marker}')

    # Failure details
    if failures:
        print(f'\n  Failed Tests:')
        for f in failures:
            sev = f.get('severity', 'MEDIUM')
            print(f'    [{sev}] {f["id"]}: {f["name"]}')
            if f.get('detail'):
                detail = f['detail'][:200]
                print(f'           {detail}')

    # GO/NO-GO verdict
    print(f'\n{"="*70}')
    go = (sev_counts['CRITICAL'] == 0 and
          sev_counts['HIGH'] == 0 and
          sev_counts['MEDIUM'] <= 3)

    if go:
        print(f'  VERDICT: *** GO *** ({passed}/{total} PASS, {passed/total*100:.1f}%)')
    else:
        blockers = []
        if sev_counts['CRITICAL'] > 0:
            blockers.append(f"{sev_counts['CRITICAL']} CRITICAL")
        if sev_counts['HIGH'] > 0:
            blockers.append(f"{sev_counts['HIGH']} HIGH")
        if sev_counts['MEDIUM'] > 3:
            blockers.append(f"{sev_counts['MEDIUM']} MEDIUM (>3)")
        print(f'  VERDICT: *** NO-GO *** — Blockers: {", ".join(blockers)}')
    print(f'{"="*70}\n')

    return go


def main():
    parser = argparse.ArgumentParser(description='Playwright E2E Test Runner')
    parser.add_argument('--module', '-m', type=str, default='',
                        help='Comma-separated module keys (e.g. P1,P4,P8)')
    args = parser.parse_args()

    # Determine which modules to run
    if args.module:
        keys = [k.strip().upper() for k in args.module.split(',')]
        to_run = [(k, MODULES[k][0], MODULES[k][1]) for k in keys if k in MODULES]
        if not to_run:
            print(f'No valid modules: {args.module}')
            print(f'Available: {", ".join(MODULES.keys())}')
            sys.exit(1)
    else:
        to_run = [(k, name, mod) for k, (name, mod) in MODULES.items()]

    print(f'Playwright E2E Test Runner — {len(to_run)} modules')
    print(f'Modules: {", ".join(k for k, _, _ in to_run)}')

    all_results = []
    module_times = {}
    t_start = time.time()

    for key, name, mod in to_run:
        results, elapsed = run_module(key, name, mod)
        all_results.extend(results)
        module_times[key] = elapsed

    elapsed_total = time.time() - t_start
    go = print_report(all_results, elapsed_total, module_times)
    sys.exit(0 if go else 1)


if __name__ == '__main__':
    main()
