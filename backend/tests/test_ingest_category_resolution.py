"""Integration tests for category_id_from_rules."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pfa.categorization import category_id_from_rules

pytestmark = pytest.mark.integration


def test_category_id_from_rules_matches_priority(clean_db):
    cid = uuid4()
    with clean_db.cursor() as cur:
        cur.execute(
            "INSERT INTO categories (id, slug, name) VALUES (%s, %s, %s)",
            (str(cid), "food", "Food"),
        )
        cur.execute(
            """INSERT INTO categorization_rules (category_id, pattern, priority)
               VALUES (%s, %s, %s)""",
            (str(cid), "starbucks", 10),
        )
    clean_db.commit()

    got = category_id_from_rules(clean_db, "STARBUCKS SEATTLE WA")
    assert got == str(cid)
