#!/usr/bin/env python3
"""
Test runner script for backend unit tests with comprehensive reporting.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run the test suite with various options."""

    print("🧪 Running Backend Unit Tests")
    print("=" * 50)

    # Change to backend directory
    backend_dir = Path(__file__).parent

    try:
        # Run tests with coverage
        print("\n📊 Running tests with coverage...")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-v",
                "--tb=short",
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov",
                "--cov-fail-under=80",
            ],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )

        print(result.stdout)
        if result.stderr:
            print("Stderr:", result.stderr)

        if result.returncode == 0:
            print("\n✅ All tests passed!")
            print("📈 Coverage report generated in htmlcov/")
        else:
            print("\n❌ Some tests failed or coverage is below threshold")
            return False

    except subprocess.CalledProcessError as e:
        print(f"❌ Error running tests: {e}")
        return False
    except FileNotFoundError:
        print("❌ pytest not found. Make sure you've installed the dev dependencies:")
        print("   pip install -r ../dev-requirements.txt")
        return False

    return True


def run_specific_test(test_pattern):
    """Run specific tests matching the pattern."""

    backend_dir = Path(__file__).parent

    try:
        print(f"\n🎯 Running specific tests: {test_pattern}")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", f"tests/{test_pattern}", "-v", "--tb=short"],
            cwd=backend_dir,
        )

        return result.returncode == 0

    except Exception as e:
        print(f"❌ Error running specific tests: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific test pattern
        test_pattern = sys.argv[1]
        success = run_specific_test(test_pattern)
    else:
        # Run all tests
        success = run_tests()

    sys.exit(0 if success else 1)
