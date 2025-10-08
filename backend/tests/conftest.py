"""
Pytest configuration and fixtures for backend tests.
"""

from datetime import datetime

import pytest


@pytest.fixture
def sample_marc_data_100_a_ind1_1():
    """Sample MARC data with highest priority field: 100, a, ind1=1."""
    return [
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "0",
            "content": "Smith, John",
        }
    ]


@pytest.fixture
def sample_marc_data_110_a_ind1_2():
    """Sample MARC data with corporate author: 110, a, ind1=2."""
    return [
        {
            "marc_tag": "110",
            "tag": "a",
            "marc_ind1": "2",
            "marc_ind2": "0",
            "content": "University of Helsinki",
        }
    ]


@pytest.fixture
def sample_marc_data_245_with_skip():
    """Sample MARC data with title field requiring skip: 245, a."""
    return [
        {
            "marc_tag": "245",
            "tag": "a",
            "marc_ind1": "0",
            "marc_ind2": "4",
            "content": "The great book about libraries",
        }
    ]


@pytest.fixture
def sample_marc_data_mixed_priority():
    """Sample MARC data with multiple fields of different priorities."""
    return [
        {
            "marc_tag": "245",
            "tag": "a",
            "marc_ind1": "0",
            "marc_ind2": "4",
            "content": "The lower priority title",
        },
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "0",
            "content": "Higher, Priority Author",
        },
        {
            "marc_tag": "110",
            "tag": "a",
            "marc_ind1": "2",
            "marc_ind2": "0",
            "content": "Some Corporation",
        },
    ]


@pytest.fixture
def sample_sierra_item_data():
    """Basic SierraItem data for creating test instances."""
    return {
        "item_record_id": 12345,
        "item_number": "i12345678",
        "barcode": "31024123456789",
        "bib_number": "b12345678",
        "bib_record_id": 98765,
        "best_author": "Test Author",
        "best_title": "Test Title",
        "itype_code_num": 1,
        "item_type_name": "Book",
        "material_code": "a",
        "material_name": "Book",
        "classification": "123.45 T123",
        "updated_at": datetime.now(),
        "in_update_queue": False,
    }


@pytest.fixture
def sample_complex_marc_data():
    """Complex MARC data testing various edge cases."""
    return [
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "0",  # Lower priority than ind1=1
            "marc_ind2": "0",
            "content": "Anderson, Anna",
        },
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",  # Higher priority
            "marc_ind2": "0",
            "content": "Brown, Bob",
        },
        {
            "marc_tag": "110",
            "tag": "a",
            "marc_ind1": "2",
            "marc_ind2": "0",
            "content": "Finnish Library Association",
        },
        {
            "marc_tag": "245",
            "tag": "a",
            "marc_ind1": "0",
            "marc_ind2": "8",
            "content": "A study of library systems and their impact",
        },
    ]


@pytest.fixture
def marc_data_non_latin_content():
    """MARC data with non-Latin characters for uroman testing."""
    return [
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "0",
            "content": "Ääkkönen, Åke",  # Finnish characters
        }
    ]


@pytest.fixture
def marc_data_special_characters():
    """MARC data with special characters to test cleaning."""
    return [
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "0",
            "content": "O'Connor, Mary-Jane (1955-)",
        }
    ]


@pytest.fixture
def marc_data_numbers_and_symbols():
    """MARC data with numbers and symbols to test character filtering."""
    return [
        {
            "marc_tag": "100",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "0",
            "content": "3M Company!@#$%^&*()",
        }
    ]


@pytest.fixture
def marc_data_all_priorities():
    """MARC data containing all possible priority combinations for comprehensive testing."""
    return [
        {"marc_tag": "100", "tag": "a", "marc_ind1": "1", "content": "First Priority"},
        {"marc_tag": "110", "tag": "a", "marc_ind1": "2", "content": "Second Priority"},
        {"marc_tag": "100", "tag": "a", "marc_ind1": "0", "content": "Third Priority"},
        {"marc_tag": "100", "tag": "a", "marc_ind1": "2", "content": "Fourth Priority"},
        {"marc_tag": "110", "tag": "a", "marc_ind1": "1", "content": "Fifth Priority"},
        {"marc_tag": "110", "tag": "a", "marc_ind1": "0", "content": "Sixth Priority"},
        {"marc_tag": "100", "tag": "a", "marc_ind1": "3", "content": "Seventh Priority"},
        {"marc_tag": "111", "tag": "a", "marc_ind1": "0", "content": "Eighth Priority"},
        {"marc_tag": "111", "tag": "a", "marc_ind1": "1", "content": "Ninth Priority"},
        {"marc_tag": "111", "tag": "a", "marc_ind1": "2", "content": "Tenth Priority"},
        {
            "marc_tag": "245",
            "tag": "a",
            "marc_ind1": "0",
            "marc_ind2": "4",
            "content": "The Eleventh Priority",
        },
        {
            "marc_tag": "245",
            "tag": "a",
            "marc_ind1": "1",
            "marc_ind2": "3",
            "content": "An Twelfth Priority",
        },
    ]
