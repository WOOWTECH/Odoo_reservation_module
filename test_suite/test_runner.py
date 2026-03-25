# -*- coding: utf-8 -*-
"""
Main test runner for reservation_module comprehensive test suite.

Executes all test modules in sequence, aggregates results, and produces
a final GO/NO-GO assessment based on the PRD criteria:
  - 0 CRITICAL failures
  - 0 HIGH failures
  - <= 3 MEDIUM failures
  = GO for production

Usage:
    python3 test_runner.py              # Run all modules
    python3 test_runner.py --module api # Run specific module
    python3 test_runner.py --loop 3     # Run all modules 3 times (multi-loop)
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Ensure test_suite directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- Module registry ----
# Each entry: (module_name, display_name, series_prefix)
MODULE_REGISTRY = [
    ('test_frontend', 'A-Series: Frontend/Page Tests', 'A'),
    ('test_api', 'B-Series: API Endpoint Tests', 'B'),
    ('test_backend', 'C-Series: Backend Logic Tests', 'C'),
    ('test_per_type', 'D-Series: Per-Type Lifecycle Tests', 'D'),
    ('test_edge_cases', 'E-Series: Edge Case Tests', 'E'),
    ('test_security', 'F-Series: Security Tests', 'F'),
    ('test_stability', 'G-Series: Stability Tests', 'G'),
]


def _import_module(name):
    """Dynamically import a test module."""
    try:
        mod = __import__(name)
        return mod
    except ImportError as e:
        print(f"  [SKIP] Could not import {name}: {e}")
        return None
    except Exception as e:
        print(f"  [ERROR] Failed to load {name}: {e}")
        return None


def run_module(mod_name, display_name):
    """Run a single test module and return its results."""
    print(f"\n{'#' * 70}")
    print(f"# {display_name}")
    print(f"{'#' * 70}")

    mod = _import_module(mod_name)
    if mod is None:
        return []

    if not hasattr(mod, 'run'):
        print(f"  [SKIP] {mod_name} has no run() function")
        return []

    start = time.time()
    try:
        results = mod.run()
    except Exception as e:
        print(f"\n  [CRASH] {mod_name}.run() raised: {e}")
        results = [{'id': f'{mod_name}_CRASH', 'name': f'{display_name} crashed',
                     'status': 'FAIL', 'detail': str(e), 'severity': 'CRITICAL'}]
    elapsed = time.time() - start
    print(f"\n  [{mod_name}] completed in {elapsed:.1f}s")
    return results or []


def aggregate_results(all_results):
    """Aggregate results from all modules."""
    total = len(all_results)
    passed = sum(1 for r in all_results if r['status'] == 'PASS')
    failed = sum(1 for r in all_results if r['status'] == 'FAIL')

    # Count by severity
    severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for r in all_results:
        if r['status'] == 'FAIL':
            sev = r.get('severity', 'MEDIUM')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return total, passed, failed, severity_counts


def print_final_report(all_results, loop_num=None):
    """Print the final aggregated report."""
    total, passed, failed, severity = aggregate_results(all_results)

    loop_label = f" (Loop #{loop_num})" if loop_num else ""
    print(f"\n{'=' * 70}")
    print(f"  COMPREHENSIVE TEST REPORT{loop_label}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 70}")
    print(f"\n  Total:    {total}")
    print(f"  Passed:   {passed}  ({passed*100//max(total,1)}%)")
    print(f"  Failed:   {failed}  ({failed*100//max(total,1)}%)")
    print(f"\n  Failures by severity:")
    print(f"    CRITICAL: {severity.get('CRITICAL', 0)}")
    print(f"    HIGH:     {severity.get('HIGH', 0)}")
    print(f"    MEDIUM:   {severity.get('MEDIUM', 0)}")
    print(f"    LOW:      {severity.get('LOW', 0)}")

    # GO/NO-GO assessment
    go = (severity.get('CRITICAL', 0) == 0 and
          severity.get('HIGH', 0) == 0 and
          severity.get('MEDIUM', 0) <= 3)

    print(f"\n  {'=' * 40}")
    if go:
        print(f"  VERDICT:  *** GO ***  (Production Ready)")
    else:
        print(f"  VERDICT:  *** NO-GO ***  (Needs Fixes)")
        if severity.get('CRITICAL', 0) > 0:
            print(f"    Reason: {severity['CRITICAL']} CRITICAL failures")
        if severity.get('HIGH', 0) > 0:
            print(f"    Reason: {severity['HIGH']} HIGH failures")
        if severity.get('MEDIUM', 0) > 3:
            print(f"    Reason: {severity['MEDIUM']} MEDIUM failures (max 3)")
    print(f"  {'=' * 40}")

    # Failure details
    if failed > 0:
        print(f"\n  FAILURE DETAILS:")
        print(f"  {'-' * 60}")
        for r in all_results:
            if r['status'] == 'FAIL':
                print(f"  [{r.get('severity', 'MEDIUM')}] {r['id']}: {r['name']}")
                if r.get('detail'):
                    print(f"           {r['detail'][:120]}")
        print(f"  {'-' * 60}")

    return go


def main():
    parser = argparse.ArgumentParser(description='Reservation Module Test Suite')
    parser.add_argument('--module', '-m', type=str, default=None,
                        help='Run specific module (e.g., api, backend, frontend)')
    parser.add_argument('--loop', '-l', type=int, default=1,
                        help='Number of test loops (default: 1)')
    parser.add_argument('--stop-on-fail', action='store_true',
                        help='Stop after first module with failures')
    args = parser.parse_args()

    print(f"\n{'*' * 70}")
    print(f"  RESERVATION MODULE - COMPREHENSIVE TEST SUITE")
    print(f"  reservation_module v18.0.1.5.0")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Loops: {args.loop}")
    print(f"{'*' * 70}")

    # Filter modules if --module specified
    modules_to_run = MODULE_REGISTRY
    if args.module:
        modules_to_run = [
            (name, display, prefix)
            for name, display, prefix in MODULE_REGISTRY
            if args.module.lower() in name.lower() or args.module.upper() == prefix
        ]
        if not modules_to_run:
            print(f"\n  No module matching '{args.module}' found.")
            print(f"  Available: {', '.join(n for n, _, _ in MODULE_REGISTRY)}")
            sys.exit(1)

    all_loop_results = []
    overall_start = time.time()

    for loop in range(1, args.loop + 1):
        if args.loop > 1:
            print(f"\n{'@' * 70}")
            print(f"  LOOP {loop}/{args.loop}")
            print(f"{'@' * 70}")

        loop_results = []
        for mod_name, display_name, prefix in modules_to_run:
            results = run_module(mod_name, display_name)
            loop_results.extend(results)

            if args.stop_on_fail:
                fails = sum(1 for r in results if r['status'] == 'FAIL')
                if fails > 0:
                    print(f"\n  [STOP] --stop-on-fail triggered in {mod_name}")
                    break

        go = print_final_report(loop_results, loop_num=loop if args.loop > 1 else None)
        all_loop_results.append({
            'loop': loop,
            'results': loop_results,
            'go': go,
        })

    # Multi-loop summary
    if args.loop > 1:
        overall_elapsed = time.time() - overall_start
        print(f"\n{'=' * 70}")
        print(f"  MULTI-LOOP SUMMARY ({args.loop} loops, {overall_elapsed:.1f}s total)")
        print(f"{'=' * 70}")
        for lr in all_loop_results:
            total, passed, failed, sev = aggregate_results(lr['results'])
            verdict = "GO" if lr['go'] else "NO-GO"
            print(f"  Loop {lr['loop']}: {passed}/{total} PASS | "
                  f"C={sev.get('CRITICAL',0)} H={sev.get('HIGH',0)} "
                  f"M={sev.get('MEDIUM',0)} L={sev.get('LOW',0)} | {verdict}")

        # Overall verdict: GO only if ALL loops pass
        all_go = all(lr['go'] for lr in all_loop_results)
        print(f"\n  OVERALL: {'*** GO ***' if all_go else '*** NO-GO ***'}")
        print(f"{'=' * 70}")

    total_elapsed = time.time() - overall_start
    print(f"\n  Total execution time: {total_elapsed:.1f}s")
    print(f"  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Exit code: 0 if last loop passed, 1 otherwise
    last_go = all_loop_results[-1]['go'] if all_loop_results else False
    sys.exit(0 if last_go else 1)


if __name__ == '__main__':
    main()
