"""Tests for the offline mock provider."""

from __future__ import annotations

from promptdrift.adapters.mock import MockProvider
from promptdrift.domain.suite import MockConfig, MockRule
from promptdrift.ports import CompletionRequest


def request(text: str) -> CompletionRequest:
    return CompletionRequest(model="mock", messages=(("user", text),))


async def test_first_matching_rule_wins() -> None:
    config = MockConfig(
        rules=[
            MockRule(contains="退款", text="规则一"),
            MockRule(contains="退款流程", text="规则二"),
        ]
    )
    response = await MockProvider(config).complete(request("退款流程是什么"))
    assert response.text == "规则一"


async def test_default_when_no_rule_matches() -> None:
    response = await MockProvider(MockConfig(default="默认回答")).complete(request("随便聊聊"))
    assert response.text == "默认回答"


async def test_default_variants_cycle() -> None:
    config = MockConfig(default_variants=["v1", "v2"])
    provider = MockProvider(config)
    texts = [(await provider.complete(request("q"))).text for _ in range(4)]
    assert texts == ["v1", "v2", "v1", "v2"]


async def test_rule_variants_cycle_for_flaky_simulation() -> None:
    config = MockConfig(rules=[MockRule(contains="退款", variants=["好", "坏"])])
    provider = MockProvider(config)
    texts = [(await provider.complete(request("退款"))).text for _ in range(3)]
    assert texts == ["好", "坏", "好"]


async def test_usage_is_synthesized_deterministically() -> None:
    config = MockConfig(default="x" * 40)
    response = await MockProvider(config).complete(request("y" * 80))
    assert response.prompt_tokens == 20
    assert response.completion_tokens == 10
    assert response.finish_reason == "stop"
    assert not response.cached


async def test_last_user_message_is_matched() -> None:
    config = MockConfig(rules=[MockRule(contains="退款", text="命中")])
    request_with_history = CompletionRequest(
        model="mock",
        messages=(("system", "你是客服"), ("user", "先聊聊天气"), ("user", "我要退款")),
    )
    response = await MockProvider(config).complete(request_with_history)
    assert response.text == "命中"


def test_provider_id() -> None:
    assert MockProvider(MockConfig()).provider_id == "mock"
