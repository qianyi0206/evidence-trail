"""Regulation Evidence Harness — agent layer over LightRAG retrieval assets.

Public entry:
    from reg_harness import build_stack
    stack = build_stack()
    state = stack.ask("...")
"""

from reg_harness.runtime import HarnessStack, build_stack
from reg_harness.loop import RegulationHarness
from reg_harness.intent import IntentResult, resolve_intent

__version__ = "0.2.0"

__all__ = [
    "HarnessStack",
    "build_stack",
    "RegulationHarness",
    "IntentResult",
    "resolve_intent",
    "__version__",
]
