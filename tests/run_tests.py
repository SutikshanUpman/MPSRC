"""Run every ingestion test and print pass/fail counts.  Usage: python tests/run_tests.py"""
import sys
import unittest
from pathlib import Path

here = Path(__file__).resolve().parent
suite = unittest.defaultTestLoader.discover(str(here), pattern="test_*.py", top_level_dir=str(here))
result = unittest.TextTestRunner(verbosity=1).run(suite)
failed = len(result.failures) + len(result.errors)
print(f"\nPASSED {result.testsRun - failed - len(result.skipped)}  FAILED {failed}  SKIPPED {len(result.skipped)}")
sys.exit(1 if failed else 0)
