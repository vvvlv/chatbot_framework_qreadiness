"""
Quantum Readiness Data Collection Tool - Layer 3.
"""

import json
import os
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
    section_intro: str
    atomic_questions: List[str]
    answer_criteria: str
    example_answers: List[str]


class QuantumDataCollectorState(TypedDict, total=False):
    messages: list[Dict]
    field_status: Dict[str, str]
    last_user_answer: Optional[str]
    message_count: int
    iterations_count: Dict[str, int]
    field_information: Dict[str, str]
    user_command: Optional[str]
    current_field_key: Optional[str]
    pending_question: Optional[str]
    pending_clarification_question: Optional[str]
    consumed_prompt_ids: List[str]
    last_validation_reason: Optional[str]
    current_question_index: Dict[str, int]
    section_intro_sent: Dict[str, bool]
    clarification_count_by_question: Dict[str, int]
    manual_clarify_count_by_question: Dict[str, int]
    awaiting_clarification: bool
    last_question_kind: Optional[str]
    post_collection_stage: int
    company_name_for_report: Optional[str]
    report_save_opt_out: bool
    transition_feedback: Optional[str]
    step: int


class QuantumDataCollectorTool(SubgraphProtocol):
    name = "quantum_data_collector"
    VALIDATOR_MODEL = os.getenv(
        "VALIDATOR_MODEL",
        os.getenv("LITELLM_DEFAULT_MODEL") or os.getenv("LLM_MODEL", "claude-haiku-4-5"),
    )

    FIELD_SPECS: List[FieldSpec] = [
        {
            "key": "a_use_case_identification",
            "explanation": "Branch A topic: use case identification (industry, computationally intensive problems, optimization, intrinsic quantum use cases, classical bottlenecks).",
            "section_intro": "Let us start by identifying your use case so we can anchor the assessment in your business reality.",
            "atomic_questions": [
                "What industry are you in, and what are your most computationally intensive business problems?",
                "Do you run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation)?",
                "Do you conduct molecular simulation, materials science, drug discovery research, or any other research that has an intrinsic quantum nature?",
            ],
            "answer_criteria": "Provide industry context plus at least one concrete high-compute or quantum-relevant use case.",
            "example_answers": [
                "Healthcare: drug discovery simulation and route optimization with long runtimes.",
                "Finance: portfolio optimization bottlenecks in intraday decisions.",
            ],
        },
        {
            "key": "a_technical_infrastructure_baseline",
            "explanation": "Branch A topic: technical and infrastructure baseline (HPC/cloud footprint, classical baselines, vendor relationships, internal expertise).",
            "section_intro": "Now I would like to understand your current technical baseline and delivery capacity.",
            "atomic_questions": [
                "Do you currently implement state-of-the-art classical solutions for the problems you are trying to solve?",
                "Do you have internal quantum expertise, or would any engagement depend entirely on external partners?",
            ],
            "answer_criteria": "Describe current technical baseline and capability level across infrastructure, tooling, and expertise.",
            "example_answers": [
                "Hybrid HPC + cloud, mature classical optimizers, early vendor pilots, small internal team.",
                "Cloud-only stack, no vendor ties, external partners required for quantum work.",
            ],
        },
        {
            "key": "a_strategic_organizational_maturity",
            "explanation": "Branch A topic: strategic and organizational maturity (adoption posture, IP sensitivity, dedicated budget).",
            "section_intro": "Next, let us look at organizational strategy and how innovation decisions are made internally.",
            "atomic_questions": [
                "What is your organization's typical technology adoption posture (first mover, second mover, wait-and-see)?",
                "Is your product or service protected by IP regulations?",
            ],
            "answer_criteria": "Provide posture, governance/budget context, and strategic readiness indicators.",
            "example_answers": [
                "Second-mover posture, strong IP portfolio, dedicated exploration budget.",
                "Wait-and-see posture, limited IP pressure, no dedicated budget.",
            ],
        },
        {
            "key": "a_roadmap_ecosystem",
            "explanation": "Branch A topic: roadmap and ecosystem (internal pilots, ecosystem participation, competitor monitoring).",
            "section_intro": "Finally, I want to understand your roadmap signal and external ecosystem positioning.",
            "atomic_questions": [
                "Have you conducted any internal assessments or pilots related to quantum computing use cases?",
                "Are you participating in any quantum ecosystem networks, consortia, or academic partnerships?",
            ],
            "answer_criteria": "Include execution roadmap signals and ecosystem engagement level.",
            "example_answers": [
                "Active pilots, consortium membership, and quarterly competitor intelligence.",
                "No pilots yet, limited ecosystem ties, informal monitoring only.",
            ],
        },
    ]

    RUBRIC_SPEC_BY_FIELD: Dict[str, Dict[str, Any]] = {
        "a_use_case_identification": {
            "output_key": "use_case_identification",
            "rubrics": {
                "industry": "Industry/sector the organization operates in.",
                "core_compute_problem": "Main computationally intensive business problems.",
                "optimization": "Whether large-scale combinatorial optimization is present.",
                "intrinsic_quantum": "Whether there are intrinsically quantum research workloads.",
            },
        },
        "a_technical_infrastructure_baseline": {
            "output_key": "technical_infrastructure_baseline",
            "rubrics": {
                "classical_maturity": "Current state-of-the-art classical baseline maturity.",
                "internal_expertise": "In-house quantum expertise versus external dependency.",
            },
        },
        "a_strategic_organizational_maturity": {
            "output_key": "strategic_organizational_maturity",
            "rubrics": {
                "adoption_posture": "Technology adoption posture regarding emerging tech.",
                "ip_sensitivity": "IP/data sensitivity and partner constraints.",
            },
        },
        "a_roadmap_ecosystem": {
            "output_key": "roadmap_ecosystem",
            "rubrics": {
                "internal_pilots": "Internal quantum assessments or pilots.",
                "ecosystem_partnerships": "Participation in quantum ecosystem networks/consortia/academia.",
            },
        },
    }

    SYSTEM_PROMPT = f"""
SYSTEM PROMPT : 
You are a professional quantum assistant that helps managers to assess the quantum readiness of their company/structure.
Your first step is to gather the information necessary for this assessment.
More precisely, your goal is to identify the user's information according to 4 fields, described by the following attributes :
- "key" : a string to identify the field
- "explanation": an explanation of the field
- "section_intro": a short conversational intro used before asking questions in the field
- "atomic_questions": an ordered list of focused questions asked one-by-one
- "answer_criteria": what information is needed to consider the field as complete
- "example_answers": a list of example user answers that fill the information needed for the field

Here are the 4 fields :

{json.dumps(FIELD_SPECS)}

I will update you on the information status for each field after every user message, and tell you what is the current field to focus on.
Your main objective is always to get more information from the user about the current field, but you can help them to better understand technical terms if they need.
"""
    TOTAL_STEPS = 4
    MAX_RETRIES_PER_FIELD = 5
    FINAL_COMPANY_NAME_QUESTION = (
        "Before I generate your report, would you like to provide a company name to display in it? "
        "If yes, type the exact name. If not, type 'skip'."
    )
    FINAL_REPORT_SAVE_OPT_OUT_QUESTION = (
        "Final privacy preference: do you want to opt out of saving this final report in our database? "
        "Please answer yes (opt out) or no (allow saving)."
    )

    def __init__(self, model_gateway: ModelGateway, interrupt_tool: ToolProtocol):
        self._model_gateway = model_gateway
        self._interrupt_tool = interrupt_tool

    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."

    def build(self):
        g = StateGraph(SubgraphState)
        g.add_node("init_state", self.init_node)
        g.add_node("generate_question", self.generate_question_node)
        g.add_node("interrupt", self._interrupt_tool.build())
        g.add_node("process_answer", self.process_answer_node)
        g.add_node("command_handler", self.command_handler_node)
        g.add_node("get_information", self.get_information_node)
        g.add_node("before_analyzer", self.before_analyzer_node)

        g.add_edge(START, "init_state")
        g.add_edge("init_state", "generate_question")
        g.add_edge("generate_question", "interrupt")
        g.add_edge("interrupt", "process_answer")
        g.add_conditional_edges(
            "process_answer",
            self.router,
            {"command_handler": "command_handler", "get_information": "get_information", "generate_question": "generate_question"},
        )
        g.add_conditional_edges(
            "command_handler",
            self.router,
            {END: END, "before_analyzer": "before_analyzer", "get_information": "get_information", "generate_question": "generate_question"},
        )
        g.add_conditional_edges(
            "get_information",
            self.router,
            {"before_analyzer": "before_analyzer", "generate_question": "generate_question"},
        )
        g.add_edge("before_analyzer", END)
        return g.compile()

    async def router(self, state: SubgraphState) -> str:
        print("[ROUTER]: debug nextNode : ", state.get("nextNode"))
        return state.get("nextNode")

    async def init_node(self, state: SubgraphState) -> SubgraphState:
        last_5_messages = []
        for msg in state.get("messages", [])[-5:]:
            role = "user" if hasattr(msg, "type") and msg.type == "human" else "assistant"
            content = msg.content if hasattr(msg, "content") else str(msg)
            last_5_messages.append({"role": role, "content": content})

        stepData: QuantumDataCollectorState = {
            "messages": last_5_messages,
            "field_status": {field["key"]: "empty" for field in self.FIELD_SPECS},
            "last_user_answer": None,
            "message_count": 0,
            "iterations_count": {field["key"]: 0 for field in self.FIELD_SPECS},
            "field_information": {field["key"]: "" for field in self.FIELD_SPECS},
            "consumed_prompt_ids": [],
            "last_validation_reason": None,
            "pending_question": None,
            "pending_clarification_question": None,
            "user_command": None,
            "current_field_key": "a_use_case_identification",
            "current_question_index": {field["key"]: 0 for field in self.FIELD_SPECS},
            "section_intro_sent": {field["key"]: False for field in self.FIELD_SPECS},
            "clarification_count_by_question": {},
            "manual_clarify_count_by_question": {},
            "awaiting_clarification": False,
            "last_question_kind": None,
            "post_collection_stage": 0,
            "company_name_for_report": None,
            "report_save_opt_out": False,
            "transition_feedback": None,
            "step": 1,
        }

        state["currentStep"] = "collecting"
        state["nextNode"] = "generate_question"
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
                "system_prompt": self.SYSTEM_PROMPT,
                "skip_command": "/skip",
                "clarify_command": "/clarify",
            },
        )
        return state

    async def generate_question_node(self, state: SubgraphState) -> SubgraphState:
        prompt_id = state.get("pending_prompt_id") or str(uuid.uuid4())
        state["pending_prompt_id"] = prompt_id
        transition_feedback = state["stepData"].get("transition_feedback")
        if state["stepData"].get("pending_question") is not None:
            question = state["stepData"]["pending_question"]
        else:
            field_key = state["stepData"].get("current_field_key")
            field_spec = self._field_spec_by_key(field_key)
            question_index = state["stepData"]["current_question_index"].get(field_key, 0)
            question_index = max(0, min(question_index, len(field_spec["atomic_questions"]) - 1))
            state["stepData"]["current_question_index"][field_key] = question_index

            if state["stepData"].get("awaiting_clarification"):
                question = (
                    state["stepData"].get("pending_clarification_question")
                    or self._fallback_clarification_question(field_spec["atomic_questions"][question_index])
                )
                state["stepData"]["last_question_kind"] = "clarification"
            else:
                base_question = field_spec["atomic_questions"][question_index].strip()
                base_question = self._slight_question_variation(state["stepData"], field_key, base_question)
                section_intro = ""
                if not state["stepData"]["section_intro_sent"].get(field_key, False):
                    section_intro = field_spec["section_intro"].strip()
                    state["stepData"]["section_intro_sent"][field_key] = True
                question = f"{section_intro}\n\n{base_question}" if section_intro else base_question
                state["stepData"]["last_question_kind"] = "main"

            if transition_feedback and state["stepData"].get("last_question_kind") == "main":
                question = f"{transition_feedback}\n\n{question}"
                state["stepData"]["transition_feedback"] = None
            question = (question or "").strip()
            state["stepData"]["messages"].append({"role": "assistant", "content": question})
            state["stepData"]["pending_question"] = question
            state["stepData"]["message_count"] += 1

        print(f"[DATA_COLLECTOR] DEBUG - used question : {question[:100]}")
        state["common_tool_input"] = {
            "nextNode": "process_answer",
            "args": {
                "event_name": "tool_question",
                "text": question,
                "prompt_id": prompt_id,
                "input_type": "free_text",
                "can_skip": True,
            },
        }
        state["nextNode"] = "interrupt"
        return state

    async def process_answer_node(self, state: SubgraphState) -> SubgraphState:
        resume_prompt_id = None
        prompt_id = state.get("pending_prompt_id")
        answer = state["common_tool_output"].get("answer")
        state["stepData"]["message_count"] += 1
        if isinstance(answer, dict):
            raw_answer = str(answer.get("text", "")).strip()
            resume_prompt_id = answer.get("prompt_id")
        else:
            raw_answer = str(answer or "").strip()
        state["stepData"]["last_user_answer"] = raw_answer
        if resume_prompt_id and resume_prompt_id != prompt_id:
            print("[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Stale prompt answer received."
            state["nextNode"] = "generate_question"
            return state
        if prompt_id in state["stepData"]["consumed_prompt_ids"]:
            print("[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Duplicate prompt answer ignored."
            state["nextNode"] = "generate_question"
            return state
        state["stepData"]["pending_question"] = None
        state["stepData"]["consumed_prompt_ids"].append(prompt_id)

        command = self._normalized_command(raw_answer)
        if command is None:
            state["nextNode"] = "get_information"
        else:
            state["nextNode"] = "command_handler"
            state["stepData"]["user_command"] = command
        return state

    async def command_handler_node(self, state: SubgraphState) -> SubgraphState:
        command = state["stepData"].get("user_command")
        field_key = state["stepData"].get("current_field_key")

        if command == "/cancel":
            state["error"] = "Tool cancelled by user."
            state["output"] = (
                "Understood. The conversation has been ended. If you'd like to start a new session or need any assistance, don't hesitate to reach out."
            )
            state["currentStep"] = "Idle"
            state["stepData"] = {}
            state["common_tool_input"] = {}
            state["common_tool_output"] = {}
            state["pending_prompt_id"] = None
            await adispatch_custom_event("tool_complete", {"tool_name": self.name})
            state["nextNode"] = END
            return state

        if command == "/skip":
            if state["stepData"].get("post_collection_stage", 0) > 0:
                self._apply_post_collection_skip(state["stepData"])
                state["pending_prompt_id"] = None
                state["nextNode"] = "before_analyzer" if state["stepData"].get("post_collection_stage", 0) >= 3 else "generate_question"
                return state

            state["stepData"]["field_status"][field_key] = "complete"
            state["stepData"]["field_information"][field_key] += "The user skipped aditional data collection for this field."
            field_spec = self._field_spec_by_key(field_key)
            state["stepData"]["current_question_index"][field_key] = len(field_spec["atomic_questions"])
            state["stepData"]["awaiting_clarification"] = False
            state["stepData"]["pending_clarification_question"] = None
            next_field, step = self._next_unfilled_key(state["stepData"]["field_status"])
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = None
            if next_field is None:
                self._start_post_collection(state["stepData"])
                state["nextNode"] = "generate_question"
                return state
            state["stepData"]["transition_feedback"] = await self._build_transition_feedback(
                state["stepData"], field_key, next_field
            )
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            state["nextNode"] = "generate_question"
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS})
            return state

        if command == "/clarify":
            state["pending_prompt_id"] = None
            if state["stepData"].get("post_collection_stage", 0) > 0:
                current_question = self._latest_assistant_question(state["stepData"].get("messages", []))
                state["stepData"]["pending_question"] = await self._auto_clarify_question_for_user(current_question)
                state["stepData"]["last_question_kind"] = "main"
                state["nextNode"] = "generate_question"
                return state

            current_question = self._get_current_atomic_question(state["stepData"], field_key)
            question_instance_key = self._question_instance_key(state["stepData"], field_key)
            clarify_count = state["stepData"]["manual_clarify_count_by_question"].get(question_instance_key, 0)
            preset_clarification = self._preset_clarification_for_question(current_question)
            if clarify_count == 0 and preset_clarification:
                state["stepData"]["pending_question"] = preset_clarification
            else:
                clarified = await self._auto_clarify_question_for_user(current_question)
                # Keep repeated clarify requests helpful and polite, never scolding.
                if clarify_count >= 1:
                    clarified = (
                        "Of course, I'm happy to clarify.\n\n"
                        f"{clarified}\n\n"
                        "If helpful, a short answer is enough."
                    )
                state["stepData"]["pending_question"] = clarified
            state["stepData"]["manual_clarify_count_by_question"][question_instance_key] = clarify_count + 1
            state["stepData"]["last_question_kind"] = "main"
            state["nextNode"] = "generate_question"
            return state

        if command == "/aicompletion":
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = await self._ai_completion(state["stepData"])
            await adispatch_custom_event("ai_completion", {"text": state["stepData"]["last_user_answer"]})
            state["nextNode"] = "get_information"
            return state

        # Secret shortcut: skip remaining questions and proceed with collected data.
        if command == "/skip_questions":
            state["pending_prompt_id"] = None
            state["stepData"]["post_collection_stage"] = 3
            state["stepData"]["pending_question"] = None
            await adispatch_custom_event("tool_progress", {"step": self.TOTAL_STEPS, "total": self.TOTAL_STEPS})
            state["nextNode"] = "before_analyzer"
            return state

        state["nextNode"] = "generate_question"
        return state

    async def get_information_node(self, state: SubgraphState) -> SubgraphState:
        if state["stepData"].get("post_collection_stage", 0) > 0:
            await self._handle_post_collection_response(state["stepData"])
            state["pending_prompt_id"] = None
            state["nextNode"] = "before_analyzer" if state["stepData"].get("post_collection_stage", 0) >= 3 else "generate_question"
            return state

        current_field = state["stepData"]["current_field_key"]
        current_atomic_question = self._get_current_atomic_question(state["stepData"], current_field)
        last_question_kind = state["stepData"].get("last_question_kind", "main")
        information_status = self._write_information_status(state["stepData"])
        main_prompt = f"""
Your task now is to extract relevant information from the user answer in order to fill the 4 quantum readiness fields described in your system prompt.

Here is a summary of the information already extracted for each field :

{information_status}

The field currently being discussed in the conversation is : {current_field}
The concrete question asked to the user was : {current_atomic_question}
The question type was : {last_question_kind}
Your last message was : {state['stepData']['messages'][-1]["content"]}
The user answered : {state['stepData']['last_user_answer']}
"""

        task1_prompt = f"""Extract relevant information for the current field from the user answer, based on the current field attributes and this specific question: {current_atomic_question}
Treat short direct answers like "yes", "no", or "not yet" as relevant information when they clearly answer the question.
If there is no relevant information, just return 'no information'.
Do not include markdown, code fences, or extra keys.
"""
        step_messages = [
            {"role": "user", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": main_prompt},
            {"role": "user", "content": task1_prompt},
        ]
        raw = await self._model_gateway.chat(messages=step_messages, model=self.VALIDATOR_MODEL, temperature=0.2)
        text = (raw or "").strip()
        if self._is_no_information(text):
            short_answer_info = self._short_answer_information(current_atomic_question, state["stepData"].get("last_user_answer"))
            if short_answer_info:
                text = short_answer_info
        print(f"[DATA_COLLECTOR] DEBUG - Output task 1 : {text}")

        task2_prompt = f"""Merge the information you found ({text}) with the already extracted information of the current field ({state['stepData']['field_information'][current_field]}) into a single text summary.
Return a concise non-redundant summary (maximum 90 words).
Do not include markdown, code fences, or extra keys.
"""
        step_messages += [{"role": "assistant", "content": text}, {"role": "user", "content": task2_prompt}]
        raw = await self._model_gateway.chat(messages=step_messages, model=self.VALIDATOR_MODEL, temperature=0.2)
        text = self._compact_information_summary((raw or "").strip())
        print(f"[DATA_COLLECTOR] DEBUG - Output task 2 : {text}")
        state["stepData"]["field_information"][current_field] = text

        output3_format = {"type": "object", "properties": {"status": {"type": "string", "enum": ["empty", "in_progress", "complete"]}}}
        task3_prompt = f"""Based on the new information summary for the current field and the answer criteria of the current field,
indicate wether the current field is 'empty' (no user information extracted for this field), 'in_progress' (some user information but not enough) or 'complete' (there is enough user information for this field).
Output STRICT JSON with this schema:
{output3_format}
"""
        step_messages += [{"role": "assistant", "content": text}, {"role": "user", "content": task3_prompt}]
        raw = await self._model_gateway.chat(messages=step_messages, model=self.VALIDATOR_MODEL, temperature=0.1)
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 3 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            status = data.get("status")
            if status in {"empty", "in_progress", "complete"}:
                if status == "complete" or state["stepData"]["field_status"][current_field] != "complete":
                    state["stepData"]["field_status"][current_field] = status
        except Exception:
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 3 output has failed.")

        output4_format = {
            "type": "object",
            "properties": {
                "list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "new_information_summary": {"type": "string"},
                            "new_status": {"type": "string", "enum": ["empty", "in_progress", "complete"]},
                        },
                        "required": ["key", "new_information_summary", "new_status"],
                    },
                }
            },
            "required": ["list"],
        }
        task4_prompt = f"""Based on the fields specifications, determine if the user answer contains relevant information for some fields other than the current field.
Update the information summary of the concerned fields with the user answer.
Compare the new information summary of the concerned fields with their answer criteria. For each field, if there is enough information, set the field status to "complete". If there is not enough information and the field was "empty", set the field status to "in_progress"
Return the list of the concerned fields, with their key, their new information summary and their new status.
Output STRICT JSON with this schema:
{output4_format}
"""
        step_messages += [{"role": "assistant", "content": text}, {"role": "user", "content": task4_prompt}]
        raw = await self._model_gateway.chat(messages=step_messages, model=self.VALIDATOR_MODEL, temperature=0.2)
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 4 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            data_list = data.get("list") or []
            for item in data_list:
                item_key = item.get("key")
                if item_key != current_field and state["stepData"]["field_status"].get(item_key) != "complete":
                    state["stepData"]["field_status"][item_key] = item.get("new_status") or state["stepData"]["field_status"][item_key]
                    compact_summary = self._compact_information_summary(
                        item.get("new_information_summary") or state["stepData"]["field_information"][item_key]
                    )
                    state["stepData"]["field_information"][item_key] = compact_summary
            if not data_list:
                self._apply_cross_field_heuristics(state["stepData"], current_field)
        except Exception:
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 4 output has failed.")

        should_clarify = False
        clarification_question = None
        question_instance_key = self._question_instance_key(state["stepData"], current_field)
        clarification_count = state["stepData"]["clarification_count_by_question"].get(question_instance_key, 0)
        if (
            last_question_kind == "main"
            and clarification_count < 1
            and state["stepData"]["field_status"].get(current_field) != "complete"
        ):
            should_clarify, clarification_question = await self._clarification_decision(
                current_question=current_atomic_question,
                user_answer=state["stepData"]["last_user_answer"],
                extracted_information=state["stepData"]["field_information"][current_field],
            )

        if should_clarify:
            state["stepData"]["awaiting_clarification"] = True
            state["stepData"]["pending_clarification_question"] = clarification_question
            state["stepData"]["clarification_count_by_question"][question_instance_key] = clarification_count + 1
            state["pending_prompt_id"] = None
            state["nextNode"] = "generate_question"
            self._log_model_quality_debug(state=state, current_field=current_field)
            return state

        state["stepData"]["awaiting_clarification"] = False
        state["stepData"]["pending_clarification_question"] = None
        state["stepData"]["iterations_count"][current_field] += 1
        self._advance_current_question(state["stepData"], current_field)
        current_index = state["stepData"]["current_question_index"].get(current_field, 0)
        field_spec = self._field_spec_by_key(current_field)
        if current_index > 0 and state["stepData"]["field_status"][current_field] == "empty":
            state["stepData"]["field_status"][current_field] = "in_progress"

        state["pending_prompt_id"] = None
        if (
            state["stepData"]["field_status"].get(current_field) == "complete"
            or current_index >= len(field_spec["atomic_questions"])
            or state["stepData"]["iterations_count"][current_field] >= self.MAX_RETRIES_PER_FIELD
        ):
            state["stepData"]["field_status"][current_field] = "complete"
            next_field, step = self._next_unfilled_key(state["stepData"]["field_status"])
            if next_field is None:
                self._start_post_collection(state["stepData"])
                state["nextNode"] = "generate_question"
                self._log_model_quality_debug(state=state, current_field=current_field)
                return state
            state["stepData"]["transition_feedback"] = await self._build_transition_feedback(
                state["stepData"], current_field, next_field
            )
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS})
        self._log_model_quality_debug(state=state, current_field=current_field)
        state["nextNode"] = "generate_question"
        return state

    async def before_analyzer_node(self, state: SubgraphState) -> SubgraphState:
        collected = state["stepData"].get("field_information", {})
        branch_a_topics = await self._build_branch_a_topics(collected)

        step_data = {
            "user_industry": collected.get("a_use_case_identification", ""),
            "branch_a_topics": branch_a_topics,
            "fields": collected,
            "company_name_for_report": state["stepData"].get("company_name_for_report"),
            "report_save_opt_out": bool(state["stepData"].get("report_save_opt_out", False)),
        }
        await adispatch_custom_event("tool_complete", {"tool_name": self.name, "step_data": step_data})
        state["stepData"] = step_data
        state["nextNode"] = "analyzer"
        return state

    async def _build_branch_a_topics(self, collected: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        branch_topics: Dict[str, Dict[str, str]] = {}
        for field_key, spec in self.RUBRIC_SPEC_BY_FIELD.items():
            output_key = spec["output_key"]
            summary = collected.get(field_key, "")
            rubrics = await self._extract_rubrics_for_field(field_key, summary)
            branch_topics[output_key] = rubrics
        return branch_topics

    async def _extract_rubrics_for_field(self, field_key: str, field_summary: str) -> Dict[str, str]:
        spec = self.RUBRIC_SPEC_BY_FIELD.get(field_key, {})
        rubric_defs = spec.get("rubrics", {})
        fallback = {rubric: "" for rubric in rubric_defs.keys()}
        if not rubric_defs:
            return fallback

        if not str(field_summary or "").strip():
            return fallback

        output_format = {
            "type": "object",
            "properties": {rubric: {"type": "string"} for rubric in rubric_defs.keys()},
            "required": list(rubric_defs.keys()),
        }
        prompt = f"""You are mapping a collected field summary into rubric-specific summaries.

Field key: {field_key}
Field summary: {field_summary}

Rubric definitions:
{json.dumps(rubric_defs)}

Instructions:
- For each rubric, return a concise summary strictly based on the field summary.
- If there is no evidence for a rubric, return an empty string for that rubric.
- Do not invent facts.
- Output STRICT JSON with this schema:
{json.dumps(output_format)}
"""
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.VALIDATOR_MODEL,
                temperature=0.1,
            )
            text = (raw or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            parsed = json.loads(text[start:end]) if start >= 0 and end > start else {}
            result = {}
            for rubric in rubric_defs.keys():
                value = parsed.get(rubric, "")
                result[rubric] = self._compact_information_summary(str(value), max_words=40) if value else ""
            result = self._apply_rubric_heuristics(field_key, field_summary, result)
            if all(not v for v in result.values()):
                first_rubric = next(iter(rubric_defs.keys()))
                result[first_rubric] = self._compact_information_summary(field_summary, max_words=40)
            return result
        except Exception:
            first_rubric = next(iter(rubric_defs.keys()))
            fallback[first_rubric] = self._compact_information_summary(field_summary, max_words=40)
            return self._apply_rubric_heuristics(field_key, field_summary, fallback)

    def _field_spec_by_key(self, field_key: Optional[str]) -> FieldSpec:
        for field in self.FIELD_SPECS:
            if field["key"] == field_key:
                return field
        return self.FIELD_SPECS[0]

    def _get_current_atomic_question(self, stepData: QuantumDataCollectorState, field_key: Optional[str]) -> str:
        field_spec = self._field_spec_by_key(field_key)
        questions = field_spec["atomic_questions"]
        question_index = stepData.get("current_question_index", {}).get(field_spec["key"], 0)
        question_index = max(0, min(question_index, len(questions) - 1))
        return questions[question_index]

    def _question_instance_key(self, stepData: QuantumDataCollectorState, field_key: Optional[str]) -> str:
        resolved_field_key = field_key or ""
        question_index = stepData.get("current_question_index", {}).get(resolved_field_key, 0)
        return f"{resolved_field_key}:{question_index}"

    def _advance_current_question(self, stepData: QuantumDataCollectorState, field_key: Optional[str]) -> None:
        resolved_field_key = field_key or ""
        field_spec = self._field_spec_by_key(resolved_field_key)
        current_idx = stepData.get("current_question_index", {}).get(resolved_field_key, 0)
        max_idx = len(field_spec["atomic_questions"])
        stepData["current_question_index"][resolved_field_key] = min(current_idx + 1, max_idx)

    def _slight_question_variation(self, stepData: QuantumDataCollectorState, field_key: Optional[str], question: str) -> str:
        base = (question or "").strip()
        if not base:
            return base
        key = field_key or ""
        seed = (
            stepData.get("current_question_index", {}).get(key, 0)
            + stepData.get("iterations_count", {}).get(key, 0)
            + int(stepData.get("message_count", 0) or 0)
        ) % 4
        if seed == 0:
            return base
        if seed == 1:
            return f"Quick check: {base[0].lower() + base[1:]}" if len(base) > 1 else f"Quick check: {base}"
        if seed == 2:
            return f"{base} (A short answer is fine.)"
        return f"Briefly, {base[0].lower() + base[1:]}" if len(base) > 1 else f"Briefly, {base}"

    async def _build_transition_feedback(
        self,
        step_data: QuantumDataCollectorState,
        completed_field: Optional[str],
        next_field: Optional[str],
    ) -> str:
        field_labels = {
            "a_use_case_identification": "your use cases",
            "a_technical_infrastructure_baseline": "your technical baseline",
            "a_strategic_organizational_maturity": "organizational strategy",
            "a_roadmap_ecosystem": "roadmap and ecosystem",
        }
        done = field_labels.get(completed_field or "", "this section")
        nxt = field_labels.get(next_field or "", "the next section")
        done_info = self._compact_information_summary(
            step_data.get("field_information", {}).get(completed_field or "", ""),
            max_words=22,
        )
        prompt = f"""Write one short conversational transition sentence (maximum 16 words).

Context:
- Completed section: {done}
- Next section: {nxt}
- What we captured: {done_info or "enough information collected"}

Rules:
- Sound natural and friendly.
- Acknowledge completion briefly.
- Mention moving to the next section.
- Exactly one sentence.
- No markdown.
"""
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.VALIDATOR_MODEL,
                temperature=0.3,
            )
            text = " ".join((raw or "").strip().replace("\n", " ").split())
            text = text.replace("**", "").strip().strip('"')
            if not text:
                return f"Great, that gives me enough on {done}. Let us move to {nxt}."
            if text.count("?") > 1:
                text = f"{text.split('?', 1)[0].strip()}?"
            if len(text.split()) > 16:
                text = " ".join(text.split()[:16]).rstrip(",;:")
                if not text.endswith("."):
                    text += "."
            return text
        except Exception:
            return f"Great, that gives me enough on {done}. Let us move to {nxt}."

    def _fallback_clarification_question(self, current_question: str) -> str:
        return "Thanks, that helps. Could you add one concrete detail so I can capture this accurately?\n\n" + current_question

    def _start_post_collection(self, step_data: QuantumDataCollectorState) -> None:
        if step_data.get("post_collection_stage", 0) > 0:
            return
        step_data["post_collection_stage"] = 1
        step_data["pending_question"] = self.FINAL_COMPANY_NAME_QUESTION
        step_data["last_question_kind"] = "main"
        step_data["current_field_key"] = None

    def _apply_post_collection_skip(self, step_data: QuantumDataCollectorState) -> None:
        stage = int(step_data.get("post_collection_stage", 0) or 0)
        if stage == 1:
            step_data["company_name_for_report"] = None
            step_data["post_collection_stage"] = 2
            step_data["pending_question"] = self.FINAL_REPORT_SAVE_OPT_OUT_QUESTION
            return
        if stage == 2:
            step_data["report_save_opt_out"] = False
            step_data["post_collection_stage"] = 3
            step_data["pending_question"] = None

    async def _handle_post_collection_response(self, step_data: QuantumDataCollectorState) -> None:
        stage = int(step_data.get("post_collection_stage", 0) or 0)
        answer = str(step_data.get("last_user_answer", "") or "").strip()
        normalized = " ".join(answer.lower().split())
        if stage == 1:
            user_context = str(step_data.get("field_information", {}).get("a_use_case_identification", "") or "")
            step_data["company_name_for_report"] = await self._extract_company_name(answer, normalized, user_context)
            step_data["post_collection_stage"] = 2
            step_data["pending_question"] = self.FINAL_REPORT_SAVE_OPT_OUT_QUESTION
            return
        if stage == 2:
            step_data["report_save_opt_out"] = self._is_affirmative_opt_out(normalized)
            step_data["post_collection_stage"] = 3
            step_data["pending_question"] = None

    async def _extract_company_name(self, raw_answer: str, normalized_answer: str, user_context: str) -> Optional[str]:
        if not raw_answer:
            return None
        skip_values = {"skip", "no", "none", "n/a", "prefer not to say", "no thanks", "not now"}
        if normalized_answer in skip_values or normalized_answer in {"yes", "sure", "ok", "okay"}:
            return None
        prompt = f"""Decide whether the user answer contains a company name for report display.

User answer: {raw_answer}
Known context: {user_context}

Return STRICT JSON:
{{
  "company_name": "<name or unknown>",
  "is_valid_company_name": true/false
}}

Rules:
- If answer is refusal, preference, explanation, or sentence not giving a company name, set unknown/false.
- If a company name is present, extract only the name.
- No markdown.
"""
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.VALIDATOR_MODEL,
                temperature=0.0,
            )
            text = (raw or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end]) if start >= 0 and end > start else {}
            company_name = " ".join(str(data.get("company_name", "")).strip().split()).strip("\"'")
            is_valid = bool(data.get("is_valid_company_name", False))
            if not is_valid or not company_name or company_name.lower() == "unknown":
                return None
            return company_name[:120]
        except Exception:
            return None

    def _is_affirmative_opt_out(self, normalized_answer: str) -> bool:
        positive = {"yes", "y", "opt out", "please opt out", "do not save", "don't save", "no save"}
        negative = {"no", "n", "save", "allow saving", "you can save", "do save"}
        if normalized_answer in positive:
            return True
        if normalized_answer in negative:
            return False
        return False

    def _preset_clarification_for_question(self, current_question: str) -> Optional[str]:
        q = (current_question or "").strip()
        question_map = {
            "What industry are you in, and what are your most computationally intensive business problems?": "To make this concrete, what industry are you in, and which one or two tasks consume the most computing time or cost today?",
            "Do you run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation)?": "In simple terms, do you solve complex decision problems where you must find the best option among many combinations, such as routing, scheduling, or portfolio construction?",
            "Do you conduct molecular simulation, materials science, drug discovery research, or any other research that has an intrinsic quantum nature?": "Do you do science-heavy R&D like molecular simulation, materials science, or drug discovery where quantum behavior is directly part of the problem?",
            "Do you currently implement state-of-the-art classical solutions for the problems you are trying to solve?": "By this I mean: are you already using the strongest non-quantum methods available today for these problems, such as advanced solvers, optimized ML models, or HPC workflows?",
            "Do you have internal quantum expertise, or would any engagement depend entirely on external partners?": "Do you currently have in-house people with quantum skills, or would you need outside consultants and vendors to do most of the work?",
            "What is your organization's typical technology adoption posture (first mover, second mover, wait-and-see)?": "How does your organization usually adopt new technology: early adopter, fast follower, or only after solutions are proven?",
            "Is your product or service protected by IP regulations?": "Are your products or services protected by patents, trade secrets, or strict IP/legal constraints?",
            "Have you conducted any internal assessments or pilots related to quantum computing use cases?": "Have you run any internal studies, experiments, or pilot projects to test possible quantum use cases?",
            "Are you participating in any quantum ecosystem networks, consortia, or academic partnerships?": "Are you connected to the quantum ecosystem through consortia, vendor programs, universities, or research partnerships?",
        }
        return question_map.get(q)

    async def _auto_clarify_question_for_user(self, current_question: str) -> str:
        q = (current_question or "").strip()
        prompt = f"""Rephrase the following question to make it easier to understand.
Original question: {q}

Rules:
- Keep the same intent.
- Make it concrete and user-friendly.
- Use plain language.
- Keep it to one sentence.
- No markdown, no bullet points, no extra text.
"""
        raw = await self._model_gateway.chat(messages=[{"role": "user", "content": prompt}], model=self.VALIDATOR_MODEL, temperature=0.2)
        clarified = " ".join((raw or "").strip().split())
        if not clarified or clarified.lower().startswith("llm is not configured") or clarified.lower().startswith("llm call failed"):
            return f"Sure, let me simplify that.\n\n{q}\nPlease answer with one concrete example from your organization."
        if clarified == q:
            return f"Thanks for asking. In practical terms, please answer this with one specific example from your organization:\n\n{q}"
        clarified = clarified.replace("**", "")
        if clarified.count("?") > 1:
            clarified = f"{clarified.split('?', 1)[0].strip()}?"
        return clarified

    async def _clarification_decision(
        self,
        current_question: str,
        user_answer: Optional[str],
        extracted_information: Optional[str],
    ) -> tuple[bool, Optional[str]]:
        output_format = {
            "type": "object",
            "properties": {"needs_clarification": {"type": "boolean"}, "clarification_question": {"type": "string"}},
            "required": ["needs_clarification", "clarification_question"],
        }
        prompt = f"""You are evaluating if a single follow-up clarification question is needed.
Current question: {current_question}
User answer: {user_answer or "no answer"}
Extracted information: {extracted_information or "no information"}

Rules:
- Ask for clarification only if the answer is too vague, contradictory, or missing key detail.
- At most one follow-up question should be asked.
- The clarification question must be concise and concrete.
- Return plain text in the clarification question with no markdown.

Output STRICT JSON with this schema:
{output_format}
"""
        raw = await self._model_gateway.chat(messages=[{"role": "user", "content": prompt}], model=self.VALIDATOR_MODEL, temperature=0.1)
        text = (raw or "").strip()
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            needs_clarification = bool(data.get("needs_clarification"))
            clarification_question = str(data.get("clarification_question") or "").strip()
            if not needs_clarification:
                return False, None
            if not clarification_question:
                return True, self._fallback_clarification_question(current_question)
            clarification_question = clarification_question.replace("**", "")
            if clarification_question.count("?") > 1:
                clarification_question = f"{clarification_question.split('?', 1)[0].strip()}?"
            return True, clarification_question
        except Exception:
            return False, None

    def _normalized_command(self, text: str) -> Optional[str]:
        v = (text or "").strip().lower()
        if v in {"/skip", "/clarify", "/cancel", "/aicompletion", "/skip_questions"}:
            return v
        return None

    def _next_unfilled_key(self, field_status: Dict[str, str]) -> Optional[str]:
        for i in range(len(self.FIELD_SPECS)):
            if field_status[self.FIELD_SPECS[i]["key"]] != "complete":
                return self.FIELD_SPECS[i]["key"], i + 1
        return None, None

    def _write_information_status(self, stepData: QuantumDataCollectorState) -> str:
        complete_fields_str = "Complete or skipped fields (No more information needed) :"
        ongoing_fields_str = "In progress fields (partially filled fields) :"
        empty_fields_str = "Empty fields :"
        for field in self.FIELD_SPECS:
            field_status = stepData.get("field_status", {}).get(field["key"], "")
            field_information = stepData.get("field_information", {}).get(field["key"], "")
            if field_status == "empty":
                empty_fields_str += f"\n    - key : {field['key']}"
            elif field_status == "in_progress":
                ongoing_fields_str += f"\n    - key : {field['key']} ; information : {self._compact_information_summary(field_information, max_words=45)}"
            elif field_status == "complete":
                complete_fields_str += f"\n    - key : {field['key']} ; information : {self._compact_information_summary(field_information, max_words=45)}"
        return f"1. {complete_fields_str}\n\n2. {ongoing_fields_str}\n\n3. {empty_fields_str}"

    def _is_no_information(self, text: str) -> bool:
        normalized = " ".join((text or "").strip().lower().split())
        return normalized in {"no information", "none", "n/a"}

    def _classify_binary_short_answer(self, answer: Optional[str]) -> Optional[str]:
        normalized = " ".join((answer or "").strip().lower().split())
        if not normalized or len(normalized.split()) > 4:
            return None
        negative_values = {"no", "nope", "nah", "not yet", "not now", "none", "n/a", "not currently"}
        positive_values = {"yes", "yeah", "yep", "affirmative", "we do", "yes we do"}
        if normalized in negative_values:
            return "negative"
        if normalized in positive_values:
            return "positive"
        return None

    def _short_answer_information(self, question: str, answer: Optional[str]) -> Optional[str]:
        polarity = self._classify_binary_short_answer(answer)
        if not polarity:
            return None
        q = (question or "").strip()
        mappings = {
            "Do you run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation)?": {
                "negative": "The user does not run large-scale combinatorial optimization problems.",
                "positive": "The user runs large-scale combinatorial optimization problems.",
            },
            "Do you conduct molecular simulation, materials science, drug discovery research, or any other research that has an intrinsic quantum nature?": {
                "negative": "The user does not conduct intrinsically quantum-natured research such as molecular simulation, materials science, or drug discovery.",
                "positive": "The user conducts intrinsically quantum-natured research such as molecular simulation, materials science, or drug discovery.",
            },
            "Do you currently implement state-of-the-art classical solutions for the problems you are trying to solve?": {
                "negative": "The user is not currently using state-of-the-art classical solutions for the target problems.",
                "positive": "The user is currently using state-of-the-art classical solutions for the target problems.",
            },
            "Do you have internal quantum expertise, or would any engagement depend entirely on external partners?": {
                "negative": "The user does not have internal quantum expertise and would rely on external partners.",
                "positive": "The user has internal quantum expertise.",
            },
            "Is your product or service protected by IP regulations?": {
                "negative": "The user reports low IP protection pressure for the product or service.",
                "positive": "The user indicates the product or service is protected by IP regulations.",
            },
            "Have you conducted any internal assessments or pilots related to quantum computing use cases?": {
                "negative": "The user has not conducted internal quantum assessments or pilots yet.",
                "positive": "The user has conducted internal quantum assessments or pilots.",
            },
            "Are you participating in any quantum ecosystem networks, consortia, or academic partnerships?": {
                "negative": "The user is not currently participating in quantum ecosystem networks, consortia, or academic partnerships.",
                "positive": "The user is participating in quantum ecosystem networks, consortia, or academic partnerships.",
            },
        }
        if q in mappings:
            return mappings[q].get(polarity)
        return f"The user answered {'negatively' if polarity == 'negative' else 'positively'} to the question: {q}"

    def _apply_rubric_heuristics(self, field_key: str, field_summary: str, rubrics: Dict[str, str]) -> Dict[str, str]:
        summary = " ".join((field_summary or "").strip().split())
        lower_summary = summary.lower()

        if field_key == "a_roadmap_ecosystem" and not rubrics.get("ecosystem_partnerships"):
            if any(kw in lower_summary for kw in ["not participating", "no ecosystem", "no partnerships", "not currently participating"]):
                rubrics["ecosystem_partnerships"] = "Not currently participating in quantum ecosystem networks, consortia, or academic partnerships."
            elif any(kw in lower_summary for kw in ["consortium", "consortia", "partnership", "university", "academic"]):
                rubrics["ecosystem_partnerships"] = self._compact_information_summary(summary, max_words=40)

        if field_key == "a_use_case_identification" and not rubrics.get("intrinsic_quantum"):
            if any(kw in lower_summary for kw in ["no intrinsic quantum", "no molecular", "without molecular", "no materials science", "no drug discovery"]):
                rubrics["intrinsic_quantum"] = "No intrinsically quantum research activities (molecular simulation, materials science, or drug discovery) were reported."

        return rubrics

    def _apply_cross_field_heuristics(self, step_data: QuantumDataCollectorState, current_field: str) -> None:
        answer = " ".join((step_data.get("last_user_answer") or "").strip().split())
        lower_answer = answer.lower()
        if not lower_answer:
            return

        keyword_map: Dict[str, List[str]] = {
            "a_use_case_identification": ["industry", "optimization", "risk model", "simulation", "portfolio"],
            "a_technical_infrastructure_baseline": ["hpc", "gpu", "cloud", "infrastructure", "internal expertise", "external partner"],
            "a_strategic_organizational_maturity": ["first mover", "second mover", "wait-and-see", "ip", "patent", "trade secret"],
            "a_roadmap_ecosystem": ["pilot", "ecosystem", "consortia", "academic", "partnership", "competitor"],
        }

        for field_key, keywords in keyword_map.items():
            if field_key == current_field:
                continue
            if step_data["field_status"].get(field_key) == "complete":
                continue
            if any(keyword in lower_answer for keyword in keywords):
                existing = step_data["field_information"].get(field_key, "")
                merged = f"{existing} {answer}".strip() if existing else answer
                step_data["field_information"][field_key] = self._compact_information_summary(merged, max_words=60)
                if step_data["field_status"].get(field_key) == "empty":
                    step_data["field_status"][field_key] = "in_progress"

    def _compact_information_summary(self, text: Optional[str], max_words: int = 90) -> str:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned:
            return ""
        if self._is_no_information(cleaned):
            return cleaned
        sentence_candidates = cleaned.replace("\n", " ").split(". ")
        deduped_sentences: List[str] = []
        seen = set()
        for sentence in sentence_candidates:
            normalized_sentence = sentence.strip().strip(".")
            if not normalized_sentence:
                continue
            key = normalized_sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped_sentences.append(normalized_sentence)
        compact = ". ".join(deduped_sentences).strip()
        if compact and not compact.endswith("."):
            compact += "."
        words = compact.split()
        if len(words) > max_words:
            compact = " ".join(words[:max_words]).rstrip(",;:")
            if not compact.endswith("."):
                compact += "."
        return compact

    def _log_model_quality_debug(self, state: SubgraphState, current_field: str) -> None:
        question = self._latest_assistant_question(state["stepData"].get("messages", []))
        user_answer = state["stepData"].get("last_user_answer", "")
        stored_field_value = state["stepData"].get("field_information", {}).get(current_field, "")
        stored_field_status = state["stepData"].get("field_status", {}).get(current_field, "unknown")
        print(
            "\n[MODEL_QUALITY_DEBUG]"
            f"\n- model: {self.VALIDATOR_MODEL}"
            f"\n- current_field: {current_field}"
            f"\n- field_status: {stored_field_status}"
            f"\n- agent_question: {question}"
            f"\n- user_response: {user_answer}"
            f"\n- stored_field_information: {stored_field_value}"
            "\n[/MODEL_QUALITY_DEBUG]\n"
        )

    def _latest_assistant_question(self, messages: List[Dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message.get("content", "")
        return "No assistant question found."

    def _field_desc_str(self) -> str:
        return "".join(f"- {field['key']}: {field['explanation']}\n" for field in self.FIELD_SPECS)

    async def _ai_completion(self, stepData: QuantumDataCollectorState) -> str:
        field_description = self._field_desc_str()
        field_information = stepData.get("field_information", {})
        ai_question = self._latest_assistant_question(stepData["messages"])
        prompt = f"""You want to assess the quantum readiness of your company, so you asked an assistant to provide you a detailed report on the quantum readiness of your company.
In order to generate a reliable report, this assistant needs your information regarding 4 fields : 
{field_description}
You already provided the following information :
{field_information}

Now, the assistant asked you the following question : {ai_question}
Invent a response consistent with the information already given.
Respond with exactly one short sentence (maximum 25 words).
Do not include markdown, code fences, lists, or extra keys.
"""
        raw = await self._model_gateway.chat(messages=[{"role": "user", "content": prompt}], model=self.VALIDATOR_MODEL, temperature=0.2)
        text = " ".join((raw or "").strip().split())
        short_text = text
        for separator in [".", "?", "!", ";"]:
            idx = short_text.find(separator)
            if idx != -1:
                short_text = short_text[: idx + 1]
                break
        words = short_text.split()
        if len(words) > 25:
            short_text = " ".join(words[:25]).rstrip(",")
            if not short_text.endswith("."):
                short_text += "."
        text = short_text.strip().strip('"')
        print(f"[DATA_COLLECTOR] DEBUG - AI completion : {text}")
        return text
