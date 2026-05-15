"""
Quantum Readiness Data Collection Tool - Layer 3.

OLD LOGIC (field-filling tool):
- A small, fixed set of field specs (key + explanation + default question).
- For each field, ask a question via interrupt().
- On resume, an LLM (mistral small) evaluates if the response is satisfactory for the field,
  rewrites it if needed, and proposes a follow-up question if not satisfactory.
- The user can skip any question (UI sends "/skip") -> we store null/"no_response".
- If the user asks for clarification, we respond with a clarification message and re-ask.

For testing, we collect 4 topic-level fields focused on quantum competitiveness.

NEW IDEA :
- Give a system prompt with all fields and rules at the beginning of data collection.
- Then let the AI manage the discussion (but provide it some field information status)
- After every human message, ask the AI how much information they identified and extract information
- Update field information status
- Frontend : top-sub-bar with status for each field
"""

import os
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
    section_intro: str
    atomic_questions: List[str]
    answer_criteria: str
    example_answers: List[str]

class QuantumDataCollectorState(TypedDict, total=False):
    """stepData for the field-filling collector."""
    
    messages: list[Dict]
    field_status: Dict[str, str] # field_key -> "empty" | "in_progress" | "complete"
    last_user_answer: Optional[str]
    message_count: int # number of AI + user messages
    iterations_count: Dict[str, int]  # field_key -> number of AI questions on the field
    field_information: Dict[str, str] # field_key -> user information about the field
    user_command: Optional[str] # potential inputed command between /cancel, /skip and /clarify
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
    step: int

class QuantumDataCollectorTool(SubgraphProtocol):
    """
    Data Collection Tool for Quantum Readiness assessment.
    
    Collects information for Branch A (quantum competitiveness) only.
    
    Uses interrupt() for each question to suspend execution and wait for user response.
    """
    
    # --- Global variables ---

    name = "quantum_data_collector"
    VALIDATOR_MODEL = os.getenv(
        "VALIDATOR_MODEL",
        os.getenv("LITELLM_DEFAULT_MODEL")
        or os.getenv("LLM_MODEL", "claude-haiku-4-5"),
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
            "example_answers": ["Healthcare: drug discovery simulation and route optimization with long runtimes.", "Finance: portfolio optimization bottlenecks in intraday decisions."],
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

    # --- Main functions ---

    def __init__(self, model_gateway: ModelGateway, interrupt_tool: ToolProtocol):
        self._model_gateway = model_gateway
        self._interrupt_tool = interrupt_tool
    
    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."
    
    def build(self):
        """Build the field-filling collector tool graph."""

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
        g.add_conditional_edges("process_answer", self.router, {
            "command_handler": "command_handler",
            "get_information": "get_information",
            "generate_question": "generate_question"
        })
        g.add_conditional_edges("command_handler", self.router, {
            END: END,
            "before_analyzer": "before_analyzer",
            "get_information": "get_information",
            "generate_question": "generate_question"
        })
        g.add_conditional_edges("get_information", self.router, {
            "before_analyzer": "before_analyzer",
            "generate_question": "generate_question"
        })
        g.add_edge("before_analyzer", END)
        
        return g.compile()
    
    async def router(self, state: SubgraphState) -> str:
        # TODO: manage errors + manage undefined nextNode
        print("[ROUTER]: debug nextNode : ", state.get("nextNode"))
        return state.get("nextNode")
    
    # --- Node functions ---

    async def init_node(self, state: SubgraphState) -> SubgraphState:

        # Convert 5 last BaseMessages to a suitable type for litellm
        last_5_messages = []
        for msg in state.get("messages", [])[-5:]:
            role = "user" if hasattr(msg, 'type') and msg.type == "human" else "assistant"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            last_5_messages.append({"role": role, "content": content})
        
        stepData : QuantumDataCollectorState = {
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
        if state["stepData"].get("pending_question") != None:
            question = state["stepData"]["pending_question"]
        else:
            field_key = state["stepData"].get("current_field_key")
            field_spec = self._field_spec_by_key(field_key)
            question_index = state["stepData"]["current_question_index"].get(field_key, 0)
            question_index = max(0, min(question_index, len(field_spec["atomic_questions"]) - 1))
            state["stepData"]["current_question_index"][field_key] = question_index

            # Clarification question (max 1) takes priority over main atomic question.
            if state["stepData"].get("awaiting_clarification"):
                question = (
                    state["stepData"].get("pending_clarification_question")
                    or self._fallback_clarification_question(field_spec["atomic_questions"][question_index])
                )
                state["stepData"]["last_question_kind"] = "clarification"
            else:
                base_question = field_spec["atomic_questions"][question_index].strip()
                section_intro = ""
                if not state["stepData"]["section_intro_sent"].get(field_key, False):
                    section_intro = field_spec["section_intro"].strip()
                    state["stepData"]["section_intro_sent"][field_key] = True
                question = f"{section_intro}\n\n{base_question}" if section_intro else base_question
                state["stepData"]["last_question_kind"] = "main"

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
            }
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
            print(f"[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Stale prompt answer received."
            state["nextNode"] = "generate_question"
            return state
        if prompt_id in state["stepData"]["consumed_prompt_ids"]:
            print(f"[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Duplicate prompt answer ignored."
            state["nextNode"] = "generate_question"
            return state
        state["stepData"]["pending_question"] = None
        state["stepData"]["consumed_prompt_ids"].append(prompt_id)

        command = self._normalized_command(raw_answer)
        if (command == None):
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
            state["output"] = "Understood. The conversation has been ended. If you'd like to start a new session or need any assistance, don't hesitate to reach out."
            state["currentStep"] = "Idle"
            state["stepData"] = {}
            state["common_tool_input"] = {}
            state["common_tool_output"] = {}
            state["pending_prompt_id"] = None
            await adispatch_custom_event("tool_complete", {"tool_name": self.name}) # TODO : change args of dispatched event
            state["nextNode"] = END
            return state
        
        if command == "/skip":
            if state["stepData"].get("post_collection_stage", 0) > 0:
                self._apply_post_collection_skip(state["stepData"])
                state["pending_prompt_id"] = None
                if state["stepData"].get("post_collection_stage", 0) >= 3:
                    state["nextNode"] = "before_analyzer"
                else:
                    state["nextNode"] = "generate_question"
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
            if next_field == None:
                self._start_post_collection(state["stepData"])
                state["nextNode"] = "generate_question"
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            state["nextNode"] = "generate_question"
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
            return state
        
        # Clarification request -> generate clarification message and re-ask.
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
                state["stepData"]["pending_question"] = await self._auto_clarify_question_for_user(current_question)
            state["stepData"]["manual_clarify_count_by_question"][question_instance_key] = clarify_count + 1
            state["stepData"]["last_question_kind"] = "main"
            state["nextNode"] = "generate_question"
            return state

        if command == "/aicompletion":
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = await self._ai_completion(state["stepData"])
            await adispatch_custom_event(
                "ai_completion",
                {"text": state["stepData"]["last_user_answer"]}
            )
            state["nextNode"] = "get_information"
            return state
        
    async def get_information_node(self, state: SubgraphState) -> SubgraphState:
        # - extract information about current field
        # - update field status (empty -> partially filled -> complete)
        # - update other fields information/status if relevant
        # - update current field if it has been completed
        # - update iteration count
        if state["stepData"].get("post_collection_stage", 0) > 0:
            self._handle_post_collection_response(state["stepData"])
            state["pending_prompt_id"] = None
            if state["stepData"].get("post_collection_stage", 0) >= 3:
                state["nextNode"] = "before_analyzer"
            else:
                state["nextNode"] = "generate_question"
            return state

        current_field = state['stepData']['current_field_key']
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
        
        # Task 1
        task1_prompt = f"""Extract relevant information for the current field from the user answer, based on the current field attributes and this specific question: {current_atomic_question}
Treat short direct answers like "yes", "no", or "not yet" as relevant information when they clearly answer the question.
If there is no relevant information, just return 'no information'.
Do not include markdown, code fences, or extra keys.
"""
        step_messages = [
            {"role": "user", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": main_prompt},
            {"role": "user", "content": task1_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        if self._is_no_information(text):
            short_answer_info = self._short_answer_information(
                current_atomic_question,
                state["stepData"].get("last_user_answer"),
            )
            if short_answer_info:
                text = short_answer_info
        print(f"[DATA_COLLECTOR] DEBUG - Output task 1 : {text}")

        # Task 2
        task2_prompt = f"""Merge the information you found ({text}) with the already extracted information of the current field ({state['stepData']['field_information'][current_field]}) into a single text summary.
Return a concise non-redundant summary (maximum 90 words).
Do not include markdown, code fences, or extra keys.
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task2_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        text = self._compact_information_summary(text)
        print(f"[DATA_COLLECTOR] DEBUG - Output task 2 : {text}")
        state["stepData"]["field_information"][current_field] = text

        # Task 3
        output3_format = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["empty", "in_progress", "complete"]
                }
            }
        }
        task3_prompt = f"""Based on the new information summary for the current field and the answer criteria of the current field,
indicate wether the current field is 'empty' (no user information extracted for this field), 'in_progress' (some user information but not enough) or 'complete' (there is enough user information for this field).
Output STRICT JSON with this schema:
{output3_format}
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task3_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.1,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 3 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            status = data.get("status")
            if status in {"empty", "in_progress"} and state["stepData"]["field_status"][current_field] != "complete":
                state["stepData"]["field_status"][current_field] = status
        except Exception:
            # Fail-safe: treat as incomplete
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 3 output has failed.")
        
        # Task 4
        output4_format = {
            "type": "object",
            "properties": {
                "list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string"
                            },
                            "new_information_summary": {
                                "type": "string"
                            },
                            "new_status": {
                                "type": "string",
                                "enum": ["empty", "in_progress", "complete"]
                            }
                        },
                        "required": ["key", "new_information_summary", "new_status"]
                    }
                }
            },
            "required": ["list"]
        }
        task4_prompt = f"""Based on the fields specifications, determine if the user answer contains relevant information for some fields other than the current field.
Update the information summary of the concerned fields with the user answer.
Compare the new information summary of the concerned fields with their answer criteria. For each field, if there is enough information, set the field status to "complete". If there is not enough information and the field was "empty", set the field status to "in_progress"
Return the list of the concerned fields, with their key, their new information summary and their new status.
Output STRICT JSON with this schema:
{output4_format}
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task4_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 4 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            data_list = data.get("list")
            for item in data_list:
                if item.get("key") != current_field and state["stepData"]["field_status"].get(item.get("key")) != "complete":
                    state["stepData"]["field_status"][item.get("key")] = (item.get("new_status") or state["stepData"]["field_status"][item.get("key")])
                    compact_summary = self._compact_information_summary(
                        item.get("new_information_summary") or state["stepData"]["field_information"][item.get("key")]
                    )
                    state["stepData"]["field_information"][item.get("key")] = compact_summary
        except Exception:
            # Fail-safe: no update on other fields
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 4 output has failed.")

        # Task 5: Clarification decision (max one per atomic question).
        should_clarify = False
        clarification_question = None
        question_instance_key = self._question_instance_key(state["stepData"], current_field)
        clarification_count = state["stepData"]["clarification_count_by_question"].get(question_instance_key, 0)
        if last_question_kind == "main" and clarification_count < 1:
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

        # Determine next step
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
            current_index >= len(field_spec["atomic_questions"])
            or state["stepData"]["iterations_count"][current_field] >= self.MAX_RETRIES_PER_FIELD
        ):
            state["stepData"]["field_status"][current_field] = "complete"
            next_field, step = self._next_unfilled_key(state["stepData"]["field_status"])
            if next_field == None:
                self._start_post_collection(state["stepData"])
                state["nextNode"] = "generate_question"
                self._log_model_quality_debug(state=state, current_field=current_field)
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
        self._log_model_quality_debug(state=state, current_field=current_field)
        state["nextNode"] = "generate_question"
        return state
    
    async def before_analyzer_node(self, state: SubgraphState) -> SubgraphState:
        collected = state["stepData"].get("field_information", {})
        branch_a_topics = {
            "use_case_identification": collected.get("a_use_case_identification"),
            "technical_infrastructure_baseline": collected.get("a_technical_infrastructure_baseline"),
            "strategic_organizational_maturity": collected.get("a_strategic_organizational_maturity"),
            "roadmap_ecosystem": collected.get("a_roadmap_ecosystem"),
        }
        step_data = {
            "user_industry": collected.get("a_use_case_identification"),
            "branch_a_topics": branch_a_topics,
            "fields": collected,
            "company_name_for_report": state["stepData"].get("company_name_for_report"),
            "report_save_opt_out": bool(state["stepData"].get("report_save_opt_out", False)),
        }
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": step_data},
        )
        state["stepData"] = step_data
        state["nextNode"] = "analyzer"
        return state

    # --- Utils functions ---

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

    def _fallback_clarification_question(self, current_question: str) -> str:
        return (
            "Thanks, that helps. Could you add one concrete detail so I can capture this accurately?\n\n"
            f"{current_question}"
        )

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

    def _handle_post_collection_response(self, step_data: QuantumDataCollectorState) -> None:
        stage = int(step_data.get("post_collection_stage", 0) or 0)
        answer = str(step_data.get("last_user_answer", "") or "").strip()
        normalized = " ".join(answer.lower().split())
        if stage == 1:
            step_data["company_name_for_report"] = self._extract_company_name(answer, normalized)
            step_data["post_collection_stage"] = 2
            step_data["pending_question"] = self.FINAL_REPORT_SAVE_OPT_OUT_QUESTION
            return
        if stage == 2:
            step_data["report_save_opt_out"] = self._is_affirmative_opt_out(normalized)
            step_data["post_collection_stage"] = 3
            step_data["pending_question"] = None

    def _extract_company_name(self, raw_answer: str, normalized_answer: str) -> Optional[str]:
        if not raw_answer:
            return None
        skip_values = {"skip", "no", "none", "n/a", "prefer not to say", "no thanks", "not now"}
        if normalized_answer in skip_values:
            return None
        if normalized_answer in {"yes", "sure", "ok", "okay"}:
            return None
        cleaned = " ".join(raw_answer.strip().split()).strip("\"'")
        if len(cleaned) < 2:
            return None
        return cleaned[:120]

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
            "What industry are you in, and what are your most computationally intensive business problems?":
                "To make this concrete, what industry are you in, and which one or two tasks consume the most computing time or cost today?",
            "Do you run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation)?":
                "In simple terms, do you solve complex decision problems where you must find the best option among many combinations, such as routing, scheduling, or portfolio construction?",
            "Do you conduct molecular simulation, materials science, drug discovery research, or any other research that has an intrinsic quantum nature?":
                "Do you do science-heavy R&D like molecular simulation, materials science, or drug discovery where quantum behavior is directly part of the problem?",
            "Do you currently implement state-of-the-art classical solutions for the problems you are trying to solve?":
                "By this I mean: are you already using the strongest non-quantum methods available today for these problems, such as advanced solvers, optimized ML models, or HPC workflows?",
            "Do you have internal quantum expertise, or would any engagement depend entirely on external partners?":
                "Do you currently have in-house people with quantum skills, or would you need outside consultants and vendors to do most of the work?",
            "What is your organization's typical technology adoption posture (first mover, second mover, wait-and-see)?":
                "How does your organization usually adopt new technology: early adopter, fast follower, or only after solutions are proven?",
            "Is your product or service protected by IP regulations?":
                "Are your products or services protected by patents, trade secrets, or strict IP/legal constraints?",
            "Have you conducted any internal assessments or pilots related to quantum computing use cases?":
                "Have you run any internal studies, experiments, or pilot projects to test possible quantum use cases?",
            "Are you participating in any quantum ecosystem networks, consortia, or academic partnerships?":
                "Are you connected to the quantum ecosystem through consortia, vendor programs, universities, or research partnerships?",
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
        raw = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        clarified = " ".join((raw or "").strip().split())
        if not clarified or clarified.lower().startswith("llm is not configured") or clarified.lower().startswith("llm call failed"):
            return (
                "Sure, let me simplify that.\n\n"
                f"{q}\n"
                "Please answer with one concrete example from your organization."
            )
        if clarified == q:
            return (
                "Thanks for asking. In practical terms, please answer this with one specific example from your organization:\n\n"
                f"{q}"
            )
        if "**" in clarified:
            clarified = clarified.replace("**", "")
        if clarified.count("?") > 1:
            first_question = clarified.split("?", 1)[0].strip()
            clarified = f"{first_question}?"
        return clarified

    async def _clarification_decision(
        self,
        current_question: str,
        user_answer: Optional[str],
        extracted_information: Optional[str],
    ) -> tuple[bool, Optional[str]]:
        output_format = {
            "type": "object",
            "properties": {
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": "string"},
            },
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
        raw = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.VALIDATOR_MODEL,
            temperature=0.1,
        )
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
            if "**" in clarification_question:
                clarification_question = clarification_question.replace("**", "")
            if clarification_question.count("?") > 1:
                first_question = clarification_question.split("?", 1)[0].strip()
                clarification_question = f"{first_question}?"
            return True, clarification_question
        except Exception:
            return False, None

    def _normalized_command(self, text: str) -> Optional[str]:
        v = (text or "").strip().lower()
        if v in {"/skip", "/clarify", "/cancel", "/aicompletion"}:
            return v
        return None
    
    def _next_unfilled_key(self, field_status: Dict[str, str]) -> Optional[str]:
        for i in range(len(self.FIELD_SPECS)):
            if field_status[self.FIELD_SPECS[i]["key"]] != "complete":
                return self.FIELD_SPECS[i]["key"], i+1
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
                ongoing_fields_str += (
                    f"\n    - key : {field['key']} ; information : "
                    f"{self._compact_information_summary(field_information, max_words=45)}"
                )
            elif field_status == "complete":
                complete_fields_str += (
                    f"\n    - key : {field['key']} ; information : "
                    f"{self._compact_information_summary(field_information, max_words=45)}"
                )
        return f"1. {complete_fields_str}\n\n2. {ongoing_fields_str}\n\n3. {empty_fields_str}"

    def _is_no_information(self, text: str) -> bool:
        normalized = " ".join((text or "").strip().lower().split())
        return normalized in {"no information", "none", "n/a"}

    def _classify_binary_short_answer(self, answer: Optional[str]) -> Optional[str]:
        normalized = " ".join((answer or "").strip().lower().split())
        if not normalized or len(normalized.split()) > 4:
            return None
        negative_values = {
            "no", "nope", "nah", "not yet", "not now", "none", "n/a", "not currently",
        }
        positive_values = {
            "yes", "yeah", "yep", "affirmative", "we do", "yes we do",
        }
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
        if polarity == "negative":
            return f"The user answered negatively to the question: {q}"
        return f"The user answered positively to the question: {q}"

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
        res = ""
        for field in self.FIELD_SPECS:
            res += f"- {field['key']}: {field['explanation']}\n"
        return res
    
    async def _ai_completion(self, stepData: QuantumDataCollectorState) -> str:
        field_description = self._field_desc_str()
        field_information = stepData.get("field_information", {})
        ai_question = self._latest_assistant_question(stepData["messages"])
        prompt=f"""You want to assess the quantum readiness of your company, so you asked an assistant to provide you a detailed report on the quantum readiness of your company.
In order to generate a reliable report, this assistant needs your information regarding 4 fields : 
{field_description}
You already provided the following information :
{field_information}

Now, the assistant asked you the following question : {ai_question}
Invent a response consistent with the information already given.
Respond with exactly one short sentence (maximum 25 words).
Do not include markdown, code fences, lists, or extra keys.
"""
        raw = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
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