from __future__ import annotations

import os


if os.getenv("GB39901_PROMPT_ENABLED", "false").lower() in {"1", "true", "yes"}:
    if os.getenv("GB39901_RELATION_PROMPT_V4", "false").lower() in {"1", "true", "yes"}:
        from gb39901_profile_v4 import CONTINUE_PROMPT, EXAMPLES, SYSTEM_PROMPT, USER_PROMPT
    else:
        from gb39901_profile import CONTINUE_PROMPT, EXAMPLES, SYSTEM_PROMPT, USER_PROMPT
    from lightrag.prompt import PROMPTS

    PROMPTS["entity_extraction_system_prompt"] = SYSTEM_PROMPT
    PROMPTS["entity_extraction_user_prompt"] = USER_PROMPT
    PROMPTS["entity_continue_extraction_user_prompt"] = CONTINUE_PROMPT
    PROMPTS["entity_extraction_examples"] = EXAMPLES
    PROMPTS["gb39901_profile_active"] = True

if os.getenv("GB39901_SCHEMA_GUARD_ENABLED", "false").lower() in {"1", "true", "yes"}:
    from schema_guard import install_schema_guard

    install_schema_guard()
