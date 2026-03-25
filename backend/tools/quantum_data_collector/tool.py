"""
Quantum Readiness Data Collection Tool - Layer 3.

Collects all required information through conversational questioning.
Uses interrupt() to pause execution and wait for user responses.
Adapts questions based on user expertise level and previous answers.
"""
import json
from typing import Dict, List, Literal, Optional, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from core.protocols import ToolProtocol
from core.state import ToolState
from core.model_gateway import ModelGateway


class QuantumDataCollectorState(ToolState, total=False):
    """State for Quantum Readiness Data Collection Tool."""
    
    # Onboarding data
    user_industry: Optional[str]
    user_interest_driver: Optional[str]
    user_expertise_level: Optional[Literal["beginner", "intermediate", "expert"]]
    company_name: Optional[str]
    
    # Cryptographic Risk Assessment data
    crypto_risk_dimensions: Dict[str, Dict]  # {dimension: {score, confidence, details}}
    
    # Quantum Opportunity Assessment data
    quantum_opportunity_dimensions: Dict[str, Dict]
    
    # Collection tracking
    current_phase: Literal["onboarding", "crypto_risk", "quantum_opportunity"]
    current_dimension: Optional[str]
    questions_asked: List[str]
    answers_received: List[Dict]
    needs_clarification: bool
    clarification_question: Optional[str]
    clarification_retry_count: int
    tool_started: bool


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
    REQUIRED_FIELDS = {
        "onboarding": {
            "user_industry": "Primary industry/sector the organization operates in.",
            "user_interest_driver": "Main motivation for pursuing quantum readiness now.",
        },
        "crypto_risk": {
            "data_sensitivity": "How sensitive and long-lived protected data is.",
            "crypto_visibility": "How well cryptographic assets/dependencies are inventoried.",
            "migration_progress": "Current progress toward post-quantum migration.",
            "compliance_exposure": "Regulatory/compliance pressure related to cryptography.",
        },
        "quantum_opportunity": {
            "problem_solution_fit": "Strength of fit between business problems and quantum advantage.",
            "org_readiness": "Organizational capability/readiness to execute quantum initiatives.",
            "tech_maturity": "Maturity of data/compute stack needed to leverage quantum.",
            "strategic_horizon": "Strategic horizon and budget commitment for quantum initiatives.",
        },
    }
    
    def __init__(self, model_gateway: ModelGateway):
        self._model_gateway = model_gateway
    
    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."
    
    def build(self):
        """Build the data collection tool graph.

        This tool uses `interrupt()` as a single "question/answer" suspension point per
        node execution. After the user responds, the node updates state and returns.
        The tool graph then loops back to the node to ask the next missing question.
        """

        total_questions = 10
        max_clarification_retries = 3
        required_crypto_dimensions = [
            "data_sensitivity",
            "crypto_visibility",
            "migration_progress",
            "compliance_exposure",
        ]
        required_quantum_dimensions = [
            "problem_solution_fit",
            "org_readiness",
            "tech_maturity",
            "strategic_horizon",
        ]

        async def _rewrite_answer(
            phase: str,
            dimension: str,
            question: str,
            answer: str,
        ) -> str:
            """
            Normalize user's free-text into a concise, meaningful value.
            Falls back to the original answer if rewriting fails.
            """
            prompt = f"""Rewrite the user's answer into a concise, unambiguous statement suitable for a structured assessment.

Phase: {phase}
Dimension: {dimension}
Question: {question}
User answer: {answer}

Rules:
- Be factual and neutral; remove hedging or filler.
- If numbers/timeframes are mentioned, keep them explicit (e.g., "7-10 years").
- Keep it under 200 characters.
- Return ONLY the rewritten text."""
            try:
                rewritten = await self._model_gateway.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                rewritten = (rewritten or "").strip()
                if rewritten and "return only the rewritten text" not in rewritten.lower():
                    return rewritten
            except Exception:
                pass
            return answer.strip()

        def _looks_like_gibberish(text: str) -> bool:
            """
            Heuristic gibberish detection for low-quality free-text:
            - very long unbroken tokens
            - low vowel ratio on alphabetic content
            - high symbol/noise ratio
            """
            t = (text or "").strip().lower()
            if not t:
                return True

            tokens = t.split()
            longest_token = max((len(tok) for tok in tokens), default=0)
            # Accept long technical tokens when they look domain-like.
            technical_markers = ("quantum", "crypt", "pqc", "fips", "nist", "kyber", "dilithium", "algorithm")
            has_technical_signal = any(marker in t for marker in technical_markers) or "-" in t
            if longest_token >= 24 and not has_technical_signal:
                return True

            alpha = [c for c in t if c.isalpha()]
            if alpha:
                vowels = sum(1 for c in alpha if c in "aeiou")
                vowel_ratio = vowels / max(len(alpha), 1)
                if len(alpha) >= 8 and vowel_ratio < 0.15:
                    return True

            symbol_count = sum(1 for c in t if not c.isalnum() and not c.isspace())
            if symbol_count > 0 and symbol_count / max(len(t), 1) > 0.25:
                return True

            return False

        def _is_unknown_response(text: str) -> bool:
            v = (text or "").strip().lower()
            unknown_markers = (
                "i don't know",
                "i dont know",
                "dont know",
                "do not know",
                "not sure",
                "unsure",
                "no idea",
                "i can't answer",
                "i cant answer",
                "unknown",
            )
            return any(marker in v for marker in unknown_markers)

        def _is_compact_negative(text: str) -> bool:
            v = (text or "").strip().lower()
            return v in {"no", "none", "not yet", "negative", "n/a", "na"}

        def _validate_field(
            phase: str,
            dimension: str,
            value: str,
        ) -> tuple[bool, str | None]:
            """
            Lightweight validation by dimension:
            - non-empty
            - minimal length
            - simple pattern checks for expected content
            Returns (is_valid, error_hint).
            """
            v = (value or "").strip().lower()
            if not v:
                return False, "I didn't get any content."
            # Treat explicit uncertainty as meaningful low-confidence input for
            # assessment dimensions to avoid dead-end loops.
            if phase in ("crypto_risk", "quantum_opportunity") and _is_unknown_response(v):
                return True, None
            # Compact negatives can be valid for many yes/no-like assessment fields.
            if dimension in {
                "crypto_visibility",
                "migration_progress",
                "compliance_exposure",
                "problem_solution_fit",
                "org_readiness",
                "tech_maturity",
                "strategic_horizon",
            } and _is_compact_negative(v):
                return True, None
            if len(v) < 3:
                return False, "The answer is too short. Please add a few more details."
            if _looks_like_gibberish(v):
                return False, "That response looks unclear or random. Please answer in a clear sentence."

            # Heuristic checks per dimension
            if dimension == "data_sensitivity":
                if not any(tok in v for tok in ("year", "month", "long", "retention", "confidential")) and not any(
                    ch.isdigit() for ch in v
                ):
                    return False, "Please include how long sensitive data must remain confidential (e.g., '7-10 years')."
            if dimension == "crypto_visibility":
                if not any(tok in v for tok in ("inventory", "encryption", "standards", "visibility", "dependencies")):
                    return False, "Mention inventory/visibility of encryption/crypto dependencies."
            if dimension == "migration_progress":
                if not any(tok in v for tok in ("pilot", "pqc", "post-quantum", "migration", "rollout", "plan", "roadmap")):
                    return False, "Include current PQC/post-quantum migration status (pilot/plan/production)."
            if dimension == "compliance_exposure":
                if not any(tok in v for tok in ("hipaa", "pci", "fips", "sox", "gdpr", "compliance", "regulatory")) and "none" not in v:
                    return False, "State applicable frameworks (e.g., HIPAA, PCI-DSS) or 'none'."
            if dimension == "problem_solution_fit":
                if not any(tok in v for tok in ("optimization", "simulation", "bottleneck", "quantum", "fit", "problem")) and "none" not in v:
                    return False, "Provide example bottlenecks or state that there are none."
            if dimension == "org_readiness":
                if not any(tok in v for tok in ("team", "expertise", "outsourced", "innovation", "research", "skills")):
                    return False, "Indicate internal team/expertise or if you'll outsource."
            if dimension == "tech_maturity":
                if not any(tok in v for tok in ("hpc", "cloud", "pipeline", "infrastructure", "stack", "maturity", "data")):
                    return False, "Briefly describe infra/data stack (HPC/cloud/pipelines)."
            if dimension == "strategic_horizon":
                if not any(tok in v for tok in ("year", "budget", "horizon", "roadmap", "planning", "timeline")) and "none" not in v:
                    return False, "Include a timeframe/budget horizon or state none."

            return True, None

        def _raw_answer_grounded(dimension: str, raw_value: str) -> bool:
            """
            Ensure the user's original answer contains at least minimal, domain-relevant
            signal for the target field. This prevents rewrite-induced hallucinated validity.
            """
            v = (raw_value or "").strip().lower()
            if not v or len(v) < 3 or _looks_like_gibberish(v):
                # Short, explicit negatives are still meaningful for some fields.
                if dimension in {
                    "crypto_visibility",
                    "migration_progress",
                    "compliance_exposure",
                    "problem_solution_fit",
                    "org_readiness",
                    "tech_maturity",
                    "strategic_horizon",
                } and _is_compact_negative(v):
                    return True
                return False
            if dimension in {
                "data_sensitivity",
                "crypto_visibility",
                "migration_progress",
                "compliance_exposure",
                "problem_solution_fit",
                "org_readiness",
                "tech_maturity",
                "strategic_horizon",
            } and _is_unknown_response(v):
                return True

            if dimension == "user_industry":
                return len(v.split()) >= 1
            if dimension == "user_interest_driver":
                return len(v.split()) >= 2
            if dimension == "data_sensitivity":
                return any(tok in v for tok in ("year", "month", "long", "retention", "confidential")) or any(
                    ch.isdigit() for ch in v
                )
            if dimension == "crypto_visibility":
                return any(tok in v for tok in ("inventory", "encryption", "standards", "visibility", "dependencies"))
            if dimension == "migration_progress":
                return any(tok in v for tok in ("pilot", "pqc", "post-quantum", "migration", "rollout", "plan", "roadmap"))
            if dimension == "compliance_exposure":
                return any(tok in v for tok in ("hipaa", "pci", "fips", "sox", "gdpr", "compliance", "regulatory", "none"))
            if dimension == "problem_solution_fit":
                return any(tok in v for tok in ("optimization", "simulation", "bottleneck", "quantum", "problem", "none"))
            if dimension == "org_readiness":
                return any(tok in v for tok in ("team", "expertise", "outsourced", "innovation", "research", "skills"))
            if dimension == "tech_maturity":
                return any(tok in v for tok in ("hpc", "cloud", "pipeline", "infrastructure", "stack", "maturity", "data"))
            if dimension == "strategic_horizon":
                return any(tok in v for tok in ("year", "budget", "horizon", "roadmap", "planning", "timeline", "none"))

            return True

        async def step(state: QuantumDataCollectorState) -> QuantumDataCollectorState:
            session_id = state.get("session_id", "unknown")
            phase = state.get("current_phase", "onboarding")

            # Initialize state defaults (for the first turn or if missing fields).
            if "current_phase" not in state:
                state["current_phase"] = "onboarding"
            if "crypto_risk_dimensions" not in state:
                state["crypto_risk_dimensions"] = {}
            if "quantum_opportunity_dimensions" not in state:
                state["quantum_opportunity_dimensions"] = {}
            if "questions_asked" not in state:
                state["questions_asked"] = []
            if "answers_received" not in state:
                state["answers_received"] = []
            if "tool_started" not in state:
                state["tool_started"] = False
            if "is_complete" not in state:
                state["is_complete"] = False
            if "needs_clarification" not in state:
                state["needs_clarification"] = False
            if "clarification_question" not in state:
                state["clarification_question"] = None
            if "clarification_retry_count" not in state:
                state["clarification_retry_count"] = 0

            if not state["tool_started"]:
                await adispatch_custom_event(
                    "tool_start",
                    {
                        "tool_name": self.name,
                        "total_steps": total_questions,
                        "required_fields": self.REQUIRED_FIELDS,
                    },
                )
                state["tool_started"] = True
                state["tool_status"] = "running"

            # Finalize if complete (normally this triggers graph END).
            if state.get("is_complete"):
                if state.get("tool_status") != "done":
                    state["step_data"] = {
                        "user_industry": state.get("user_industry"),
                        "user_interest_driver": state.get("user_interest_driver"),
                        "user_expertise_level": state.get("user_expertise_level"),
                        "crypto_risk_dimensions": state.get("crypto_risk_dimensions", {}),
                        "quantum_opportunity_dimensions": state.get("quantum_opportunity_dimensions", {}),
                    }
                    state["tool_status"] = "done"
                    state["tool_output"] = {"step_data": state["step_data"], "is_complete": True}
                    await adispatch_custom_event(
                        "tool_complete",
                        {"tool_name": self.name, "step_data": state["step_data"]},
                    )
                return state

            print(f"[DATA_COLLECTOR] Step - session: {session_id}, phase: {phase}")

            # Clarification sub-step: ask clarification_question, then process and clear.
            if state.get("needs_clarification") and state.get("clarification_question"):
                question = state["clarification_question"]
                # Clarifications are still part of the same dimension/question step.
                # Don't increment the global step counter or exceed `total_steps`.
                state["step"] = len(state["questions_asked"])

                await adispatch_custom_event(
                    "tool_question",
                    {"text": question, "step": state["step"], "input_type": "free_text"},
                )
                answer = interrupt(question)

                dimension = state.get("current_dimension")
                phase_for_processing = state.get("current_phase", phase)
                context = (
                    state.get("crypto_risk_dimensions", {})
                    if phase_for_processing == "crypto_risk"
                    else state.get("quantum_opportunity_dimensions", {})
                )

                normalized = await _rewrite_answer(
                    phase=phase_for_processing,
                    dimension=dimension,
                    question=question,
                    answer=answer,
                )
                if not _raw_answer_grounded(dimension, answer):
                    ok, hint = False, _validate_field(phase_for_processing, dimension, answer)[1]
                else:
                    ok, hint = _validate_field(phase_for_processing, dimension, normalized)
                if not ok:
                    # Keep asking for this same field until a minimally valid value is provided.
                    state["clarification_retry_count"] = state.get("clarification_retry_count", 0) + 1
                    if state["clarification_retry_count"] >= max_clarification_retries:
                        # Escape hatch: persist low-confidence placeholder and continue,
                        # instead of trapping the user in an endless clarification loop.
                        fallback_answer = (answer or "").strip() or "Unknown"
                        if phase_for_processing == "crypto_risk":
                            state["crypto_risk_dimensions"][dimension] = {
                                "score": 50,
                                "confidence": "low",
                                "details": f"Unresolved after {max_clarification_retries} retries: {fallback_answer}",
                            }
                        elif phase_for_processing == "quantum_opportunity":
                            state["quantum_opportunity_dimensions"][dimension] = {
                                "score": 50,
                                "confidence": "low",
                                "details": f"Unresolved after {max_clarification_retries} retries: {fallback_answer}",
                            }
                        elif dimension == "user_industry":
                            state["user_industry"] = fallback_answer
                        elif dimension == "user_interest_driver":
                            state["user_interest_driver"] = fallback_answer
                            state["user_expertise_level"] = "intermediate"
                            state["current_phase"] = "crypto_risk"
                        state["answers_received"].append(
                            {
                                "phase": phase_for_processing,
                                "dimension": dimension,
                                "question": question,
                                "answer": fallback_answer,
                                "clarification": True,
                                "forced_accept": True,
                            }
                        )
                        state["needs_clarification"] = False
                        state["clarification_question"] = None
                        state["clarification_retry_count"] = 0
                        await adispatch_custom_event(
                            "tool_progress",
                            {"step": state["step"], "total": total_questions},
                        )
                        return state
                    state["needs_clarification"] = True
                    state["clarification_question"] = hint or "Please provide a clearer answer for this field."
                    return state

                processed = await self._process_answer(
                    phase=phase_for_processing,
                    dimension=dimension,
                    question=question,
                    answer=normalized,
                    context=context,
                )

                if phase_for_processing == "crypto_risk":
                    state["crypto_risk_dimensions"][dimension] = processed
                else:
                    state["quantum_opportunity_dimensions"][dimension] = processed

                state["answers_received"].append(
                    {
                        "phase": phase_for_processing,
                        "dimension": dimension,
                        "question": question,
                        "answer": normalized,
                        "clarification": True,
                    }
                )

                state["needs_clarification"] = False
                state["clarification_question"] = None
                state["clarification_retry_count"] = 0
                await adispatch_custom_event(
                    "tool_progress",
                    {"step": state["step"], "total": total_questions},
                )
                return state

            # Normal question selection: ask exactly one question and suspend.
            if phase == "onboarding":
                if not state.get("user_industry"):
                    state["current_dimension"] = "user_industry"
                    question = "To start, what industry are you working in?"
                    state["questions_asked"].append(question)
                    state["step"] = len(state["questions_asked"])
                    await adispatch_custom_event(
                        "tool_question",
                        {"text": question, "step": state["step"], "input_type": "free_text"},
                    )
                    answer = interrupt(question)
                    normalized = await _rewrite_answer("onboarding", "user_industry", question, answer)
                    if not _raw_answer_grounded("user_industry", answer):
                        ok, hint = _validate_field("onboarding", "user_industry", answer)
                    else:
                        ok, hint = _validate_field("onboarding", "user_industry", normalized)
                    if not ok:
                        state["needs_clarification"] = True
                        state["clarification_question"] = hint or "Please specify your primary industry/sector."
                        return state
                    state["user_industry"] = normalized
                    state["answers_received"].append(
                        {"phase": "onboarding", "question": question, "answer": answer}
                    )
                    await adispatch_custom_event(
                        "tool_progress",
                        {"step": state["step"], "total": total_questions},
                    )
                    return state

                if not state.get("user_interest_driver"):
                    state["current_dimension"] = "user_interest_driver"
                    question = (
                        "What makes you interested in quantum technologies right now for your organization?"
                    )
                    state["questions_asked"].append(question)
                    state["step"] = len(state["questions_asked"])
                    await adispatch_custom_event(
                        "tool_question",
                        {"text": question, "step": state["step"], "input_type": "free_text"},
                    )
                    answer = interrupt(question)
                    normalized = await _rewrite_answer("onboarding", "user_interest_driver", question, answer)
                    if not _raw_answer_grounded("user_interest_driver", answer):
                        ok, hint = _validate_field("onboarding", "user_interest_driver", answer)
                    else:
                        ok, hint = _validate_field("onboarding", "user_interest_driver", normalized)
                    if not ok:
                        state["needs_clarification"] = True
                        state["clarification_question"] = hint or "Briefly state your main motivation (e.g., crypto readiness, optimization)."
                        return state
                    state["user_interest_driver"] = normalized
                    state["user_expertise_level"] = "intermediate"  # default
                    state["current_phase"] = "crypto_risk"
                    state["answers_received"].append(
                        {"phase": "onboarding", "question": question, "answer": answer}
                    )
                    await adispatch_custom_event(
                        "tool_progress",
                        {"step": state["step"], "total": total_questions},
                    )
                    return state

                # Onboarding complete, advance.
                state["current_phase"] = "crypto_risk"
                return state

            if phase == "crypto_risk":
                next_dimension = next(
                    (d for d in required_crypto_dimensions if d not in state["crypto_risk_dimensions"]),
                    None,
                )
                if next_dimension is None:
                    state["current_phase"] = "quantum_opportunity"
                    return state

                state["current_dimension"] = next_dimension
                state["clarification_retry_count"] = 0
                question = await self._generate_question(
                    phase="crypto_risk",
                    dimension=next_dimension,
                    context=state.get("crypto_risk_dimensions", {}),
                    user_context={
                        "industry": state.get("user_industry"),
                        "expertise": state.get("user_expertise_level", "intermediate"),
                    },
                )
                state["questions_asked"].append(question)
                state["step"] = len(state["questions_asked"])
                await adispatch_custom_event(
                    "tool_question",
                    {"text": question, "step": state["step"], "input_type": "free_text"},
                )
                answer = interrupt(question)

                normalized = await _rewrite_answer("crypto_risk", next_dimension, question, answer)
                if not _raw_answer_grounded(next_dimension, answer):
                    ok, hint = _validate_field("crypto_risk", next_dimension, answer)
                else:
                    ok, hint = _validate_field("crypto_risk", next_dimension, normalized)
                if not ok:
                    state["needs_clarification"] = True
                    state["clarification_question"] = hint or f"Please add more detail for {next_dimension.replace('_',' ')}."
                    return state

                processed = await self._process_answer(
                    phase="crypto_risk",
                    dimension=next_dimension,
                    question=question,
                    answer=normalized,
                    context=state.get("crypto_risk_dimensions", {}),
                )
                state["crypto_risk_dimensions"][next_dimension] = processed
                state["answers_received"].append(
                    {
                        "phase": "crypto_risk",
                        "dimension": next_dimension,
                        "question": question,
                        "answer": normalized,
                    }
                )
                await adispatch_custom_event(
                    "tool_progress",
                    {"step": state["step"], "total": total_questions},
                )

                if processed.get("confidence") == "low":
                    state["needs_clarification"] = True
                    state["clarification_question"] = await self._generate_clarification(
                        dimension=next_dimension,
                        original_answer=answer,
                    )
                return state

            if phase == "quantum_opportunity":
                next_dimension = next(
                    (d for d in required_quantum_dimensions if d not in state["quantum_opportunity_dimensions"]),
                    None,
                )
                if next_dimension is None:
                    state["is_complete"] = True
                    state["current_phase"] = "complete"
                    state["step_data"] = {
                        "user_industry": state.get("user_industry"),
                        "user_interest_driver": state.get("user_interest_driver"),
                        "user_expertise_level": state.get("user_expertise_level"),
                        "crypto_risk_dimensions": state.get("crypto_risk_dimensions", {}),
                        "quantum_opportunity_dimensions": state.get("quantum_opportunity_dimensions", {}),
                        "required_fields": self.REQUIRED_FIELDS,
                    }
                    state["tool_status"] = "done"
                    state["tool_output"] = {"step_data": state["step_data"], "is_complete": True}
                    await adispatch_custom_event(
                        "tool_complete",
                        {"tool_name": self.name, "step_data": state["step_data"]},
                    )
                    return state

                state["current_dimension"] = next_dimension
                state["clarification_retry_count"] = 0
                question = await self._generate_question(
                    phase="quantum_opportunity",
                    dimension=next_dimension,
                    context=state.get("quantum_opportunity_dimensions", {}),
                    user_context={
                        "industry": state.get("user_industry"),
                        "expertise": state.get("user_expertise_level", "intermediate"),
                    },
                )
                state["questions_asked"].append(question)
                state["step"] = len(state["questions_asked"])
                await adispatch_custom_event(
                    "tool_question",
                    {"text": question, "step": state["step"], "input_type": "free_text"},
                )
                answer = interrupt(question)

                normalized = await _rewrite_answer("quantum_opportunity", next_dimension, question, answer)
                if not _raw_answer_grounded(next_dimension, answer):
                    ok, hint = _validate_field("quantum_opportunity", next_dimension, answer)
                else:
                    ok, hint = _validate_field("quantum_opportunity", next_dimension, normalized)
                if not ok:
                    state["needs_clarification"] = True
                    state["clarification_question"] = hint or f"Please add more detail for {next_dimension.replace('_',' ')}."
                    return state

                processed = await self._process_answer(
                    phase="quantum_opportunity",
                    dimension=next_dimension,
                    question=question,
                    answer=normalized,
                    context=state.get("quantum_opportunity_dimensions", {}),
                )
                state["quantum_opportunity_dimensions"][next_dimension] = processed
                state["answers_received"].append(
                    {
                        "phase": "quantum_opportunity",
                        "dimension": next_dimension,
                        "question": question,
                        "answer": normalized,
                    }
                )
                await adispatch_custom_event(
                    "tool_progress",
                    {"step": state["step"], "total": total_questions},
                )

                if processed.get("confidence") == "low":
                    state["needs_clarification"] = True
                    state["clarification_question"] = await self._generate_clarification(
                        dimension=next_dimension,
                        original_answer=answer,
                    )
                return state

            # Unknown phase: fail fast.
            state["tool_status"] = "error"
            state["error"] = f"Unknown current_phase: {phase}"
            state["is_complete"] = True
            state["current_phase"] = "complete"
            return state

        def _continue_or_end(s: QuantumDataCollectorState) -> str:
            return END if s.get("is_complete") else "step"

        g = StateGraph(QuantumDataCollectorState)
        g.add_node("step", step)
        g.add_edge(START, "step")
        g.add_conditional_edges("step", _continue_or_end)
        return g.compile()
    
    async def _generate_question(
        self,
        phase: str,
        dimension: str,
        context: Dict,
        user_context: Dict,
    ) -> str:
        """Generate adaptive question using LLM."""
        dimension_questions = {
            "data_sensitivity": [
                "How long does sensitive data need to remain confidential?",
                "What types of sensitive data do you handle?",
                "Do you have data that needs protection for 10+ years?",
            ],
            "crypto_visibility": [
                "Do you know what encryption standards your systems currently use?",
                "Do you have an inventory of where cryptography is used across your infrastructure?",
                "Are you aware of all cryptographic dependencies in your systems?",
            ],
            "migration_progress": [
                "Have you begun using any post-quantum cryptography (PQC) standards?",
                "What is your current migration status for quantum-resistant cryptography?",
                "Have you piloted any PQC implementations?",
            ],
            "compliance_exposure": [
                "Are any of your systems subject to compliance requirements like FIPS, PCI-DSS, or HIPAA?",
                "Do you use any third-party vendors or cloud providers for key management?",
                "What compliance frameworks apply to your cryptographic systems?",
            ],
            "problem_solution_fit": [
                "Do you run large optimization problems?",
                "Do you do molecular simulation, materials research or other applications that inherently possess a quantum nature?",
                "Do you use ML at scale where quantum speedups might apply?",
                "What computational problems are bottlenecks in your operations?",
            ],
            "org_readiness": [
                "Do you have any internal quantum expertise, or would this be outsourced?",
                "Do you have a research or innovation team exploring emerging tech?",
                "What's your typical technology adoption horizon — early adopter or wait-and-see?",
                "How does your organization approach emerging technologies?",
            ],
            "tech_maturity": [
                "Are you currently using HPCs?",
                "What is your current computational infrastructure?",
                "Do you have the data infrastructure to support quantum computing?",
                "What is your current technology stack maturity?",
            ],
            "strategic_horizon": [
                "Do you have a budget allocated for emerging tech or cybersecurity modernization?",
                "What is your strategic planning horizon?",
                "How does quantum fit into your long-term strategy?",
                "What are your priorities for technology investment?",
            ],
        }
        
        prompt = f"""You are a quantum readiness advisor conducting a {phase} assessment.

User context:
- Industry: {user_context.get('industry', 'Unknown')}
- Expertise level: {user_context.get('expertise', 'intermediate')}

Dimension to assess: {dimension}
Available questions for this dimension:
{chr(10).join(f"- {q}" for q in dimension_questions.get(dimension, []))}

What we know so far: {json.dumps(context, indent=2) if context else "Nothing yet"}

Task: Ask ONE clear, conversational question from the list above. Adapt language to {user_context.get('expertise', 'intermediate')} level.

CRITICAL: Return ONLY the question text. No explanations, no bullet points, no markdown formatting, no "Here's a question:" prefix. Just the question itself."""
        
        try:
            response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            question = response.strip()
            if question.startswith("**"):
                question = question.replace("**", "").strip()
            if question.startswith('"') and question.endswith('"'):
                question = question[1:-1].strip()
            # Guardrail: never leak provider/runtime errors as user questions.
            if not question or "llm call failed" in question.lower() or "configuration" in question.lower():
                raise ValueError("Unusable LLM-generated question")
            return question
        except Exception:
            # Stable fallback question if generation fails.
            choices = dimension_questions.get(dimension, [])
            if choices:
                idx = len(context) % len(choices)
                return choices[idx]
            return f"Please provide details for {dimension.replace('_', ' ')}."
    
    async def _process_answer(
        self,
        phase: str,
        dimension: str,
        question: str,
        answer: str,
        context: Dict,
    ) -> Dict:
        """Process user answer and extract score, confidence, and details."""
        prompt = f"""You are analyzing a user's answer for quantum readiness assessment.

Phase: {phase}
Dimension: {dimension}
Question asked: {question}
User's answer: {answer}

Context so far: {json.dumps(context, indent=2) if context else "None"}

Task: Analyze the answer and extract:
1. A normalized score (0-100) for this dimension
2. Confidence level (high/medium/low)
3. Key details extracted from the answer

Return JSON:
{{
    "score": 75,  // 0-100
    "confidence": "medium",  // "high" | "medium" | "low"
    "details": "User indicated they handle financial data with 10+ year retention requirements..."
}}

If the answer is vague or unclear, mark confidence as "low"."""
        
        response = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        
        try:
            # Try to parse JSON from response
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                result = json.loads(json_str)
            else:
                # Fallback if no JSON
                result = {
                    "score": 50,
                    "confidence": "low",
                    "details": answer,
                }
        except json.JSONDecodeError:
            result = {
                "score": 50,
                "confidence": "low",
                "details": answer,
            }
        
        return result
    
    async def _generate_clarification(
        self,
        dimension: str,
        original_answer: str,
    ) -> str:
        """Generate a clarification question if answer was unclear."""
        prompt = f"""The user gave an unclear answer about {dimension}: "{original_answer}"

Generate a follow-up clarification question to get more specific information.

CRITICAL: Return ONLY the question text. No explanations, no bullet points, no markdown formatting. Just the question itself."""
        
        response = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        
        question = response.strip()
        if question.startswith("**"):
            question = question.replace("**", "").strip()
        if question.startswith('"') and question.endswith('"'):
            question = question[1:-1].strip()
        
        return question
