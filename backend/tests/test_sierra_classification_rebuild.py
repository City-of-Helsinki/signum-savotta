"""
Unit tests for the rebuild_sierra_classification_varfields function.
"""

import os
import sys
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.sierra_classification import rebuild_sierra_classification_varfields  # noqa!


class TestRebuildSierraClassificationVarfields:
    """Test cases for rebuild_sierra_classification_varfields function."""

    def test_with_none_varfields(self):
        """Test that function creates new varfield when fetched_varfields is None."""
        result = rebuild_sierra_classification_varfields(None, "123.45")

        expected = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": "123.45"}],
            }
        ]

        assert result == expected

    def test_with_empty_varfields(self):
        """Test that function creates new varfield when fetched_varfields is empty."""
        result = rebuild_sierra_classification_varfields([], "678.90")

        expected = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": "678.90"}],
            }
        ]

        assert result == expected

    def test_update_existing_classification_with_genre(self):
        """Test updating existing 099 field that has genre information."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": "123.45 Etelä-Haaga -kokoelma"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        assert len(result) == 1
        assert result[0]["subfields"][0]["content"] == "678.90 Etelä-Haaga -kokoelma"

    def test_update_existing_classification_without_genre(self):
        """Test updating existing 099 field that has no genre information."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": "123.45"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        assert len(result) == 1
        assert result[0]["subfields"][0]["content"] == "678.90"

    def test_update_existing_classification_with_multiple_genre_words(self):
        """Test updating existing 099 field with multiple genre words."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": "123.45 Science Fiction"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        assert len(result) == 1
        assert result[0]["subfields"][0]["content"] == "678.90 Science Fiction"

    def test_no_099_field_creates_new(self):
        """Test that function creates new 099 field when none exists."""
        varfields = [
            {
                "fieldTag": "d",
                "marcTag": "245",
                "subfields": [{"tag": "a", "content": "Some Title"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "123.45")

        assert len(result) == 2  # Original + new 099 field
        assert result[1]["fieldTag"] == "c"
        assert result[1]["marcTag"] == "099"
        assert result[1]["subfields"][0]["content"] == "123.45"

    def test_099_field_without_a_subfield_creates_new(self):
        """Test that function creates new 099 field when existing one has no 'a' subfield."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "b", "content": "Some Other Content"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "123.45")

        assert len(result) == 2  # Original + new 099 field
        assert result[1]["fieldTag"] == "c"
        assert result[1]["marcTag"] == "099"
        assert result[1]["subfields"][0]["content"] == "123.45"

    def test_multiple_099_fields_updates_all_matches(self):
        """Test that function updates all 099 fields with 'a' subfield found."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "123.45 Fiction"}],
            },
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "456.78 Drama"}],
            },
        ]

        result = rebuild_sierra_classification_varfields(varfields, "999.99")

        assert len(result) == 2
        assert result[0]["subfields"][0]["content"] == "999.99 Fiction"
        assert result[1]["subfields"][0]["content"] == "999.99 Drama"  # Also updated

    @patch("utils.sierra_classification.regex")
    def test_regex_match_exception_handled(self, mock_regex):
        """Test that regex exceptions are handled gracefully."""
        mock_regex.match.side_effect = Exception("Regex error")

        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "123.45 Fiction"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        # Should still work but without genre preservation
        assert result[0]["subfields"][0]["content"] == "678.90"

    def test_regex_no_match_preserves_no_genre(self):
        """Test that when regex finds no match, no genre is preserved."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "NoNumbers"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        assert result[0]["subfields"][0]["content"] == "678.90"

    def test_classification_with_decimals_and_spaces(self):
        """Test handling of complex classification patterns."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "123.45, 678.90 Mystery Romance"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "111.22")

        assert result[0]["subfields"][0]["content"] == "111.22 Mystery Romance"

    def test_preserves_other_varfields(self):
        """Test that other varfields remain unchanged."""
        varfields = [
            {
                "fieldTag": "d",
                "marcTag": "245",
                "subfields": [{"tag": "a", "content": "Book Title"}],
            },
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "123.45 Fiction"}],
            },
            {
                "fieldTag": "e",
                "marcTag": "300",
                "subfields": [{"tag": "a", "content": "200 pages"}],
            },
        ]

        result = rebuild_sierra_classification_varfields(varfields, "999.99")

        assert len(result) == 3
        assert result[0]["marcTag"] == "245"  # Unchanged
        assert result[1]["subfields"][0]["content"] == "999.99 Fiction"  # Updated
        assert result[2]["marcTag"] == "300"  # Unchanged

    def test_empty_classification_string(self):
        """Test behavior with empty classification string."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [{"tag": "a", "content": "123.45 Fiction"}],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "")

        assert result[0]["subfields"][0]["content"] == " Fiction"

    def test_complex_subfields_structure(self):
        """Test with complex subfields structure containing multiple subfields."""
        varfields = [
            {
                "fieldTag": "c",
                "marcTag": "099",
                "subfields": [
                    {"tag": "b", "content": "Other content"},
                    {"tag": "a", "content": "123.45 Fiction"},
                    {"tag": "c", "content": "More content"},
                ],
            }
        ]

        result = rebuild_sierra_classification_varfields(varfields, "678.90")

        # Should only update the 'a' subfield
        assert result[0]["subfields"][0]["content"] == "Other content"
        assert result[0]["subfields"][1]["content"] == "678.90 Fiction"
        assert result[0]["subfields"][2]["content"] == "More content"
