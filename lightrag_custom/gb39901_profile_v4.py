from __future__ import annotations

from gb39901_profile import (
    CONTINUE_PROMPT as BASE_CONTINUE_PROMPT,
    EXAMPLES,
    SYSTEM_PROMPT as BASE_SYSTEM_PROMPT,
    USER_PROMPT as BASE_USER_PROMPT,
)
from schema_guard import relation_contract_text


RELATION_CONTRACT = r"""
---Relation Endpoint Contract (hard whitelist)---
关系只有在 source entity type、RELATION_TYPE、target entity type 与下列某一行完全匹配时才允许输出：
{relation_contract}

端点约束规则：
1. 必须先确定关系两端实体类型，再选择关系；禁止只按自然语言相似性选择关键词。
2. 若当前方向不匹配但反方向匹配，交换 source/target；不得保留错误方向。
3. 若没有任何匹配关系，跳过该边；不得为了连图而创造边。
4. Clause -> Threshold 只能使用 SPECIFIES，不得使用 HAS_THRESHOLD。
5. Requirement -> TestScenario/VerificationActivity 只能使用 VERIFIED_BY，不得使用 APPLIES_TO 或 SPECIFIES。
6. Requirement -> DocumentationArtifact 使用 REQUIRES_DOCUMENT。
7. VerificationActivity -> DocumentationArtifact 使用 PRODUCES。
8. Requirement -> Organization、Requirement -> CredibilityCriterion、Threshold -> Parameter、SafetyGoal -> SystemFunction 在本 Schema 中没有允许关系，必须跳过。
9. HAS_THRESHOLD 的 source 只能是 Requirement/Metric/AcceptanceCriterion/CredibilityCriterion/Condition/TestScenario，target 只能是 Threshold。
10. APPLIES_TO 的 target 只能是 VehicleCategory/System/SystemFunction/SimulationToolchain/LoadState。
""".format(relation_contract=relation_contract_text())


SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.replace(
    "---Extraction Rules---",
    RELATION_CONTRACT + "\n---Extraction Rules---",
)

USER_PROMPT = BASE_USER_PROMPT.replace(
    "5. 只输出规定格式，不输出解释或 Markdown 围栏。",
    "5. 每条关系必须通过 Relation Endpoint Contract 的 source/type/target 白名单。\n"
    "6. 没有合法关系时跳过该边，禁止输出不合规关系。\n"
    "7. 只输出规定格式，不输出解释或 Markdown 围栏。",
)

CONTINUE_PROMPT = BASE_CONTINUE_PROMPT.replace(
    "不要重复已经正确输出的内容，不得引入当前文本没有的事实。",
    "不要重复已经正确输出的内容，不得引入当前文本没有的事实。"
    "补充关系前必须再次核对 Relation Endpoint Contract；端点不合法的关系不得输出。",
)
