"""Tests for the judge assertion: parsing, request building, and the
end-to-end runner/CLI wiring with a mock judge provider."""

from __future__ import annotations

from typer.testing import CliRunner

from promptdrift.adapters.mock import MockProvider
from promptdrift.domain.assertions import Judge
from promptdrift.domain.suite import MockConfig, Suite
from promptdrift.errors import StaleBaselineError
from promptdrift.services.differ import compare
from promptdrift.services.judge import (
    JUDGE_SYSTEM_PROMPT,
    JudgeBinding,
    build_judge_request,
    parse_judge_response,
)
from promptdrift.services.runner import Runner
from tests.conftest import suite_from_yaml_text

JUDGE = Judge(rubric="回复是否包含清晰的退款步骤？", min_score=4)

RUBRIC_SUITE = """
suite: judged
provider:
  mock:
    default: "1. 打开订单页 2. 点击申请退款"
samples: 3
judge:
  mock:
    default: '{"score": 5, "reason": "步骤清晰"}'
cases:
  - id: refund
    messages: [{role: user, content: "怎么退款"}]
    assertions:
      - judge:
          rubric: "回复是否包含清晰的退款步骤？"
          min_score: 4
"""


def binding_for(suite: Suite) -> JudgeBinding:
    assert isinstance(suite.judge, MockConfig)
    return JudgeBinding(provider=MockProvider(suite.judge), model=suite.judge.model_name)


def mock_target(suite: Suite) -> MockProvider:
    assert isinstance(suite.provider, MockConfig)
    return MockProvider(suite.provider)


JUDGE_BLOCK = 'judge:\n  mock:\n    default: \'{"score": 5, "reason": "步骤清晰"}\''


class TestParseJudgeResponse:
    def test_valid_json_pass_and_fail(self) -> None:
        outcome = parse_judge_response('{"score": 5, "reason": "好"}', JUDGE)
        assert outcome.passed
        assert "5/5" in (outcome.detail or "")
        assert outcome.assertion_id == JUDGE.assertion_id

        low = parse_judge_response('{"score": 2, "reason": "步骤缺失"}', JUDGE)
        assert not low.passed
        assert "min 4" in (low.detail or "")

    def test_fenced_json(self) -> None:
        text = '好的，评分如下：\n```json\n{"score": 4, "reason": "基本符合"}\n```'
        assert parse_judge_response(text, JUDGE).passed

    def test_regex_fallback_when_json_is_broken(self) -> None:
        text = '理由忘了写格式 {"score": 4, "reason": ok'
        assert parse_judge_response(text, JUDGE).passed

    def test_unparseable_fails(self) -> None:
        outcome = parse_judge_response("我觉得还行吧", JUDGE)
        assert not outcome.passed
        assert "not parseable" in (outcome.detail or "")

    def test_out_of_range_score_fails(self) -> None:
        outcome = parse_judge_response('{"score": 9, "reason": "x"}', JUDGE)
        assert not outcome.passed
        assert "1-5" in (outcome.detail or "")

    def test_non_integer_score_fails(self) -> None:
        outcome = parse_judge_response('{"score": "high", "reason": "x"}', JUDGE)
        assert not outcome.passed

    def test_boundary_is_inclusive(self) -> None:
        assert parse_judge_response('{"score": 4, "reason": ""}', JUDGE).passed
        assert not parse_judge_response('{"score": 3, "reason": ""}', JUDGE).passed


class TestBuildJudgeRequest:
    def test_request_shape(self) -> None:
        binding = JudgeBinding(
            provider=MockProvider(MockConfig()), model="judge-model", params={"temperature": 0.1}
        )
        request = build_judge_request(
            JUDGE,
            [("system", "你是客服"), ("user", "怎么退款")],
            "1. 打开订单页",
            binding,
        )
        assert request.model == "judge-model"
        assert request.temperature == 0.1
        assert [role for role, _ in request.messages] == ["system", "user"]
        assert request.messages[0][1] == JUDGE_SYSTEM_PROMPT
        user_content = request.messages[1][1]
        assert "退款步骤" in user_content
        assert "你是客服" in user_content
        assert "1. 打开订单页" in user_content


class TestRunnerWiring:
    async def test_judge_outcomes_flow_through_run(self) -> None:
        suite = suite_from_yaml_text(RUBRIC_SUITE)
        run = await Runner(mock_target(suite), binding_for(suite)).run(suite)
        case = run.case("refund")
        assert case is not None
        rates = case.rates()
        judge_id = next(aid for aid in rates if aid.startswith("judge-"))
        assert rates[judge_id] == (3, 3)

    async def test_low_judge_scores_fail(self) -> None:
        low_suite = suite_from_yaml_text(
            RUBRIC_SUITE.replace(
                '{"score": 5, "reason": "步骤清晰"}', '{"score": 1, "reason": "差"}'
            )
        )
        run = await Runner(mock_target(low_suite), binding_for(low_suite)).run(low_suite)
        case = run.case("refund")
        assert case is not None
        judge_id = next(aid for aid in case.rates() if aid.startswith("judge-"))
        assert case.rates()[judge_id] == (0, 3)

    async def test_judge_without_provider_is_a_clear_failure(self) -> None:
        suite = suite_from_yaml_text(RUBRIC_SUITE)
        run = await Runner(mock_target(suite)).run(suite)  # no judge binding
        case = run.case("refund")
        assert case is not None
        outcome = case.samples[0].outcomes[0]
        assert not outcome.passed
        assert "judge:" in (outcome.detail or "")

    async def test_judge_provider_change_stales_the_baseline(self) -> None:
        suite = suite_from_yaml_text(RUBRIC_SUITE)
        run = await Runner(mock_target(suite), binding_for(suite)).run(suite)

        changed_suite = suite_from_yaml_text(
            RUBRIC_SUITE.replace(JUDGE_BLOCK, "judge:\n  openai_compat:\n    model: other-judge")
        )
        assert changed_suite.fingerprint() != suite.fingerprint()

        from promptdrift.adapters.snapshot_store import snapshot_from_run

        snapshot = snapshot_from_run(run, suite)
        swapped = snapshot.model_copy(update={"config_fingerprint": changed_suite.fingerprint()})
        try:
            compare(run, swapped)
            raise AssertionError("expected StaleBaselineError")
        except StaleBaselineError:
            pass


class TestCliWiring:
    def test_cli_run_with_mock_judge(self, tmp_path) -> None:
        (tmp_path / "promptest.yaml").write_text(RUBRIC_SUITE, encoding="utf-8")
        result = CliRunner().invoke(
            __import__("promptdrift.cli.app", fromlist=["app"]).app,
            ["--root", str(tmp_path), "run"],
        )
        assert result.exit_code == 0, result.output
        assert "judge-" in result.output

    def test_cli_diff_with_judge_regression(self, tmp_path) -> None:
        import yaml as yaml_lib

        from promptdrift.cli.app import app

        runner = CliRunner()
        (tmp_path / "promptest.yaml").write_text(RUBRIC_SUITE, encoding="utf-8")
        assert runner.invoke(app, ["--root", str(tmp_path), "approve"]).exit_code == 0
        assert runner.invoke(app, ["--root", str(tmp_path), "diff"]).exit_code == 0

        # judge mock default changes → behavior change, fingerprint unchanged
        raw = yaml_lib.safe_load(RUBRIC_SUITE)
        raw["judge"]["mock"]["default"] = '{"score": 1, "reason": "退化"}'
        (tmp_path / "promptest.yaml").write_text(
            yaml_lib.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        regressed = runner.invoke(app, ["--root", str(tmp_path), "diff"])
        assert regressed.exit_code == 1, regressed.output
        assert "regressed" in regressed.output
