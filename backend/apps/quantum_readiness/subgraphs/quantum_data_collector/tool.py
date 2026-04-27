"""
Quantum Readiness Data Collection Tool - Layer 3.

NEW LOGIC (field-filling tool):
- A small, fixed set of field specs (key + explanation + default question).
- For each field, ask a question via interrupt().
- On resume, an LLM (mistral small) evaluates if the response is satisfactory for the field,
  rewrites it if needed, and proposes a follow-up question if not satisfactory.
- The user can skip any question (UI sends "/skip") -> we store null/"no_response".
- If the user asks for clarification, we respond with a clarification message and re-ask.

For testing, we collect 8 topic-level fields (4 per branch) to keep interview
time short while preserving the two-branch structure.
"""

import json
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.model_gateway import ModelGateway
from core.protocols import SubgraphProtocol, ToolProtocol
from core.state import SubgraphState

class FieldSpec(TypedDict):
    key: str
    explanation: str
    default_question: str
    answer_criteria: str
    example_answers: List[str]


class QuantumDataCollectorState(TypedDict, total=False):
    """stepData for the field-filling collector."""

    # Field filling
    field_values: Dict[str, Optional[str]]  # key -> rewritten value or None (skipped)
    field_raw_values: Dict[str, Optional[str]]  # key -> raw user answer
    field_status: Dict[str, str]  # key -> "filled" | "skipped"
    current_field_key: Optional[str]
    pending_question: Optional[str]  # current question to ask for current_field_key
    consumed_prompt_ids: List[str]
    retry_count: int
    last_validation_reason: Optional[str]
    user_command: Optional[str] # potential inputed command between /cancel, /skip and /clarify

    # Audit
    questions_asked: List[Dict[str, Any]]
    answers_received: List[Dict[str, Any]]


class QuantumDataCollectorTool(SubgraphProtocol):
    """
    Data Collection Tool for Quantum Readiness assessment.
    
    Collects information through three phases:
    1. Onboarding (industry, interest driver)
    2. Cryptographic Risk Assessment (4 dimensions)
    3. Quantum Opportunity Assessment (4 dimensions)
    
    Uses interrupt() for each question to suspend execution and wait for user response.
    """
    
    name = "quantum_data_collector"
    # Keep model lightweight for faster validation loops.
    VALIDATOR_MODEL = "mistral/mistral-small-latest"
    # For testing: keep it small (3–4 fields).
    FIELD_SPECS: List[FieldSpec] = [
        {
            "key": "a_use_case_identification",
            "explanation": "Branch A topic: use case identification (industry, computationally intensive problems, optimization, intrinsic quantum use cases, classical bottlenecks).",
            "default_question": "Quantum Competitiveness - Use Case Identification: Tell us your industry and the most computationally intensive problems where quantum could matter, including optimization or intrinsic quantum research, and any current classical bottlenecks.",
            "answer_criteria": "Provide industry context plus at least one concrete high-compute or quantum-relevant use case.",
            "example_answers": ["Healthcare: drug discovery simulation and route optimization with long runtimes.", "Finance: portfolio optimization bottlenecks in intraday decisions."],
        },
        {
            "key": "a_technical_infrastructure_baseline",
            "explanation": "Branch A topic: technical and infrastructure baseline (HPC/cloud footprint, classical baselines, vendor relationships, internal expertise).",
            "default_question": "Quantum Competitiveness - Technical & Infrastructure Baseline: Summarize your compute footprint, classical solution maturity, any quantum vendor relationships, and whether you have internal quantum expertise.",
            "answer_criteria": "Describe current technical baseline and capability level across infrastructure, tooling, and expertise.",
            "example_answers": [
                "Hybrid HPC + cloud, mature classical optimizers, early vendor pilots, small internal team.",
                "Cloud-only stack, no vendor ties, external partners required for quantum work.",
            ],
        },
        {
            "key": "a_strategic_organizational_maturity",
            "explanation": "Branch A topic: strategic and organizational maturity (adoption posture, IP sensitivity, dedicated budget).",
            "default_question": "Quantum Competitiveness - Strategic & Organizational Maturity: Describe your technology adoption posture, IP sensitivity, and whether budget for quantum exploration is dedicated or competing with other initiatives.",
            "answer_criteria": "Provide posture, governance/budget context, and strategic readiness indicators.",
            "example_answers": [
                "Second-mover posture, strong IP portfolio, dedicated exploration budget.",
                "Wait-and-see posture, limited IP pressure, no dedicated budget.",
            ],
        },
        {
            "key": "a_roadmap_ecosystem",
            "explanation": "Branch A topic: roadmap and ecosystem (internal pilots, ecosystem participation, competitor monitoring).",
            "default_question": "Quantum Competitiveness - Roadmap & Ecosystem: Describe any internal quantum assessments/pilots, ecosystem or academic partnerships, and how you track competitor activity.",
            "answer_criteria": "Include execution roadmap signals and ecosystem engagement level.",
            "example_answers": [
                "Active pilots, consortium membership, and quarterly competitor intelligence.",
                "No pilots yet, limited ecosystem ties, informal monitoring only.",
            ],
        },
        {
            "key": "b_data_exposure_profile",
            "explanation": "Branch B topic: data and exposure profile (confidentiality horizon, standards visibility, cryptography inventory, compliance, long-lived PKI assets).",
            "default_question": "Cryptographic Risk & PQ Security - Data & Exposure Profile: Summarize how long sensitive data must remain confidential, how well you know your current encryption standards and cryptography inventory, key compliance drivers, and any long-lived public-key dependencies.",
            "answer_criteria": "Provide exposure profile details with at least partial inventory/standards awareness.",
            "example_answers": ["10+ year confidentiality data, partial inventory, PCI and ISO scope, strong PKI dependencies.", "Shorter horizons, limited inventory, low regulatory pressure."],
        },
        {
            "key": "b_migration_readiness",
            "explanation": "Branch B topic: migration readiness (NIST PQC evaluation, vendor plans, crypto agility, timeline/budget).",
            "default_question": "Cryptographic Risk & PQ Security - Migration Readiness: Describe your current PQC migration status (NIST algorithms), vendor readiness checks, cryptographic agility in new systems, and your migration timeline/budget.",
            "answer_criteria": "Indicate migration stage and practical readiness for execution.",
            "example_answers": ["PQC pilots underway, vendor plans reviewed, agility-by-design, funded roadmap.", "Not started, no vendor review, no timeline or budget."],
        },
        {
            "key": "b_supply_chain_ecosystem",
            "explanation": "Branch B topic: supply chain and ecosystem risk (vendor vulnerability, contractual pressure, incident response).",
            "default_question": "Cryptographic Risk & PQ Security - Supply Chain & Ecosystem: Explain your third-party encryption exposure, expected contractual PQC pressure from customers/partners, and incident response preparedness for sudden cryptographic compromise.",
            "answer_criteria": "Cover external dependency risk and preparedness to respond.",
            "example_answers": ["Critical vendors expose legacy crypto risk; response plan tested.", "Exposure unclear and incident planning minimal."],
        },
        {
            "key": "b_governance",
            "explanation": "Branch B topic: governance (executive sponsorship and dedicated budget).",
            "default_question": "Cryptographic Risk & PQ Security - Governance: Describe executive-level ownership of quantum cryptographic risk and whether budget for PQC migration is dedicated.",
            "answer_criteria": "State leadership sponsorship and budget governance maturity.",
            "example_answers": ["CISO-sponsored program with ring-fenced PQC budget.", "No clear executive sponsor; budget competes with general security needs."],
        },
    ]
    TOTAL_STEPS = 8
    MAX_RETRIES_PER_FIELD = 2
    
    def __init__(self, model_gateway: ModelGateway, interrupt_tool: ToolProtocol):
        self._model_gateway = model_gateway
        self._interrupt_tool = interrupt_tool
    
    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."
    
    def build(self):
        """Build the field-filling collector tool graph."""

        g = StateGraph(SubgraphState)

        g.add_node("init_state", self.init_step)
        g.add_node("pick_active_field", self.pick_active_field_step)
        g.add_node("question", self.question_step)
        g.add_node("interrupt", self._interrupt_tool.build())
        g.add_node("process_answer", self.process_answer_step)
        g.add_node("command_handler", self.command_handler_step)
        g.add_node("validate_and_rewrite", self.validate_and_rewrite_step)

        g.add_edge(START, "init_state")
        g.add_edge("init_state", "pick_active_field")
        g.add_conditional_edges("pick_active_field", self.router, {
            "question": "question",
            "analyzer": END,
            END: END
        })
        g.add_edge("question", "interrupt")
        g.add_edge("interrupt", "process_answer")
        g.add_conditional_edges("process_answer", self.router, {
            "command_handler": "command_handler",
            "validate_and_rewrite": "validate_and_rewrite",
            "pick_active_field": "pick_active_field"
        })
        g.add_conditional_edges("command_handler", self.router, {
            "pick_active_field": "pick_active_field",
            END: END
        })
        g.add_edge("validate_and_rewrite", "pick_active_field")
        
        return g.compile()
    
    async def router(self, state: SubgraphState) -> str:
        # TODO: manage errors + manage undefined nextNode
        print("[ROUTER]: debug nextNode : ", state.get("nextNode"))
        return state.get("nextNode")
    
    async def init_step(self, state: SubgraphState) -> SubgraphState:
        stepData : QuantumDataCollectorState = {
            "field_values": {},
            "field_raw_values": {},
            "field_status": {},
            "current_field_key": None,
            "pending_question": None,
            "consumed_prompt_ids": [],
            "retry_count": 0,
            "last_validation_reason": None,
            "user_command": None,
            "questions_asked": [],
            "answers_received": [],
        }

        state["currentStep"] = "collecting"
        state["nextNode"] = "pick_active_field"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None
        state["common_tool_input"] = None

        await adispatch_custom_event(
            "tool_start",
            {
                "tool_name": self.name,
                "total_steps": self.TOTAL_STEPS,
                "fields": self.FIELD_SPECS,
                "skip_command": "/skip",
                "clarify_command": "/clarify",
            },
        )
        return state

    async def pick_active_field_step(self, state: SubgraphState) -> SubgraphState:
        # pick active field
        field_key = state["stepData"].get("current_field_key") or self._next_unfilled_key(state["stepData"])
        print("debug step (quantum_data_collector/tool.py l.330) : field_key :\n    ", field_key)
        if field_key is None:
            collected = state["stepData"].get("field_values", {})
            branch_a_topics = {
                "use_case_identification": collected.get("a_use_case_identification"),
                "technical_infrastructure_baseline": collected.get("a_technical_infrastructure_baseline"),
                "strategic_organizational_maturity": collected.get("a_strategic_organizational_maturity"),
                "roadmap_ecosystem": collected.get("a_roadmap_ecosystem"),
            }
            branch_b_topics = {
                "data_exposure_profile": collected.get("b_data_exposure_profile"),
                "migration_readiness": collected.get("b_migration_readiness"),
                "supply_chain_ecosystem": collected.get("b_supply_chain_ecosystem"),
                "governance": collected.get("b_governance"),
            }

            step_data = {
                "user_industry": collected.get("a_use_case_identification"),
                "branch_a_topics": branch_a_topics,
                "branch_b_topics": branch_b_topics,
                "fields": collected,
            }
            await adispatch_custom_event(
                "tool_complete",
                {"tool_name": self.name, "step_data": step_data},
            )
            state["stepData"] = step_data
            state["nextNode"] = "analyzer"
            return state

        state["stepData"]["current_field_key"] = field_key
        state["nextNode"] = "question"
        return state

    async def question_step(self, state: SubgraphState) -> SubgraphState:
        field_key = state["stepData"].get("current_field_key")
        field = self._spec_for(field_key)
        if state["stepData"].get("pending_question"):
            question = state["stepData"]["pending_question"]
        else:
            question = field["default_question"]
        step_num = list(s["key"] for s in self.FIELD_SPECS).index(field_key) + 1
        prompt_id = state.get("pending_prompt_id") or str(uuid.uuid4())
        state["pending_prompt_id"] = prompt_id

        state["stepData"]["questions_asked"].append(
            {
                "field_key": field_key,
                "question": question,
                "step": step_num,
                "retry": state["stepData"].get("retry_count", 0),
                "prompt_id": prompt_id,
            }
        )

        state["nextNode"] = "interrupt"
        state["common_tool_input"] = {
            "nextNode": "process_answer",
            "args": {
                "text": question,
                "prompt_id": prompt_id,
                "step": step_num,
                "input_type": "free_text",
                "can_skip": True,
            }
        }
        return state
    
    async def process_answer_step(self, state: SubgraphState) -> SubgraphState:
        resume_prompt_id = None
        prompt_id = state.get("pending_prompt_id")
        question = state["stepData"].get("questions_asked")[-1]
        answer = state["common_tool_output"].get("answer")
        if isinstance(answer, dict):
            raw_answer = str(answer.get("text", "")).strip()
            resume_prompt_id = answer.get("prompt_id")
        else:
            raw_answer = str(answer or "").strip()
        state["stepData"]["answers_received"].append(
            {
                "field_key": question["field_key"],
                "question": question["question"],
                "raw_answer": raw_answer,
                "step": question["step"],
                "prompt_id": resume_prompt_id,
            }
        )
        if resume_prompt_id and resume_prompt_id != prompt_id:
            state["stepData"]["pending_question"] = question
            state["stepData"]["last_validation_reason"] = "Stale prompt answer received."
            state["nextNode"] = "pick_active_field"
            return state
        if prompt_id in state["stepData"]["consumed_prompt_ids"]:
            state["stepData"]["pending_question"] = question
            state["stepData"]["last_validation_reason"] = "Duplicate prompt answer ignored."
            state["nextNode"] = "pick_active_field"
            return state
        state["stepData"]["consumed_prompt_ids"].append(prompt_id)

        command = self._normalized_command(raw_answer)
        if (command == None):
            state["nextNode"] = "validate_and_rewrite"
        else:
            state["nextNode"] = "command_handler"
            state["stepData"]["user_command"] = command
        return state
        
    async def command_handler_step(self, state: SubgraphState) -> SubgraphState:

        command = state["stepData"].get("user_command")
        answer = state["stepData"].get("answers_received")[-1]

        if command == "/cancel":
            state["error"] = "Tool cancelled by user."
            state["currentStep"] = "Idle"
            state["stepData"] = {}
            state["common_tool_input"] = {}
            state["common_tool_output"] = {}
            state["pending_prompt_id"] = None
            state["nextNode"] = END
            return state
        
        if command == "/skip":
            state["stepData"]["field_values"][answer["field_key"]] = None
            state["stepData"]["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
            state["stepData"]["field_status"][answer["field_key"]] = "skipped"
            state["stepData"]["pending_question"] = None
            state["pending_prompt_id"] = None
            state["stepData"]["retry_count"] = 0
            state["stepData"]["current_field_key"] = None
            state["nextNode"] = "pick_active_field"
            await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": self.TOTAL_STEPS})
            return state
        
        # Clarification request -> generate clarification message and re-ask.
        if command == "/clarify":
            field = self._spec_for(answer["field_key"])
            state["stepData"]["pending_question"] = await self._build_clarification_message(field)
            state["pending_prompt_id"] = None
            state["stepData"]["retry_count"] = min(state["stepData"].get("retry_count", 0) + 1, self.MAX_RETRIES_PER_FIELD)
            state["nextNode"] = "pick_active_field"
            return state
    
    async def validate_and_rewrite_step(self, state: SubgraphState) -> SubgraphState:
        question = state["stepData"].get("questions_asked")[-1]
        answer = state["stepData"].get("answers_received")[-1]
        field = self._spec_for(answer["field_key"])

        # Validate + rewrite with LLM
        judged = await self._evaluate_and_rewrite(field=field, question=question["question"], user_answer=answer["raw_answer"])
        if judged.get("ok") and judged.get("rewritten"):
            rewritten = str(judged["rewritten"]).strip()
            state["stepData"]["field_values"][answer["field_key"]] = rewritten
            state["stepData"]["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
            state["stepData"]["field_status"][answer["field_key"]] = "filled"
            state["stepData"]["pending_question"] = None
            state["pending_prompt_id"] = None
            state["stepData"]["retry_count"] = 0
            state["stepData"]["current_field_key"] = None
            state["stepData"]["last_validation_reason"] = None
            state["nextNode"] = "pick_active_field"
            await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": self.TOTAL_STEPS})
            return state

        # Not ok -> follow-up loop
        state["stepData"]["retry_count"] = state["stepData"].get("retry_count", 0) + 1
        follow_up = judged.get("follow_up_question") or f"Could you provide more detail? {field['default_question']}"
        state["stepData"]["last_validation_reason"] = judged.get("reason") or "Missing required details."
        if state["stepData"]["retry_count"] >= self.MAX_RETRIES_PER_FIELD:
            # Escape hatch: accept a low-confidence fill.
            state["stepData"]["field_values"][answer["field_key"]] = answer["raw_answer"] or "No response"
            state["stepData"]["field_raw_values"][answer["field_key"]] = answer["raw_answer"]
            state["stepData"]["field_status"][answer["field_key"]] = "filled"
            state["stepData"]["pending_question"] = None
            state["pending_prompt_id"] = None
            state["stepData"]["retry_count"] = 0
            state["stepData"]["current_field_key"] = None
            state["nextNode"] = "pick_active_field"
            await adispatch_custom_event("tool_progress", {"step": answer["step"], "total": self.TOTAL_STEPS})
            return state

        state["stepData"]["pending_question"] = str(follow_up).strip()
        state["pending_prompt_id"] = None
        state["nextNode"] = "pick_active_field"
        return state

    # ------------- Utils functions ----------------

    def _spec_for(self, key: str) -> FieldSpec:
        for s in self.FIELD_SPECS:
            if s["key"] == key:
                return s
        raise KeyError(key)
    
    def _normalized_command(self, text: str) -> Optional[str]:
        v = (text or "").strip().lower()
        if v in {"/skip", "/clarify", "/cancel"}:
            return v
        return None
    
    async def _evaluate_and_rewrite(
        self,
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
        
    async def _build_clarification_message(self, field: FieldSpec) -> str:
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
    
    def _next_unfilled_key(self, stepData: QuantumDataCollectorState) -> Optional[str]:
        values = stepData.get("field_values", {}) or {}
        for spec in self.FIELD_SPECS:
            if spec["key"] not in values:
                return spec["key"]
        return None

    async def _generate_initial_question(
        self,
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