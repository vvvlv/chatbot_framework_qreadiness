"""
Quantum Readiness Data Collection Tool - Layer 3.

NEW LOGIC (field-filling tool):
- A small, fixed set of field specs (key + explanation + default question).
- For each field, ask a question via interrupt().
- On resume, an LLM (mistral small) evaluates if the response is satisfactory for the field,
  rewrites it if needed, and proposes a follow-up question if not satisfactory.
- The user can skip any question (UI sends "/skip") -> we store null/"no_response".
- If the user asks for clarification, we respond with a clarification message and re-ask.

For now (testing), we only collect 4 fields and pack them into a step_data shape
that remains compatible with the current analyzer/presenter pipeline.
"""

import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from core.model_gateway import ModelGateway
from core.protocols import ToolProtocol
from core.state import ToolState


class FieldSpec(TypedDict):
    key: str
    explanation: str
    default_question: str
    answer_criteria: str
    example_answers: List[str]


class QuantumDataCollectorState(ToolState, total=False):
    """State for the field-filling collector."""

    tool_started: bool

    # Field filling
    field_values: Dict[str, Optional[str]]  # key -> rewritten value or None (skipped)
    field_raw_values: Dict[str, Optional[str]]  # key -> raw user answer
    field_status: Dict[str, str]  # key -> "filled" | "skipped"
    current_field_key: Optional[str]
    pending_question: Optional[str]  # current question to ask for current_field_key
    retry_count: int

    # Audit
    questions_asked: List[Dict[str, Any]]
    answers_received: List[Dict[str, Any]]


class QuantumDataCollectorTool(ToolProtocol):
    """
    Data Collection Tool for Quantum Readiness assessment.
    
    Collects information through three phases:
    1. Onboarding (industry, interest driver)
    2. Cryptographic Risk Assessment (4 dimensions)
    3. Quantum Opportunity Assessment (4 dimensions)
    
    Uses interrupt() for each question to suspend execution and wait for user response.
    """
    
    name = "quantum_data_collector"
    # Use a stronger model for validation + rewriting to reduce loops.
    VALIDATOR_MODEL = "mistral/mistral-medium-latest"
    # For testing: keep it small (3–4 fields).
    FIELD_SPECS: List[FieldSpec] = [
        {
            "key": "user_industry",
            "explanation": "The primary industry/sector the organization operates in (e.g., healthcare, finance, manufacturing).",
            "default_question": "What industry does your organization operate in? (e.g., healthcare, finance, manufacturing)",
            "answer_criteria": "A short industry label (1–4 words). Avoid describing your job role; focus on the org’s sector.",
            "example_answers": ["Healthcare provider", "Retail banking", "Manufacturing (automotive)"],
        },
        {
            "key": "data_sensitivity",
            "explanation": "Describe what sensitive data you protect and how long it needs to remain confidential (include retention/confidentiality timeframes if known).",
            "default_question": "List 1–2 sensitive data types you protect and the confidentiality timeframe for each (if known).",
            "answer_criteria": "Mention at least one sensitive data type AND a timeframe (or say 'unknown'). Prefer concrete numbers (years/months).",
            "example_answers": [
                "Patient records (10+ years), payment card data (2 years).",
                "Customer PII (unknown), contracts (7 years).",
            ],
        },
        {
            "key": "crypto_visibility",
            "explanation": "Describe whether you have an inventory of cryptographic usage (where encryption/keys/PKI/TLS are used) across systems and vendors.",
            "default_question": "Do you have a cryptography inventory? If yes: what’s covered (TLS, PKI, KMS, apps) and when was it last updated?",
            "answer_criteria": "State whether you have an inventory (yes/no/partial) AND what scope it covers (at least one area).",
            "example_answers": [
                "Partial: TLS endpoints documented; KMS/3rd-party SaaS encryption not fully tracked; last reviewed Q4 2025.",
                "Yes: full inventory across apps, databases, KMS, and PKI; updated monthly.",
            ],
        },
        {
            "key": "migration_progress",
            "explanation": "Describe your current progress toward post-quantum cryptography (PQC): not started, planning, pilot, or production rollout.",
            "default_question": "What’s your PQC status today (not started / planning / pilot / production) and what’s the next concrete step + target date?",
            "answer_criteria": "Include a current status label and one concrete next step (or explicitly say there is no plan).",
            "example_answers": [
                "Planning: evaluating Kyber/Dilithium for TLS in 2026; no pilots yet.",
                "Not started: no roadmap; will revisit after vendor support improves.",
            ],
        },
    ]
    
    def __init__(self, model_gateway: ModelGateway):
        self._model_gateway = model_gateway
    
    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."
    
    def build(self):
        """Build the field-filling collector tool graph."""

        total_steps = len(self.FIELD_SPECS)
        max_retries_per_field = 5

        def _spec_for(key: str) -> FieldSpec:
            for s in self.FIELD_SPECS:
                if s["key"] == key:
                    return s
            raise KeyError(key)

        def _is_skip(text: str) -> bool:
            v = (text or "").strip().lower()
            return v in {"/skip", "skip", "skip this", "no response"}

        def _looks_like_clarification_request(text: str) -> bool:
            v = (text or "").strip().lower()
            markers = (
                "/clarify",
                "clarify",
                "what do you mean",
                "can you explain",
                "explain the question",
                "i don't understand",
                "i dont understand",
                "what counts as",
                "what should i answer",
            )
            return any(m in v for m in markers)

        async def _evaluate_and_rewrite(
            *,
            field: FieldSpec,
            question: str,
            user_answer: str,
        ) -> Dict[str, Any]:
            """
            Ask the LLM to judge satisfaction + rewrite + propose next question.
            Must return JSON with keys:
              ok: bool
              rewritten: str | null
              follow_up_question: str | null
              reason: str | null
            """
            extra_rules = ""
            if field["key"] == "migration_progress":
                extra_rules = """

Extra rules for this field:
- Normalize the answer into ONE of these canonical labels: not_started | planning | pilot | production
- If the user mentions both current state and a future plan (e.g., "not started yet but planning 2026"), that is STILL satisfactory.
- In that case, prefer the label that reflects the current program state (usually planning if they have a concrete plan; otherwise not_started)."""

            prompt = f"""You are validating whether a user's answer satisfies a specific structured field.

Field key: {field['key']}
Field explanation: {field['explanation']}
What a good answer looks like: {field.get('answer_criteria','')}
Example answers:
{chr(10).join(f"- {ex}" for ex in (field.get('example_answers') or [])[:3])}
Question asked: {question}
User answer: {user_answer}
{extra_rules}

Decide if the answer is satisfactory for filling this field. If satisfactory, rewrite the answer into a concise, unambiguous value suitable for storage.
If not satisfactory, propose ONE follow-up question that will most likely elicit the missing information.

Output STRICT JSON with this schema:
{{
  "ok": true|false,
  "rewritten": "string or null",
  "follow_up_question": "string or null",
  "reason": "string or null"
}}

Rules:
- If ok=true, rewritten MUST be non-empty and <= 240 characters.
- If ok=false, follow_up_question MUST be non-empty and conversational.
- Do not include markdown, code fences, or extra keys."""

            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.VALIDATOR_MODEL,
                temperature=0.2,
            )
            text = (raw or "").strip()
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                data = json.loads(text[start:end])
                return {
                    "ok": bool(data.get("ok")),
                    "rewritten": (data.get("rewritten") or None),
                    "follow_up_question": (data.get("follow_up_question") or None),
                    "reason": (data.get("reason") or None),
                }
            except Exception:
                # Fail-safe: treat as not ok and ask a generic follow-up.
                return {
                    "ok": False,
                    "rewritten": None,
                    "follow_up_question": f"Could you provide a bit more detail? {field['default_question']}",
                    "reason": "Could not parse validator output.",
                }

        async def _build_clarification_message(field: FieldSpec) -> str:
            prompt = f"""The user asked for clarification.

Field: {field['key']}
Explanation: {field['explanation']}
Default question: {field['default_question']}
What a good answer looks like: {field.get('answer_criteria','')}
Example answers:
{chr(10).join(f"- {ex}" for ex in (field.get('example_answers') or [])[:2])}

Write a short clarification (1-3 sentences) with one example answer, then re-ask the default question.
Return ONLY the message text."""
            try:
                msg = await self._model_gateway.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.VALIDATOR_MODEL,
                    temperature=0.2,
                )
                text = (msg or "").strip()
                # Remove accidental markdown emphasis that models sometimes add.
                text = text.replace("**", "").strip()
                return text or (field["explanation"] + "\n\n" + field["default_question"])
            except Exception:
                return field["explanation"] + "\n\n" + field["default_question"]

        def _next_unfilled_key(state: QuantumDataCollectorState) -> Optional[str]:
            values = state.get("field_values", {}) or {}
            for spec in self.FIELD_SPECS:
                if spec["key"] not in values:
                    return spec["key"]
            return None

        async def _generate_initial_question(
            *,
            field: FieldSpec,
            collected: Dict[str, Optional[str]],
        ) -> str:
            """
            Generate a more concrete first question (still adaptive) using the LLM.
            Falls back to field['default_question'].
            """
            prompt = f"""You are collecting structured assessment fields.

Field key: {field['key']}
Field explanation: {field['explanation']}
What a good answer looks like: {field.get('answer_criteria','')}
Example answers:
{chr(10).join(f"- {ex}" for ex in (field.get('example_answers') or [])[:3])}

Already collected (may be partial):
{json.dumps(collected, ensure_ascii=False)}

Task: Ask ONE concrete, specific question to fill this field.
Rules:
- Ask for specific details (timeframes, scope, status) when applicable.
- Keep it to 1–2 sentences.
- Include an optional parenthetical hint like "(e.g., ...)" if helpful.
- Return ONLY the question text."""
            try:
                resp = await self._model_gateway.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.VALIDATOR_MODEL,
                    temperature=0.2,
                )
                q = (resp or "").strip().replace("**", "").strip()
                if q:
                    return q
            except Exception:
                pass
            return field["default_question"]

        async def step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            # defaults
            state.setdefault("tool_started", False)
            state.setdefault("field_values", {})
            state.setdefault("field_raw_values", {})
            state.setdefault("field_status", {})
            state.setdefault("current_field_key", None)
            state.setdefault("pending_question", None)
            state.setdefault("retry_count", 0)
            state.setdefault("questions_asked", [])
            state.setdefault("answers_received", [])
            state.setdefault("is_complete", False)

            if not state["tool_started"]:
                await adispatch_custom_event(
                    "tool_start",
                    {
                        "tool_name": self.name,
                        "total_steps": total_steps,
                        "fields": self.FIELD_SPECS,
                        "skip_command": "/skip",
                        "clarify_command": "/clarify",
                    },
                )
                state["tool_started"] = True
                state["tool_status"] = "running"

            if state.get("is_complete"):
                return state

            # pick active field
            field_key = state.get("current_field_key") or _next_unfilled_key(state)
            if field_key is None:
                # Build pipeline-compatible output (minimal).
                collected = state.get("field_values", {})
                crypto_risk_dimensions: Dict[str, Dict[str, Any]] = {}
                for dim in ("data_sensitivity", "crypto_visibility", "migration_progress"):
                    v = collected.get(dim)
                    if v is None:
                        crypto_risk_dimensions[dim] = {"score": 50, "confidence": "low", "details": "No response"}
                    else:
                        crypto_risk_dimensions[dim] = {"score": 50, "confidence": "medium", "details": v}

                state["step_data"] = {
                    "user_industry": collected.get("user_industry"),
                    "crypto_risk_dimensions": crypto_risk_dimensions,
                    "quantum_opportunity_dimensions": {},
                    "fields": collected,
                }
                state["tool_status"] = "done"
                state["tool_output"] = {"step_data": state["step_data"], "is_complete": True}
                state["is_complete"] = True
                await adispatch_custom_event(
                    "tool_complete",
                    {"tool_name": self.name, "step_data": state["step_data"]},
                )
                return state

            field = _spec_for(field_key)
            state["current_field_key"] = field_key

            if state.get("pending_question"):
                question = state["pending_question"]
            else:
                question = await _generate_initial_question(
                    field=field,
                    collected=state.get("field_values", {}) or {},
                )
            step_num = list(s["key"] for s in self.FIELD_SPECS).index(field_key) + 1
            state["step"] = step_num

            # Ask and suspend.
            await adispatch_custom_event(
                "tool_question",
                {"text": question, "step": step_num, "input_type": "free_text", "can_skip": True},
            )
            state["questions_asked"].append(
                {"field_key": field_key, "question": question, "step": step_num, "retry": state.get("retry_count", 0)}
            )
            answer = interrupt(question)

            raw_answer = (answer or "").strip()
            state["answers_received"].append(
                {"field_key": field_key, "question": question, "raw_answer": raw_answer, "step": step_num}
            )

            # Skip
            if _is_skip(raw_answer):
                state["field_values"][field_key] = None
                state["field_raw_values"][field_key] = raw_answer
                state["field_status"][field_key] = "skipped"
                state["pending_question"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                await adispatch_custom_event("tool_progress", {"step": step_num, "total": total_steps})
                return state

            # Clarification request -> generate clarification message and re-ask.
            if _looks_like_clarification_request(raw_answer):
                state["pending_question"] = await _build_clarification_message(field)
                state["retry_count"] = min(state.get("retry_count", 0) + 1, max_retries_per_field)
                return state

            # Validate + rewrite with LLM
            judged = await _evaluate_and_rewrite(field=field, question=question, user_answer=raw_answer)
            if judged.get("ok") and judged.get("rewritten"):
                rewritten = str(judged["rewritten"]).strip()
                state["field_values"][field_key] = rewritten
                state["field_raw_values"][field_key] = raw_answer
                state["field_status"][field_key] = "filled"
                state["pending_question"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                await adispatch_custom_event("tool_progress", {"step": step_num, "total": total_steps})
                return state

            # Not ok -> follow-up loop
            state["retry_count"] = state.get("retry_count", 0) + 1
            follow_up = judged.get("follow_up_question") or f"Could you provide more detail? {field['default_question']}"
            if state["retry_count"] >= max_retries_per_field:
                # Escape hatch: accept a low-confidence fill.
                state["field_values"][field_key] = raw_answer or "No response"
                state["field_raw_values"][field_key] = raw_answer
                state["field_status"][field_key] = "filled"
                state["pending_question"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                await adispatch_custom_event("tool_progress", {"step": step_num, "total": total_steps})
                return state

            state["pending_question"] = str(follow_up).strip()
            return state

        def _continue_or_end(s: QuantumDataCollectorState) -> str:
            return END if s.get("is_complete") else "step"

        g = StateGraph(QuantumDataCollectorState)
        g.add_node("step", step)
        g.add_edge(START, "step")
        g.add_conditional_edges("step", _continue_or_end)
        return g.compile()
