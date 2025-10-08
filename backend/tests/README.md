# Backend Unit Tests

This directory contains unit tests for the backend components, with a focus on testing the `shelfmark` hybrid property of the `SierraItem` class.

## Test Structure

- [`__init__.py`](backend/tests/__init__.py): Package initialization
- [`conftest.py`](backend/tests/conftest.py): Pytest fixtures and shared test data
- [`test_sierra_item_shelfmark.py`](backend/tests/test_sierra_item_shelfmark.py): Comprehensive tests for the shelfmark hybrid property

## Running Tests

### Prerequisites

Install the required development dependencies:

```bash
# Install from dev-requirements.txt
pip install -r dev-requirements.txt

# Or install individual packages
pip install pytest pytest-asyncio pytest-mock pytest-cov
```

### Running All Tests

From the backend directory:

```bash
# Run all tests with verbose output
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run with HTML coverage report
pytest --cov=src --cov-report=html:htmlcov
```

### Running Specific Tests

```bash
# Run only shelfmark tests
pytest tests/test_sierra_item_shelfmark.py

# Run specific test class
pytest tests/test_sierra_item_shelfmark.py::TestSierraItemShelfmark

# Run specific test method
pytest tests/test_sierra_item_shelfmark.py::TestSierraItemShelfmark::test_shelfmark_with_empty_json
```

## Test Configuration

The [`pytest.ini`](backend/pytest.ini) file contains the following configuration:

- **Test Discovery**: Automatically finds `test_*.py` files
- **Async Support**: Enabled via `pytest-asyncio`
- **Coverage**: 80% minimum coverage requirement
- **Output**: Verbose output with short tracebacks

## Shelfmark Tests Overview

The [`test_sierra_item_shelfmark.py`](backend/tests/test_sierra_item_shelfmark.py) file includes comprehensive tests for:

### SierraItem.shelfmark Property Tests

1. **Empty/Invalid Data Handling**
   - `test_shelfmark_with_empty_json()`: Tests None and empty string cases
   - `test_shelfmark_with_invalid_json()`: Tests malformed JSON handling

2. **MARC Priority Testing**
   - `test_shelfmark_priority_100_a_ind1_1()`: Highest priority field
   - `test_shelfmark_priority_110_a_ind1_2()`: Corporate author handling
   - `test_shelfmark_all_marc_priorities()`: Complete priority order testing

3. **Field Priority Logic**
   - `test_shelfmark_higher_priority_wins()`: Priority override behavior
   - `test_shelfmark_fallback_to_later_priority()`: Fallback mechanism

4. **Special Cases**
   - `test_shelfmark_245_with_skip()`: Title field skip parameter
   - `test_shelfmark_json_with_single_quotes()`: JSON preprocessing
   - `test_shelfmark_no_matching_fields()`: No valid fields scenario

### signumize() Function Tests

1. **Basic Functionality**
   - `test_signumize_basic_latin_text()`: Standard Latin text processing
   - `test_signumize_with_skip()`: Skip parameter functionality
   - `test_signumize_case_conversion()`: Uppercase conversion

2. **Character Handling**
   - `test_signumize_mixed_characters()`: Special character removal
   - `test_signumize_numbers_included()`: Number inclusion
   - `test_signumize_short_content()`: Short string handling

3. **Edge Cases**
   - `test_signumize_empty_after_cleaning()`: Empty result handling
   - `test_signumize_uroman_fallback()`: Non-Latin character processing
   - `test_signumize_long_content()`: Three-character truncation

## Test Fixtures

The [`conftest.py`](backend/tests/conftest.py) provides reusable fixtures:

- `sample_marc_data_*`: Various MARC field configurations
- `sample_sierra_item_data`: Basic SierraItem instance data
- `marc_data_*`: Special cases for character handling and edge cases

## Expected Test Coverage

The test suite covers:

- ✅ All MARC tag priority combinations (12 priority levels)
- ✅ JSON preprocessing and error handling
- ✅ Skip parameter logic for title fields
- ✅ Character cleaning and romanization
- ✅ Edge cases and error conditions
- ✅ Mock/patch testing for external dependencies

## Continuous Integration

The pytest configuration includes:

- **Coverage Requirements**: 80% minimum coverage
- **HTML Reports**: Generated in `htmlcov/` directory
- **Fail Fast**: Tests fail if coverage drops below threshold