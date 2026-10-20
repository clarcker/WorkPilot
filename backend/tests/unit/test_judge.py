"""Q3 judge 单元测试（解析 / 汇总，不调真实 LLM）。"""
from __future__ import annotations

from eval.judge import aggregate_judges, _parse_judge_json


class TestParseJudgeJson:
    def test_parse_clean_json(self):
        data = _parse_judge_json(
            '{"faithfulness": 5, "points_covered": "3/4", '
            '"hallucinated_claims": [], "refusal_correct": true, '
            '"citation_correct": true, "notes": "ok"}'
        )
        assert data["faithfulness"] == 5
        assert data["points_covered"] == "3/4"
        assert data["points_covered_count"] == 3
        assert data["expected_points_count"] == 4
        assert data["hallucinated_claims"] == []
        assert data["refusal_correct"] is True

    def test_parse_fenced_json(self):
        raw = "```json\n{\"faithfulness\": 2, \"points_covered_count\": 1, \"expected_points_count\": 3, \"hallucinated_claims\": [\"编造金额 9999\"]}\n```"
        data = _parse_judge_json(raw)
        assert data["faithfulness"] == 2
        assert data["hallucinated_claims"] == ["编造金额 9999"]

    def test_faithfulness_clamped(self):
        data = _parse_judge_json('{"faithfulness": 9, "points_covered": "0/0"}')
        assert data["faithfulness"] == 5
        data = _parse_judge_json('{"faithfulness": "bad"}')
        assert data["faithfulness"] == 3


class TestAggregateJudges:
    def test_aggregate(self):
        judges = [
            {"faithfulness": 5, "points_covered_count": 3, "expected_points_count": 3,
             "hallucinated_claims": [], "refusal_correct": True, "_expected_refusal": True,
             "judge_model": "deepseek-v4-flash", "judge_external": True},
            {"faithfulness": 3, "points_covered_count": 1, "expected_points_count": 2,
             "hallucinated_claims": ["假数据"], "refusal_correct": False,
             "_expected_refusal": False, "judge_model": "deepseek-v4-flash", "judge_external": True},
        ]
        agg = aggregate_judges(judges)
        assert agg["faithfulness_avg"] == 4.0
        assert agg["points_coverage"] == round(4 / 5, 4)
        assert agg["hallucination_count"] == 1
        assert agg["refusal_correct_rate"] == 1.0
        assert agg["judge_model"] == "deepseek-v4-flash"
        assert agg["local_judge"] is False

    def test_empty(self):
        agg = aggregate_judges([])
        assert agg["faithfulness_avg"] is None
