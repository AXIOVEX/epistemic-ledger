"""Stress, performance, and robustness harness (DESIGN-16).

The harness drives the real package in subprocesses — a crash test run
in-process proves nothing about crash consistency. Every sweep emits a
JSON report and classifies outcomes honestly: a store that fails loudly
and recovers is a finding; a store that is silently wrong is a failure.
"""
