"""Bundled YAML scaffolds used by ``promptdrift init`` and ``promptdrift demo``.

Both run on the mock provider, so a fresh install can produce a meaningful
run→approve→diff story with zero API keys and zero network.
"""

from __future__ import annotations

SCHEMA_URL = (
    "https://raw.githubusercontent.com/promptdrift/promptdrift/main/schema/promptest.schema.json"
)

_STARTER_REFUND = (
    "您好！退款流程如下：1. 打开「我的订单」；2. 选择对应订单点击「申请退款」；"
    "3. 款项将在 3-5 个工作日内原路退回。"
)

STARTER_SUITE_YAML = f"""\
# promptdrift suite — prompt regression testing, flake-aware by design.
#
# This starter suite runs fully offline on the mock provider, so you can try
# the whole workflow right now:
#
#   promptdrift run       execute once
#   promptdrift approve   record this behavior as the baseline
#   promptdrift diff      compare future runs against that baseline
#
# When you are ready to test a real model, switch `provider` to openai_compat:
#
#   provider:
#     openai_compat:
#       model: glm-4.7
#       base_url: https://open.bigmodel.cn/api/paas/v4   # or DeepSeek/Qwen/OpenAI
#       api_key_env: ZHIPUAI_API_KEY
#
# Baselines live in .promptest/baselines/ and are meant to be committed.
$schema: {SCHEMA_URL}
suite: starter
description: Starter suite on the mock provider — replace with your real prompts.

provider:
  mock:
    rules:
      - contains: "退款"
        text: "{_STARTER_REFUND}"
      - contains: "发票"
        text: '{{"order_id": "A1024", "invoice_status": "issued"}}'
    default: "您好，请问有什么可以帮您？"

samples: 3        # per case; more samples = sharper statistics, higher cost
concurrency: 4    # max in-flight provider calls

cases:
  - id: refund-steps
    description: 用户询问退款流程时，回复必须包含明确的申请入口与时限。
    messages:
      - role: user
        content: "订单有点问题，我想申请{{{{topic}}}}"
    vars:
      topic: 退款
    assertions:
      - contains: "申请退款"
      - regex: "3-5 个工作日"
      - not_contains: "抱歉"

  - id: invoice-json
    description: 发票查询必须返回结构化 JSON。
    messages:
      - role: user
        content: "帮我查一下订单 A1024 的发票"
    assertions:
      - is_json: true
      - json_schema:
          type: object
          required: [order_id, invoice_status]
"""

#: The "good" refund answer the demo pins down with assertions.
DEMO_REFUND_GOOD = (
    "您好！退款流程如下：1. 打开「我的订单」；2. 选择对应订单点击「申请退款」；"
    "3. 款项将在 3-5 个工作日内原路退回。如需帮助随时找我。"
)

#: The "prompt change" the demo applies in step 3: a rushed rewrite that
#: drops the structured steps the assertions pin down.
DEMO_REFUND_BAD = "您好，退款的话您可以在 App 里自己操作一下哈。"


def demo_suite_yaml(regressed: bool = False) -> str:
    """The demo suite YAML; ``regressed=True`` swaps in the degraded answer."""
    refund_text = DEMO_REFUND_BAD if regressed else DEMO_REFUND_GOOD
    return f"""\
# promptdrift demo suite — runs offline on the mock provider.
$schema: {SCHEMA_URL}
suite: demo-support-agent
description: Demo suite for the run → approve → regress → diff walkthrough.

provider:
  mock:
    rules:
      - contains: "退款"
        text: "{refund_text}"
      - contains: "发票"
        text: '{{"order_id": "A1024", "invoice_status": "issued"}}'
    default: "您好，请问有什么可以帮您？"

samples: 3

cases:
  - id: refund-steps
    messages:
      - role: user
        content: "订单有点问题，我想申请退款"
    assertions:
      - contains: "申请退款"
      - regex: "3-5 个工作日"

  - id: invoice-json
    messages:
      - role: user
        content: "帮我查一下订单 A1024 的发票"
    assertions:
      - is_json: true
      - json_schema:
          type: object
          required: [order_id, invoice_status]
"""
