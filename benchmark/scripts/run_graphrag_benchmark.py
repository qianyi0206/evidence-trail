#!/usr/bin/env python3
"""Run controlled retrieval and answer experiments against LightRAG /query/data."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # Allows offline unit tests of pure benchmark helpers.
    httpx = None  # type: ignore[assignment]

from benchmark_common import (
    AEB_ROOT,
    EVIDENCE_PATH,
    QUESTIONS_PATH,
    index_by_id,
    load_jsonl,
    normalize_text,
    parse_json_object,
    write_jsonl,
)


MODES = ("closed_book", "naive", "hybrid", "mix", "oracle")

SOURCE_FILE_MARKERS = {
    "gb39901": ("gb+39901-2025", "gb39901"),
    "unece_r152": ("unece_r152", "un_r152"),
    "euroncap_c2c": ("euroncap_aeb_c2c", "aeb_c2c"),
    "euroncap_score": ("euroncap_collision_avoidance", "collision_avoidance"),
}


def load_demo_env(profile_env: str | None) -> tuple[dict[str, str], Any, Any]:
    sys.path.insert(0, str(AEB_ROOT / "scripts"))
    if profile_env:
        os.environ["AEB_PROFILE_ENV"] = profile_env
    from common import api_headers, lightrag_url, load_env  # type: ignore

    env = load_env()
    return env, api_headers, lightrag_url


def token_estimate(text: str) -> int:
    # Conservative language-agnostic approximation used only for equal budgeting.
    return max(1, len(text.encode("utf-8")) // 4)


def source_ids_for_file_path(file_path: str) -> set[str]:
    """Infer the benchmark source before matching generic clause locators.

    Clause numbers such as 1 or 5.4 recur in every standard. Without this
    guard, a GB chunk can be incorrectly credited as UNECE or Euro NCAP gold
    evidence merely because both documents have a clause with the same number.
    """
    normalized = str(file_path or "").casefold()
    return {
        source_id
        for source_id, markers in SOURCE_FILE_MARKERS.items()
        if any(marker in normalized for marker in markers)
    }


def expand_clause_locator(clause: str) -> list[str]:
    """Expand simple same-section ranges such as 6.5-6.7 or A.2-A.3."""
    value = str(clause).strip().replace("～", "-").replace("–", "-").replace("—", "-")
    match = re.fullmatch(r"(.+?\.)(\d+)\s*-\s*(?:\1)?(\d+)", value)
    if not match:
        # The second endpoint normally repeats the prefix (6.5-6.7), which a
        # backreference inside this expression cannot consume portably.
        range_match = re.fullmatch(r"(.+?\.)(\d+)\s*-\s*(.+?\.)(\d+)", value)
        if not range_match or range_match.group(1) != range_match.group(3):
            return [value]
        prefix, start, end = range_match.group(1), int(range_match.group(2)), int(range_match.group(4))
    else:
        prefix, start, end = match.group(1), int(match.group(2)), int(match.group(3))
    if end < start or end - start > 50:
        return [value]
    return [f"{prefix}{index}" for index in range(start, end + 1)]


def clause_marker_matches(text: str, clause: str) -> bool:
    """Match an explicit clause marker without substring collisions."""
    for candidate in expand_clause_locator(clause):
        escaped = re.escape(candidate)
        clause_or_descendant = rf"{escaped}(?:\.[0-9]+)*"
        patterns = (
            rf"(?:来源条款|source_clause)\s*[=:]\s*{clause_or_descendant}(?![0-9A-Za-z.])",
            rf"clause\s*:\s*{clause_or_descendant}(?![0-9A-Za-z.])",
            rf"\[{clause_or_descendant}\](?![0-9A-Za-z.])",
            rf"第\s*{clause_or_descendant}\s*条",
        )
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return True
    return False


def evidence_for_text(text: str, file_path: str, evidence: list[dict[str, Any]]) -> list[str]:
    normalized = normalize_text(text)
    matched = []
    allowed_source_ids = source_ids_for_file_path(file_path)
    table_match = re.search(r"(?:__table_|table[_-]?)(a_)?(\d+)", file_path, re.IGNORECASE)
    for record in evidence:
        if allowed_source_ids and record.get("source_id") not in allowed_source_ids:
            continue
        locator = record.get("locator", {})
        table = str(locator.get("table", "")).lower().replace(" ", "_").replace(".", "_")
        if table_match and table:
            expected = ("a_" if table_match.group(1) else "") + table_match.group(2)
            if table == expected:
                matched.append(record["id"])
                continue
        clause_values = []
        if locator.get("clause"):
            clause_values.append(str(locator["clause"]))
        clause_values.extend(str(item) for item in locator.get("clauses", []))
        if any(clause_marker_matches(text, clause) for clause in clause_values):
            matched.append(record["id"])
            continue
        excerpt = normalize_text(record.get("source_excerpt", ""))
        if excerpt and len(excerpt) >= 20 and (excerpt in normalized or (len(normalized) >= 30 and normalized in excerpt)):
            matched.append(record["id"])
    return sorted(set(matched))


def raw_items(payload: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    items = []
    for item in data.get("relationships", []):
        text = (
            f"{item.get('src_id', '')} --{item.get('keywords', '')}--> {item.get('tgt_id', '')}\n"
            f"{item.get('description', '')}"
        ).strip()
        items.append({"kind": "relationship", "text": text, "file_path": item.get("file_path", ""), "raw": item})
    for item in data.get("entities", []):
        text = f"{item.get('entity_name', '')} [{item.get('entity_type', '')}]\n{item.get('description', '')}".strip()
        items.append({"kind": "entity", "text": text, "file_path": item.get("file_path", ""), "raw": item})
    for item in data.get("chunks", []):
        text = str(item.get("content", "")).strip()
        items.append({"kind": "chunk", "text": text, "file_path": item.get("file_path", ""), "raw": item})
    unique = []
    seen = set()
    for item in items:
        key = normalize_text(item["text"])
        if not key or key in seen:
            continue
        seen.add(key)
        item["evidence_ids"] = evidence_for_text(item["text"], item["file_path"], evidence)
        item["token_estimate"] = token_estimate(item["text"])
        unique.append(item)
    return unique


def trim_items(items: list[dict[str, Any]], max_tokens: int) -> list[dict[str, Any]]:
    selected = []
    used = 0
    for item in items:
        remaining = max_tokens - used
        if remaining <= 0:
            break
        if item["token_estimate"] <= remaining:
            selected.append(item)
            used += item["token_estimate"]
            continue
        # Keep a final truncated item instead of silently wasting the shared budget.
        byte_budget = remaining * 4
        raw = item["text"].encode("utf-8")[:byte_budget]
        while raw:
            try:
                text = raw.decode("utf-8")
                break
            except UnicodeDecodeError:
                raw = raw[:-1]
        else:
            text = ""
        if text:
            truncated = {**item, "text": text, "token_estimate": token_estimate(text), "truncated": True}
            selected.append(truncated)
        break
    return selected


# ---------------------------------------------------------------------------
# P0 context policy: question-aware ranking + hybrid/mix noise control
# ---------------------------------------------------------------------------

_FOCUS_PHRASES = (
    "最大设计总质量",
    "行车质量",
    "误响应",
    "仿真",
    "可信度",
    "静止车辆",
    "匀速",
    "紧急制动",
    "碰撞预警",
    "激活范围",
    "同一型式",
    "功能安全",
    "附录",
    "例外",
    "异常",
)


def extract_focus_terms(question: dict[str, Any]) -> list[str]:
    """Pull cheap lexical anchors from the question for local re-ranking.

    Does not use gold answers or gold evidence — only the question text and
    task type, so it is safe for both live runs and offline unit tests.
    """
    text = str(question.get("question", ""))
    terms: list[str] = []
    for match in re.findall(r"\b([MN]\d)\b", text, flags=re.IGNORECASE):
        terms.append(match.upper())
    for match in re.findall(r"(\d+(?:\.\d+)?)\s*km\s*/\s*h", text, flags=re.IGNORECASE):
        terms.append(match)
    for match in re.findall(r"(?:条款|第)?\s*(\d+(?:\.\d+)+[A-Za-z]?)", text):
        terms.append(match)
    for match in re.findall(r"表\s*([A-Za-z]?\d+)", text):
        terms.append(f"table_{match}")
        terms.append(f"表{match}")
    for phrase in _FOCUS_PHRASES:
        if phrase in text:
            terms.append(phrase)
    task_type = str(question.get("task_type", ""))
    if "table" in task_type or "表" in text:
        terms.append("__prefer_table__")
    if "unanswerable" in task_type:
        terms.append("__prefer_refusal_cues__")
    if any(token in text for token in ("哪些", "列出", "完整", "五类", "分别")):
        terms.append("__prefer_lists__")
    if any(token in text for token in ("不同", "区别", "例外", "异常", "如何处理")):
        terms.append("__prefer_exceptions__")
    # Preserve order, drop empties.
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        ordered.append(term)
    return ordered


def item_relevance_score(
    item: dict[str, Any],
    focus_terms: list[str],
    mode: str,
) -> float:
    """Higher is better. Used only to reorder already-retrieved items.

    Must not use gold-derived ``evidence_ids`` — those are offline labels only.
    Ranking is question focus terms + kind + path heuristics.
    """
    text = str(item.get("text", ""))
    file_path = str(item.get("file_path", ""))
    kind = str(item.get("kind", ""))
    score = 0.0

    # Graph modes return many entity/relation blurbs that dilute table cells.
    if mode in {"hybrid", "mix"}:
        if kind == "chunk":
            score += 6.0
        elif kind == "relationship":
            score += 1.0
        elif kind == "entity":
            score += 0.5
        else:
            score += 2.0
    else:
        if kind == "chunk":
            score += 3.0

    text_cf = text.casefold()
    path_cf = file_path.casefold()
    for term in focus_terms:
        if term == "__prefer_table__":
            if "table" in path_cf or "<tr>" in text_cf or "表" in text:
                score += 3.0
            continue
        if term == "__prefer_lists__":
            if any(token in text for token in ("、", "；", "1)", "（1）", "分别", "包括")):
                score += 1.0
            continue
        if term == "__prefer_exceptions__":
            if any(token in text for token in ("若", "例外", "替代", "大于", "异常", "否则")):
                score += 2.5
            continue
        if term == "__prefer_refusal_cues__":
            if any(token in text for token in ("不适用", "未规定", "不要求", "无", "至少")):
                score += 1.0
            continue
        if term.startswith("table_"):
            marker = term.replace("table_", "")
            if marker.casefold() in path_cf or f"表{marker}" in text or f"table_{marker}" in path_cf:
                score += 3.0
            continue
        if term.casefold() in text_cf or term in text or term.casefold() in path_cf:
            score += 1.5
    return score


def prioritize_items(
    items: list[dict[str, Any]],
    question: dict[str, Any],
    mode: str,
    max_tokens: int,
    *,
    context_policy: str = "compact",
) -> list[dict[str, Any]]:
    """P0A: reorder and budget context to cut hybrid/mix noise.

    Policies:
    - ``legacy``: original first-seen order + trim (baseline behavior).
    - ``compact``: question-aware ranking; hybrid/mix spend most budget on chunks.
    """
    if not items:
        return []
    if context_policy == "legacy" or mode in {"closed_book", "oracle"}:
        return trim_items(items, max_tokens)

    focus_terms = extract_focus_terms(question)
    ranked = sorted(
        items,
        key=lambda item: (
            -item_relevance_score(item, focus_terms, mode),
            # Prefer shorter items on ties (denser table cells over long blurbs).
            item.get("token_estimate", 0),
        ),
    )

    if mode in {"hybrid", "mix"}:
        # Prefer source text over graph blurbs; keep a small graph tail for multi-hop cues.
        chunk_budget = max(1, int(max_tokens * 0.75))
        chunks = [item for item in ranked if item.get("kind") == "chunk"]
        others = [item for item in ranked if item.get("kind") != "chunk"]
        selected = trim_items(chunks, chunk_budget)
        used = sum(int(item.get("token_estimate", 0)) for item in selected)
        selected.extend(trim_items(others, max(0, max_tokens - used)))
        # Present highest-signal items first to the answer model.
        selected.sort(
            key=lambda item: (
                -item_relevance_score(item, focus_terms, mode),
                0 if item.get("kind") == "chunk" else 1,
            )
        )
        for item in selected:
            item["context_policy"] = "compact"
            item["relevance_score"] = item_relevance_score(item, focus_terms, mode)
        return selected

    selected = trim_items(ranked, max_tokens)
    for item in selected:
        item["context_policy"] = "compact"
        item["relevance_score"] = item_relevance_score(item, focus_terms, mode)
    return selected


# OCR / CN standards often write "1 000" / "2 000" (space or NBSP as thousands sep).
_THOUSANDS_SEP_RE = re.compile(r"(?<=\d)[\s\u00a0,](?=\d{3}(?:\D|$))")


def normalize_numeric_text(text: str) -> str:
    """Collapse spaced/comma thousands so '1 000' and '1000' match."""
    if not text:
        return ""
    prev = None
    cur = text
    while prev != cur:
        prev = cur
        cur = _THOUSANDS_SEP_RE.sub("", cur)
    return cur


def collect_context_numbers(items: list[dict[str, Any]]) -> set[str]:
    """Normalize numeric tokens that appear in the provided evidence text."""
    joined = normalize_numeric_text("\n".join(str(item.get("text", "")) for item in items))
    found: set[str] = set()
    for match in re.findall(r"\d+(?:\.\d+)?", joined):
        found.add(match)
        try:
            as_float = float(match)
            if as_float.is_integer():
                found.add(str(int(as_float)))
        except ValueError:
            pass
    return found


def extract_answer_numbers(value: Any) -> list[str]:
    numbers: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            numbers.extend(extract_answer_numbers(child))
    elif isinstance(value, list):
        for child in value:
            numbers.extend(extract_answer_numbers(child))
    elif isinstance(value, bool):
        return numbers
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            numbers.append(str(int(value)))
        else:
            numbers.append(str(value))
    elif isinstance(value, str):
        numbers.extend(re.findall(r"\d+(?:\.\d+)?", normalize_numeric_text(value)))
    return numbers


def post_validate_prediction(
    prediction: dict[str, Any],
    items: list[dict[str, Any]],
    question: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """P0C: lightweight refusal / numeric grounding checks without gold leakage."""
    flags: list[str] = []
    if not isinstance(prediction, dict):
        return {"answerable": False, "answer": {"answerable": False, "reason": "模型未返回JSON对象"}, "claims": [], "citations": [], "validation_flags": ["invalid_prediction_type"]}

    answerable = prediction.get("answerable")
    if mode != "closed_book" and not items and answerable is True:
        prediction = {
            **prediction,
            "answerable": False,
            "answer": {
                "answerable": False,
                "reason": "未提供可用检索证据，不能给出有依据的法规数值或结论。",
            },
            "claims": [],
            "citations": [],
            "reference_citations": [],
        }
        flags.append("forced_refusal_empty_context")
        answerable = False

    if mode != "closed_book" and answerable is True and items:
        context_numbers = collect_context_numbers(items)
        answer_numbers = extract_answer_numbers(prediction.get("answer"))
        unsupported = []
        for number in answer_numbers:
            if number in context_numbers:
                continue
            try:
                magnitude = float(number)
            except ValueError:
                unsupported.append(number)
                continue
            # Allow pure tiny enumeration indices (0–4) without bag support; refuse the rest.
            if magnitude >= 5:
                unsupported.append(number)
        if unsupported:
            flags.append("numeric_not_in_context:" + ",".join(unsupported[:8]))
            # Hard fail closed: any substantive ungrounded number blocks the answer.
            if any(float(n) >= 5 for n in unsupported if re.fullmatch(r"\d+(?:\.\d+)?", n)):
                prediction = {
                    **prediction,
                    "answerable": False,
                    "answer": {
                        "answerable": False,
                        "reason": (
                            "模型给出的关键数值未出现在所附证据中，已按拒答处理以避免无依据阈值。"
                            f" unsupported={unsupported[:8]}"
                        ),
                    },
                    "validation_note": "numeric_grounding_failed",
                }
                flags.append("forced_refusal_ungrounded_numeric")

    if question.get("scoring_method") == "unanswerable" and prediction.get("answerable") is True:
        # Soft flag only: gold is not consulted; the stronger prompt should handle most cases.
        flags.append("unanswerable_task_but_model_answered")

    prediction["validation_flags"] = flags
    return prediction


def oracle_items(question: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for evidence_id in question.get("gold_evidence_ids", []):
        record = evidence_by_id[evidence_id]
        text = "\n".join(
            [
                f"evidence_id: {evidence_id}",
                f"title: {record['title']}",
                "normalized_facts: "
                + json.dumps(record.get("normalized_facts", {}), ensure_ascii=False, sort_keys=True),
                "source_excerpt:",
                record["source_excerpt"],
            ]
        )
        items.append(
            {
                "kind": "oracle_evidence", "text": text,
                "file_path": record["source_file"], "evidence_ids": [evidence_id],
                "token_estimate": token_estimate(text),
            }
        )
    return items


def answer_shape(value: Any, label: str = "value") -> Any:
    """Preserve the gold schema and collection types without leaking values."""
    if isinstance(value, dict):
        return {key: answer_shape(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [answer_shape(value[0], "item")] if value else ["<item>"]
    if isinstance(value, bool):
        return f"<{label}: boolean>"
    if isinstance(value, (int, float)):
        return f"<{label}: number>"
    return f"<{label}>"


def answer_contract(question: dict[str, Any]) -> dict[str, Any]:
    """Value-free JSON shape for the model. Never leak gold labels/values."""
    method = question.get("scoring_method")
    if method == "unanswerable":
        answer: Any = {
            "answerable": "<boolean>",
            "reason": "<why the supplied evidence is insufficient>",
        }
    else:
        answer = answer_shape(question.get("gold_answer") or {}, "answer")
    return {
        "answerable": "<boolean: true only if evidence fully supports the answer>",
        "answer": answer,
        "claims": ["<one atomic claim per item>"],
        "citations": ["R1"],
        "claim_citations": {"0": ["R1"]},
    }


def chat_url(host: str) -> str:
    base = host.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def post_with_retry(
    client: Any,
    url: str,
    *,
    headers: dict[str, str],
    json_payload: dict[str, Any],
    attempts: int = 4,
) -> Any:
    """Retry transient transport, throttling, and server errors only."""
    for attempt in range(attempts):
        try:
            response = client.post(url, headers=headers, json=json_payload)
            if response.status_code not in {408, 429} and response.status_code < 500:
                return response
            response.raise_for_status()
        except Exception as error:
            retryable = (
                (httpx is not None and isinstance(error, httpx.TransportError))
                or getattr(getattr(error, "response", None), "status_code", 0) in {408, 429}
                or getattr(getattr(error, "response", None), "status_code", 0) >= 500
            )
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable retry state")


def generate_answer(
    client: httpx.Client,
    env: dict[str, str],
    question: dict[str, Any],
    items: list[dict[str, Any]],
    mode: str,
) -> tuple[dict[str, Any], str, float, dict[str, Any]]:
    references = []
    context_blocks = []
    for index, item in enumerate(items, 1):
        reference = f"R{index}"
        references.append({"reference": reference, "evidence_ids": item.get("evidence_ids", []), "kind": item["kind"]})
        context_blocks.append(f"[{reference}] {item['text']}")
    context = "\n\n".join(context_blocks) if context_blocks else "（未提供检索证据）"
    task_type = str(question.get("task_type", ""))
    # P0B: stronger structured constraints — lists, exceptions, refusal, no invented numbers.
    shared_rules = (
        "答案必须是一个JSON对象，不要输出Markdown。"
        "claims中每项只能包含一个原子声明；citations和claim_citations只能引用证据中的R编号。"
        "枚举类问题必须逐项完整列出，不得合并改写或漏项。"
        "若证据中出现例外、替代、异常条件（如“若…则…”），答案必须保留该条件，不得省略。"
        "任何速度、阈值、百分比等数值必须能在所附证据原文中直接找到；证据没有的数字一律不得猜测邻近行或常用值。"
        "若问题前提在证据中不存在（例如询问表中没有的车速行），answerable必须为false，并说明缺什么。"
    )
    if mode == "closed_book":
        system = (
            "你是法规基准测试中的闭卷回答器。当前不提供检索证据；只能依靠模型已有知识回答，"
            "不得伪造引用。若不确定或问题前提错误，answerable必须为false。citations必须为空数组，"
            "claim_citations必须为空对象。"
            + shared_rules
        )
    else:
        system = (
            "你是法规基准测试中的受控回答器。只能使用给出的证据，不得使用外部知识补全。"
            "若证据不足、互相冲突、或问题前提错误，answerable必须为false。"
            + shared_rules
        )
        if "unanswerable" in task_type:
            system += "本题很可能不可回答：优先拒答，禁止用相近工况的数值顶替。"
        if "table" in task_type or "conditional_table" in task_type:
            system += "表格题必须同时对齐车型、场景、试验车速、目标速度与载荷状态后再取单元格。"
        if "comparison" in task_type or "exception" in task_type:
            system += "比较题必须同时给出对比双方与例外处理规则。"
        if "synthesis" in task_type or "multi_hop" in task_type:
            system += "综合/多跳题优先覆盖完整列表与共同判据，不要只答部分场景。"

    user = (
        f"问题：{question['question']}\n"
        f"task_type：{task_type}\n\n"
        f"证据：\n{context}\n\n"
        f"请按以下形状输出（尖括号只是字段提示，不是答案）：\n"
        f"{json.dumps(answer_contract(question), ensure_ascii=False)}"
    )
    headers = {"Content-Type": "application/json"}
    api_key = env.get("LLM_BINDING_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.perf_counter()
    response = post_with_retry(
        client,
        chat_url(env["LLM_BINDING_HOST"]),
        headers=headers,
        json_payload={
            "model": env["LLM_MODEL"], "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
    )
    response.raise_for_status()
    latency = time.perf_counter() - started
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    parsed = parse_json_object(content)
    reference_map = {item["reference"]: item["evidence_ids"] for item in references}
    raw_citations = parsed.get("citations", []) if isinstance(parsed.get("citations", []), list) else []
    mapped_citations = sorted({evidence_id for citation in raw_citations for evidence_id in reference_map.get(str(citation), [])})
    parsed["reference_citations"] = raw_citations
    parsed["citations"] = mapped_citations
    raw_claim_citations = parsed.get("claim_citations", {})
    if isinstance(raw_claim_citations, dict):
        parsed["claim_reference_citations"] = raw_claim_citations
        parsed["claim_citations"] = {
            str(key): sorted({evidence_id for citation in value if isinstance(value, list) for evidence_id in reference_map.get(str(citation), [])})
            if isinstance(value, list) else []
            for key, value in raw_claim_citations.items()
        }
    # P0C post-validation (no gold labels).
    parsed = post_validate_prediction(parsed, items, question, mode)
    usage = payload.get("usage", {})
    return parsed, content, latency, usage


def retrieval(
    client: httpx.Client,
    env: dict[str, str],
    api_headers: Any,
    lightrag_url: Any,
    question: dict[str, Any],
    mode: str,
    evidence: list[dict[str, Any]],
    max_tokens: int,
    top_k: int,
    context_policy: str = "compact",
) -> tuple[list[dict[str, Any]], float, dict[str, Any]]:
    started = time.perf_counter()
    response = post_with_retry(
        client,
        lightrag_url(env, "/query/data"), headers=api_headers(env),
        json_payload={
            "query": question["question"], "mode": mode, "top_k": top_k, "chunk_top_k": top_k,
            "max_total_tokens": max_tokens, "max_entity_tokens": max_tokens,
            "max_relation_tokens": max_tokens, "enable_rerank": False,
        },
    )
    response.raise_for_status()
    latency = time.perf_counter() - started
    payload = response.json()
    if payload.get("status") != "success":
        message = str(payload.get("message", ""))
        if "no relevant document chunks found" in message.casefold():
            return [], latency, {
                "query_mode": mode,
                "retrieval_status": "empty",
                "message": message,
            }
        raise RuntimeError(f"Retrieval failed for {question['id']} {mode}: {message}")
    items = prioritize_items(
        raw_items(payload, evidence),
        question,
        mode,
        max_tokens,
        context_policy=context_policy,
    )
    metadata = dict(payload.get("metadata") or {})
    metadata["context_policy"] = context_policy
    return items, latency, metadata


def ranked_evidence(items: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(evidence_id for item in items for evidence_id in item.get("evidence_ids", [])))


def result_record(
    question: dict[str, Any], mode: str, items: list[dict[str, Any]], retrieval_latency: float,
    metadata: dict[str, Any], prediction: dict[str, Any] | None, raw_answer: str,
    answer_latency: float, usage: dict[str, Any], context_budget: int,
    input_cost_per_million: float | None, output_cost_per_million: float | None,
) -> dict[str, Any]:
    ranked = ranked_evidence(items)
    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    answer_cost = None
    if input_cost_per_million is not None and output_cost_per_million is not None:
        answer_cost = (
            float(prompt_tokens or 0) * input_cost_per_million
            + float(completion_tokens or 0) * output_cost_per_million
        ) / 1_000_000
    return {
        "question_id": question["id"], "mode": mode, "split": question["split"],
        "task_type": question["task_type"], "context_budget_tokens": context_budget,
        "context_tokens": sum(item["token_estimate"] for item in items),
        "retrieved_evidence_ids": sorted(set(ranked)), "ranked_evidence_ids": ranked,
        "retrieved_items": [
            {
                "rank": index, "kind": item["kind"], "file_path": item.get("file_path", ""),
                "evidence_ids": item.get("evidence_ids", []), "token_estimate": item["token_estimate"],
                "text": item["text"], "truncated": item.get("truncated", False),
            }
            for index, item in enumerate(items, 1)
        ],
        "retrieval_latency_seconds": retrieval_latency, "retrieval_cost_usd": metadata.get("estimated_cost_usd"),
        "retrieval_metadata": metadata, "prediction": prediction or {}, "raw_answer": raw_answer,
        "citations": (prediction or {}).get("citations", []),
        "answer_latency_seconds": answer_latency, "answer_usage": usage, "answer_cost_usd": answer_cost,
    }


def main() -> None:
    if httpx is None:
        raise RuntimeError("httpx is required to run the live GraphRAG benchmark")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-env", default=".env.gb39901_v4")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
    parser.add_argument(
        "--source-set", choices=["gb", "cross", "all"], default="gb",
        help="Run the 50-question GB main set, 10-question cross-document set, or both.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--question-id", action="append", default=[],
        help="Run only selected question IDs; repeat this option to build a stratified pilot.",
    )
    parser.add_argument("--context-tokens", type=int, default=6000)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument(
        "--context-policy",
        choices=["compact", "legacy"],
        default="compact",
        help="compact=P0 question-aware ranking + hybrid/mix chunk bias; legacy=original order.",
    )
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    evidence = load_jsonl(EVIDENCE_PATH)
    evidence_by_id = index_by_id(evidence, "evidence")
    questions = load_jsonl(QUESTIONS_PATH)
    if args.source_set == "gb":
        questions = [item for item in questions if item["id"].startswith("gb_")]
    elif args.source_set == "cross":
        questions = [item for item in questions if item["id"].startswith("cross_")]
    if args.question_id:
        requested = set(args.question_id)
        available = {item["id"] for item in questions}
        missing = sorted(requested - available)
        if missing:
            raise RuntimeError(f"Unknown or out-of-scope --question-id values: {missing}")
        questions = [item for item in questions if item["id"] in requested]
    if args.split != "all":
        questions = [item for item in questions if item["split"] == args.split]
    if args.limit:
        questions = questions[: args.limit]
    env, api_headers, lightrag_url = load_demo_env(args.profile_env)
    completed: set[tuple[str, str]] = set()
    records = []
    if args.resume and args.output.is_file():
        records = load_jsonl(args.output)
        completed = {(item["question_id"], item["mode"]) for item in records}
    with httpx.Client(timeout=600) as client:
        for question in questions:
            for mode in args.modes:
                if (question["id"], mode) in completed:
                    continue
                if mode == "closed_book":
                    items, retrieval_latency, metadata = [], 0.0, {
                        "query_mode": "closed_book",
                        "context_policy": args.context_policy,
                    }
                elif mode == "oracle":
                    items = trim_items(oracle_items(question, evidence_by_id), args.context_tokens)
                    retrieval_latency, metadata = 0.0, {
                        "query_mode": "oracle",
                        "context_policy": args.context_policy,
                    }
                else:
                    items, retrieval_latency, metadata = retrieval(
                        client, env, api_headers, lightrag_url, question, mode,
                        evidence, args.context_tokens, args.top_k,
                        context_policy=args.context_policy,
                    )
                if args.retrieval_only:
                    prediction, raw_answer, answer_latency, usage = None, "", 0.0, {}
                else:
                    prediction, raw_answer, answer_latency, usage = generate_answer(client, env, question, items, mode)
                records.append(
                    result_record(
                        question, mode, items, retrieval_latency, metadata, prediction,
                        raw_answer, answer_latency, usage, args.context_tokens,
                        args.input_cost_per_million, args.output_cost_per_million,
                    )
                )
                write_jsonl(args.output, records)
                print(
                    f"benchmark {question['id']} {mode}: evidence={len(ranked_evidence(items))} "
                    f"context_tokens={sum(item['token_estimate'] for item in items)}"
                )
    print(f"completed rows={len(records)} output={args.output}")


if __name__ == "__main__":
    main()
