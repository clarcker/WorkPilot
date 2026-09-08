"""Eval runner 集成测试。"""
import pytest
from eval.runner import load_cases


@pytest.mark.no_db
def test_load_cases():
    cases = load_cases()
    assert len(cases) >= 10
    for case in cases:
        assert "id" in case
        assert "question" in case
        assert "expected_intent" in case