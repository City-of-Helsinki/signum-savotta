"""
Sierra classification utilities for rebuilding varFields.
"""

import regex


def rebuild_sierra_classification_varfields(
    fetched_varfields: list, new_classification: str
) -> list:
    """
    Rebuilds Sierra item classification in varFields by updating existing 099 field
    or creating a new one while preserving genre information.

    This function handles the classification update logic that was previously embedded
    in send_to_sierra. It extracts genre information from existing classifications
    using regex and combines it with the new classification.

    Args:
        fetched_varfields (list): List of varField dictionaries from Sierra API
        new_classification (str): New classification to set

    Returns:
        list: Updated varFields list with rebuilt classification

    Example:
        >>> varfields = [{"fieldTag": "c", "marcTag": "099", "subfields": [{"tag": "a", "content": "123.45 Fiction"}]}]
        >>> result = rebuild_sierra_classification_varfields(varfields, "678.90")
        >>> result[0]["subfields"][0]["content"]
        '678.90 Fiction'
    """
    if fetched_varfields is None:
        fetched_varfields = []

    updated_existing = False

    # Look for existing 099 field with classification
    for f_index, f_value in enumerate(fetched_varfields):
        if f_value["fieldTag"] == "c" and f_value["marcTag"] == "099":
            for sf_index, sf_value in enumerate(f_value["subfields"]):
                if sf_value["tag"] == "a":
                    old_classification = sf_value["content"]

                    # Extract genre information using regex
                    try:
                        match = regex.match(r"(?:[0-9,\s.]+)([\p{L}\s,-]+)", old_classification)
                        genre_text = match.group(1).strip() if match else None
                    except Exception:
                        genre_text = None

                    # Rebuild classification with new number and preserved genre
                    genre_suffix = "" if genre_text is None else f" {genre_text}"
                    fetched_varfields[f_index]["subfields"][sf_index][
                        "content"
                    ] = f"{new_classification}{genre_suffix}"
                    updated_existing = True

    # If no existing 099 field found, create a new one
    if not updated_existing:
        fetched_varfields.append(
            {
                "fieldTag": "c",
                "marcTag": "099",
                "ind1": " ",
                "ind2": " ",
                "subfields": [{"tag": "a", "content": new_classification}],
            }
        )

    return fetched_varfields
