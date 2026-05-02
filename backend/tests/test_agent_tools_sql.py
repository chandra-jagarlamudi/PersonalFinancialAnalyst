"""Read-only sql_select validation (unit — fails before touching Postgres)."""

from __future__ import annotations

import pytest

from pfa.agent_tools import tool_sql_select


def test_sql_select_rejects_disallowed_keyword():
    with pytest.raises(ValueError, match="disallowed"):
        tool_sql_select(query="DELETE FROM transactions LIMIT 1")


def test_sql_select_rejects_multiple_statements():
    with pytest.raises(ValueError, match="semicolon"):
        tool_sql_select(query="SELECT 1 LIMIT 1; SELECT 2 LIMIT 2")


def test_sql_select_requires_limit_suffix():
    with pytest.raises(ValueError, match="LIMIT"):
        tool_sql_select(query="SELECT 1 AS x")


def test_sql_select_requires_reasonable_limit_bound():
    with pytest.raises(ValueError, match="LIMIT"):
        tool_sql_select(query="SELECT 1 AS x LIMIT 501")


def test_sql_select_requires_select_or_with():
    with pytest.raises(ValueError, match="only SELECT"):
        tool_sql_select(query="SHOW TABLES LIMIT 1")
