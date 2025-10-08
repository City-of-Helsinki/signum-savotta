"""
Unit tests for the shelfmark hybrid property of SierraItem class.
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from models.sierra_item import SierraItem, signumize  # noqa!


class TestSierraItemShelfmark:
    """Test cases for SierraItem shelfmark hybrid property."""

    def create_sierra_item(self, shelfmark_json_data=None):
        """Helper method to create SierraItem instance for testing."""
        return SierraItem(
            item_record_id=12345,
            item_number="i12345678",
            barcode="31024123456789",
            bib_number="b12345678",
            bib_record_id=98765,
            best_author="Test Author",
            best_title="Test Title",
            itype_code_num=1,
            item_type_name="Book",
            material_code="a",
            material_name="Book",
            classification="123.45 T123",
            shelfmark_json=shelfmark_json_data,
            updated_at=datetime.now(),
            in_update_queue=False,
        )

    def test_shelfmark_with_empty_json(self):
        """Test shelfmark returns '***' when shelfmark_json is empty or None."""
        # Test with None
        item = self.create_sierra_item(None)
        assert item.shelfmark == "***"

        # Test with empty string
        item.shelfmark_json = ""
        assert item.shelfmark == "***"

    def test_shelfmark_with_invalid_json(self):
        """Test shelfmark returns '***' when shelfmark_json contains invalid JSON."""
        item = self.create_sierra_item()
        item.shelfmark_json = "invalid json string"
        assert item.shelfmark == "***"

    def test_real_world_example_1(self):
        """Test real world example."""

        marc_str = "[{'marc_tag': '100', 'marc_ind1': '1', 'marc_ind2': ' ', 'field_type_code': 'a', 'tag': '0', 'content': '(FIN11)000137780'}, {'marc_tag': '100', 'marc_ind1': '1', 'marc_ind2': ' ', 'field_type_code': 'a', 'tag': 'e', 'content': 'kirjoittaja.'}, {'marc_tag': '100', 'marc_ind1': '1', 'marc_ind2': ' ', 'field_type_code': 'a', 'tag': 'a', 'content': 'Heikkil\u00e4, Markku,'}, {'marc_tag': '245', 'marc_ind1': '1', 'marc_ind2': '0', 'field_type_code': 't', 'tag': 'a', 'content': 'Kaik Turust :'}, {'marc_tag': '245', 'marc_ind1': '1', 'marc_ind2': '0', 'field_type_code': 't', 'tag': 'b', 'content': 'ei viralline mut torelline kr\u00f6ntm\u00e4ntti /'}, {'marc_tag': '245', 'marc_ind1': '1', 'marc_ind2': '0', 'field_type_code': 't', 'tag': 'c', 'content': 'Markku \"F\u00f6rin \u00e4ij\u00e4\" Heikkil\u00e4.'}]"  # noqa!

        item = self.create_sierra_item(marc_str)
        with patch("models.sierra_item.signumize", return_value="HEI") as mock_signumize:
            result = item.shelfmark
            assert result == "HEI"
            mock_signumize.assert_called_once_with("Heikkilä, Markku,", 0)


class TestSignumizeFunction:
    """Test cases for the signumize helper function."""

    def test_signumize_basic_latin_text(self):
        """Test signumize with basic Latin characters."""
        result = signumize("Smith")
        assert result == "SMI"

    def test_signumize_with_skip(self):
        """Test signumize with skip parameter."""
        result = signumize("The Book", skip=4)
        assert result == "BOO"

    def test_signumize_mixed_characters(self):
        """Test signumize removes non-Latin characters."""
        result = signumize("Sm!th@#$%^&*()", skip=0)
        assert result == "SMT"

    def test_signumize_numbers_included(self):
        """Test signumize includes numbers."""
        result = signumize("Smith123")
        assert result == "SMI"

    def test_signumize_short_content(self):
        """Test signumize with content shorter than 3 characters."""
        result = signumize("AB")
        assert result == "AB"

    @patch("models.sierra_item.ur")
    def test_signumize_uroman_fallback(self, mock_ur):
        """Test signumize falls back to uroman when no Latin characters found."""
        mock_uroman_instance = MagicMock()
        mock_uroman_instance.romanize_string.return_value = "romanized"
        mock_ur.romanize_string = mock_uroman_instance.romanize_string
        mock_ur.RomFormat.STR = "STR"

        # First regex.sub call returns empty, triggering uroman fallback
        with patch("models.sierra_item.regex") as mock_regex:
            mock_regex.sub.side_effect = [
                "",
                "ROM",
            ]  # First call empty, second call returns romanized result

            result = signumize("неалфавит")  # Non-Latin text
            assert result == "ROM"

    @patch("models.sierra_item.ur")
    def test_signumize_uroman_also_empty(self, mock_ur):
        """Test signumize raises AttributeError when even uroman returns nothing."""
        mock_uroman_instance = MagicMock()
        mock_uroman_instance.romanize_string.return_value = "!@#$"  # Will be cleaned to empty
        mock_ur.romanize_string = mock_uroman_instance.romanize_string
        mock_ur.RomFormat.STR = "STR"

        with patch("models.sierra_item.regex") as mock_regex:
            mock_regex.sub.side_effect = ["", ""]  # Both cleaning attempts return empty

            with pytest.raises(AttributeError, match="Signum is empty"):
                signumize("!@#$%")

    def test_signumize_case_conversion(self):
        """Test signumize converts to uppercase."""
        result = signumize("lowercase")
        assert result == "LOW"

    def test_signumize_long_content(self):
        """Test signumize truncates to 3 characters max."""
        result = signumize("VeryLongContentHere")
        assert result == "VER"
