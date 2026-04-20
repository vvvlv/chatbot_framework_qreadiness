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
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from core.model_gateway import ModelGateway
from core.protocols import ToolProtocol
from core.state import SubgraphState


class FieldSpec(TypedDict):
    key: str
    explanation: str
    default_question: str
    answer_criteria: str
    example_answers: List[str]


class QuantumDataCollectorState(SubgraphState, total=False):
    """State for the field-filling collector."""

    # graph routing
    error: Optional[str]
    is_complete: bool # indicates if all steps are complete
    next_step: Optional[str] # the next node to call in case of conditional edges
    tool_started: bool # TODO : unecessary ?

    # Field filling
    field_values: Dict[str, Optional[str]]  # key -> rewritten value or None (skipped)
    field_raw_values: Dict[str, Optional[str]]  # key -> raw user answer
    field_status: Dict[str, str]  # key -> "filled" | "skipped"
    current_field_key: Optional[str]
    pending_question: Optional[str]  # current question to ask for current_field_key
    pending_prompt_id: Optional[str]
    awaiting_answer: bool # TODO : unecessary ?
    consumed_prompt_ids: List[str]
    retry_count: int
    last_validation_reason: Optional[str]
    user_command: Optional[str] # potential inputed command between /cancel, /skip and /clarify

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

        def _normalized_command(text: str) -> Optional[str]:
            v = (text or "").strip().lower()
            if v in {"/skip", "/clarify", "/cancel"}:
                return v
            return None

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
              missing_bits: string[]
              reason: str | null
            """
            print("_evaluate_and_rewrite ->")
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
  "missing_bits": ["string", "..."],
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
                    "missing_bits": data.get("missing_bits") or [],
                    "reason": (data.get("reason") or None),
                }
            except Exception:
                # Fail-safe: treat as not ok and ask a generic follow-up.
                return {
                    "ok": False,
                    "rewritten": None,
                    "follow_up_question": f"Could you provide a bit more detail? {field['default_question']}",
                    "missing_bits": ["Missing required details."],
                    "reason": "Could not parse validator output.",
                }

        async def _build_clarification_message(field: FieldSpec) -> str:
            print("_build_clarification_message ->")
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
            print("_generate_initial_question ->")
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
                print("An exception occured during _generate_initial_question")
            return field["default_question"]

        async def init_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("init_step ->")

            # defaults
            state.setdefault("field_values", {})
            state.setdefault("field_raw_values", {})
            state.setdefault("field_status", {})
            state.setdefault("current_field_key", None)
            state.setdefault("pending_question", None)
            state.setdefault("pending_prompt_id", None)
            state.setdefault("consumed_prompt_ids", [])
            state.setdefault("retry_count", 0)
            state.setdefault("last_validation_reason", None)
            state.setdefault("questions_asked", [])
            state.setdefault("answers_received", [])
            state.setdefault("is_complete", False)
            state.setdefault("error", None)
            state.setdefault("next_step", "pick_active_field")

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
            return state

        async def pick_active_field_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("pick_active_field_step ->")
            # pick active field
            state["next_step"] = "question"
            field_key = state.get("current_field_key") or _next_unfilled_key(state)
            print("debug step (quantum_data_collector/tool.py l.330) : field_key :\n    ", field_key)
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

                step_data = {
                    "user_industry": collected.get("user_industry"),
                    "crypto_risk_dimensions": crypto_risk_dimensions,
                    "quantum_opportunity_dimensions": {},
                    "fields": collected,
                }
                state["tool_output"] = {
                    "step_data": step_data,
                    "is_complete": True,
                    "error": None,
                }
                state["is_complete"] = True
                await adispatch_custom_event(
                    "tool_complete",
                    {"tool_name": self.name, "step_data": step_data},
                )
                return state

            state["current_field_key"] = field_key
            return state

        async def question_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("question_step ->")
            state["next_step"] = "HITL"
            field_key = state.get("current_field_key")
            field = _spec_for(field_key)
            if state.get("pending_question"):
                question = state["pending_question"]
            else:
                question = await _generate_initial_question(
                    field=field,
                    collected=state.get("field_values", {}) or {},
                )
            step_num = list(s["key"] for s in self.FIELD_SPECS).index(field_key) + 1
            prompt_id = state.get("pending_prompt_id") or str(uuid.uuid4())
            state["pending_prompt_id"] = prompt_id

            state["questions_asked"].append(
                {
                    "field_key": field_key,
                    "question": question,
                    "step": step_num,
                    "retry": state.get("retry_count", 0),
                    "prompt_id": prompt_id,
                }
            )
            return state

        async def HITL_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("HITL_step ->")
            question = state.get("questions_asked")[-1]
            print("debug step (quantum_data_collector/tool.py l.386) : question : ", question)
            prompt_id = state.get("pending_prompt_id")
            answer = interrupt(
                {
                    "text": question["question"],
                    "prompt_id": prompt_id,
                    "step": question["step"],
                    "input_type": "free_text",
                    "can_skip": True,
                }
            )
            print("debug step (quantum_data_collector/tool.py l.396) : line after interrupt()")
            state["awaiting_answer"] = False

            resume_prompt_id = None
            if isinstance(answer, dict):
                raw_answer = str(answer.get("text", "")).strip()
                resume_prompt_id = answer.get("prompt_id")
            else:
                raw_answer = str(answer or "").strip()
            state["answers_received"].append(
                {
                    "field_key": question["field_key"],
                    "question": question,
                    "raw_answer": raw_answer,
                    "step": question["step"],
                    "prompt_id": resume_prompt_id,
                }
            )
            if resume_prompt_id and resume_prompt_id != prompt_id:
                state["pending_question"] = question
                state["last_validation_reason"] = "Stale prompt answer received."
                state["next_step"] = "pick_active_field"
                return state
            if prompt_id in state["consumed_prompt_ids"]:
                state["pending_question"] = question
                state["last_validation_reason"] = "Duplicate prompt answer ignored."
                state["next_step"] = "pick_active_field"
                return state
            state["consumed_prompt_ids"].append(prompt_id)

            command = _normalized_command(raw_answer)
            if (command == None):
                state["next_step"] = "validate_and_rewrite"
            else:
                state["next_step"] = "command_handler"
                state["user_command"] = command
            return state
        
        async def command_handler_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("command_handler_step ->")

            state["next_step"] = "pick_active_field"
            command = state.get("user_command")
            answer = state.get("answers_received")[-1]

            if command == "/cancel":
                state["error"] = "Tool cancelled by user."
                state["is_complete"] = True
                state["pending_prompt_id"] = None
                state["tool_output"] = {"step_data": {}, "is_complete": True, "error": state["error"]}
                return state
            if command == "/skip":
                state["field_values"][answer["field_key"]] = None
                state["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
                state["field_status"][answer["field_key"]] = "skipped"
                state["pending_question"] = None
                state["pending_prompt_id"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": total_steps})
                return state

            # Clarification request -> generate clarification message and re-ask.
            if command == "/clarify":
                field = _spec_for(answer["field_key"])
                state["pending_question"] = await _build_clarification_message(field)
                state["pending_prompt_id"] = None
                state["retry_count"] = min(state.get("retry_count", 0) + 1, max_retries_per_field)
                return state
        
        async def validate_and_rewrite_step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            print("validate_and_rewrite_step ->")

            state["next_step"] = "pick_active_field"
            question = state.get("questions_asked")[-1]
            answer = state.get("answers_received")[-1]
            field = _spec_for(answer["field_key"])

            # Validate + rewrite with LLM
            judged = await _evaluate_and_rewrite(field=field, question=question["question"], user_answer=answer["raw_answer"])
            if judged.get("ok") and judged.get("rewritten"):
                rewritten = str(judged["rewritten"]).strip()
                state["field_values"][answer["field_key"]] = rewritten
                state["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
                state["field_status"][answer["field_key"]] = "filled"
                state["pending_question"] = None
                state["pending_prompt_id"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                state["last_validation_reason"] = None
                await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": total_steps})
                return state

            # Not ok -> follow-up loop
            state["retry_count"] = state.get("retry_count", 0) + 1
            follow_up = judged.get("follow_up_question") or f"Could you provide more detail? {field['default_question']}"
            state["last_validation_reason"] = judged.get("reason") or "Missing required details."
            if state["retry_count"] >= max_retries_per_field:
                # Escape hatch: accept a low-confidence fill.
                state["field_values"][answer["field_key"]] = answer["raw_answer"] or "No response"
                state["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
                state["field_status"][answer["field_key"]] = "filled"
                state["pending_question"] = None
                state["pending_prompt_id"] = None
                state["retry_count"] = 0
                state["current_field_key"] = None
                await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": total_steps})
                return state

            state["pending_question"] = str(follow_up).strip()
            state["pending_prompt_id"] = None
            return state

        def _continue_or_end(s: QuantumDataCollectorState) -> str:
            print("debut step (quantum_data_collector/tool.py l.485): state :\n      ", s)
            return END if s.get("is_complete") else s.get("next_step")

        g = StateGraph(QuantumDataCollectorState)

        g.add_node("init_state", init_step)
        g.add_node("pick_active_field", pick_active_field_step)
        g.add_node("question", question_step)
        g.add_node("HITL", HITL_step)
        g.add_node("command_handler", command_handler_step)
        g.add_node("validate_and_rewrite", validate_and_rewrite_step)

        g.add_edge(START, "init_state")
        g.add_edge("init_state", "pick_active_field")
        g.add_conditional_edges("pick_active_field", _continue_or_end)
        g.add_edge("question", "HITL")
        g.add_conditional_edges("HITL", _continue_or_end)
        g.add_conditional_edges("command_handler", _continue_or_end)
        g.add_edge("validate_and_rewrite", "pick_active_field")
        
        return g.compile()
