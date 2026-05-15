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
    default_question: str
    answer_criteria: str
    example_answers: List[str]

class QuantumDataCollectorState(TypedDict, total=False):
    """stepData for the field-filling collector."""
    
    messages: list[Dict]
    field_status: Dict[str, Dict[str, str]] # field_key -> rubric -> "empty" | "in_progress" | "complete"
    last_user_answer: Optional[str]
    iterations_count: Dict[str, Dict[str, int]]  # field_key -> rubric -> number of AI questions on the field
    field_information: Dict[str, Dict[str, str]] # field_key -> rubric -> user information about the field
    user_command: Optional[str] # potential inputed command between /cancel, /skip, /clarify and /aicompletion
    current_field_key: Optional[str]
    current_rubric: Optional[str]
    pending_question: Optional[str]
    consumed_prompt_ids: List[str]
    last_validation_reason: Optional[str]
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
        os.getenv("LLM_MODEL", "mistral/mistral-small-latest"),
    )
    SLOTS_BY_FIELD: Dict[str, Dict] = {
        "a_use_case_identification": {
            "description": "Industry, computationally intensive problems, optimization, intrinsic quantum use cases, classical bottlenecks",
            "rubrics": {
                "industry": "Which industry or sector the organization operates in.",
                "core_compute_problem": "What are the main computationally intensive business problems.",
                "optimization": "If they run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation).",
                "intrinsic_quantum": "If they conduct molecular simulation, materials science, drug discovery research or any other research that has an intrinsic quantum nature.",
                # "classical_bottleneck": " conduct molecular simulation, materials science, drug discovery research or any other research that has an intrinsic quantum nature.",
            },
        },
        "a_technical_infrastructure_baseline": {
            "description": "HPC/cloud footprint, classical baselines, vendor relationships, internal expertise",
            "rubrics": {
                # "compute_footprint": "Where workloads run (cloud, HPC, hybrid) and rough scale.",
                "classical_maturity": "What are currently implemented state-of-the-art classical solutions for the problems they are trying to solve",
                # "vendor_landscape": "Existing relationships with quantum hardware or software vendors",
                "internal_expertise": "In-house quantum-capable people or reliance on partners.",
            },
        },
        "a_strategic_organizational_maturity": {
            "description": "Adoption posture, IP sensitivity, dedicated budget",
            "rubrics": {
                "adoption_posture": "Technology adoption posture toward emerging tech (first mover, second mover, wait-and-see).",
                "ip_sensitivity": "Sensitivity of IP or data to new algorithms or partners.",
                # "budget_model": "Whether exploration budget is dedicated, shared, or absent.",
            },
        },
        "a_roadmap_ecosystem": {
            "description": "Internal pilots, ecosystem participation, competitor monitoring",
            "rubrics": {
                "internal_pilots": "Whether they have conducted any internal assessments or pilots related to quantum computing use cases.",
                "ecosystem_partnerships": "Participation to any quantum ecosystem networks, consortia, or academic partnerships.",
                # "competitors": "Does their sector have early quantum adopters among competitors — Are they monitoring their activity",
            },
        },
    }
    SYSTEM_PROMPT = f"""
SYSTEM PROMPT : 
You are a professional quantum assistant that helps managers to assess the quantum readiness of their company/structure.
Your first step is to gather the information necessary for this assessment.
More precisely, your goal is to identify the user's information according to 4 fields. Each field has several rubrics, each corresponding to a basic piece of information.
Here are the 4 fields :

{json.dumps(SLOTS_BY_FIELD)}

I will update you on the information status for each rubric after every user message, and tell you what is the current rubric to focus on.
Your main objective is always to get more information from the user about the current rubric, but you can help them to better understand technical terms if they need.
Don't ask several questions in a single message. If necessary, start with the most general question.
"""
    TOTAL_STEPS = 4
    MAX_RETRIES_PER_FIELD = 5

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
            "field_status": {field: {rubric: "empty" for rubric in content["rubrics"].keys()} for field, content in self.SLOTS_BY_FIELD.items()},
            "last_user_answer": None,
            "iterations_count": {field: {rubric: 0 for rubric in content["rubrics"].keys()} for field, content in self.SLOTS_BY_FIELD.items()},
            "field_information": {field: {rubric: "" for rubric in content["rubrics"].keys()} for field, content in self.SLOTS_BY_FIELD.items()},
            "consumed_prompt_ids": [],
            "last_validation_reason": None,
            "pending_question": None,
            "user_command": None,
            "current_field_key": "a_use_case_identification",
            "step": 1,
            "current_rubric": "industry",
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
            information_status = self._write_information_status(state["stepData"])
            print(f"[DATA COLLECTOR] DEBUG - information status : {information_status}")
            extra_rules = ""
            if state["stepData"]["iterations_count"][state['stepData']['current_field_key']][state['stepData']['current_rubric']] == 4:
                extra_rules = """It is your last question to get information about the current rubric.
If the user strays too far from the topic, warn them that you're going to switch to a next field at next question.
"""
            if state["stepData"].get("last_user_answer", None) == None:
                system_message = f"""
INFORMATION STATUS :

{information_status}

CURRENT FIELD : {state['stepData'].get('current_field_key', 'No current field key')}
CURRENT RUBRIC : {state['stepData'].get('current_rubric', 'No current rubric')}

INSTRUCTION : generate a question to get more information from the user about the current rubric.
"""
            else:
                system_message = f"""
INFORMATION STATUS :

{information_status}

CURRENT FIELD : {state['stepData'].get('current_field_key', 'No current field key')}
CURRENT RUBRIC : {state['stepData'].get('current_rubric', 'No current rubric')}

INSTRUCTION : Generate a message based on your system prompt, the last user message and the message history.
{extra_rules}
"""
            new_message = {
                "role": "user",
                "content": f"""<instructions>{system_message}</instructions>

<user_message>{state['stepData'].get('last_user_answer', 'no user message')}</user_message>"""
            }
            state["stepData"]["messages"].append(new_message)
            llm_message : list[Dict] = [{"role": "system", "content": self.SYSTEM_PROMPT}] + state["stepData"]["messages"][-5:]
            question = await self._model_gateway.chat(
                messages=llm_message,
                model=self.VALIDATOR_MODEL,
                temperature=0.4,
            )
            question = (question or "").strip()
            state["stepData"]["messages"].append({"role": "assistant", "content": question})
            state["stepData"]["pending_question"] = question

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
        rubric = state["stepData"].get("current_rubric")

        if command == "/cancel":
            state["error"] = "Tool cancelled by user."
            state["output"] = "Understood. The conversation has been ended. If you'd like to start a new session or need any assistance, don't hesitate to reach out."
            state["currentStep"] = "Idle"
            state["stepData"] = {}
            state["common_tool_input"] = {}
            state["common_tool_output"] = {}
            state["pending_prompt_id"] = None
            await adispatch_custom_event("tool_complete", {"tool_name": self.name})
            state["nextNode"] = END
            return state
        
        if command == "/skip":
            state["stepData"]["field_status"][field_key][rubric] = "complete"
            state["stepData"]["field_information"][field_key][rubric] += "The user skipped aditional data collection for this rubric."
            next_field, next_rubric = self._next_unfilled_key(state["stepData"]["field_status"], field_key)
            if next_field != field_key:
                state["stepData"]["step"] += 1
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = None
            if next_field == None:
                await adispatch_custom_event("tool_progress", {"step": self.TOTAL_STEPS, "total": self.TOTAL_STEPS})
                state["nextNode"] = "before_analyzer"
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["current_rubric"] = next_rubric
            state["nextNode"] = "generate_question"
            await adispatch_custom_event("tool_progress", {"step": state["stepData"]["step"], "total": self.TOTAL_STEPS})
            return state
        
        # Clarification request -> generate clarification message and re-ask.
        if command == "/clarify":
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = "Can you clarify your last message ?"
            state["stepData"]["iterations_count"][field_key][rubric] += 1
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

        current_field = state['stepData']['current_field_key']
        current_rubric = state['stepData']['current_rubric']
        information_status = self._write_information_status(state["stepData"])
        output_format = {
            "type": "array",
            "items": {
                "oneOf": [
                    {
                        "type": object,
                        "properties": {
                            "field": {
                                "type": "string",
                                "const": field,
                                "description": "ID of the field"
                            },
                            "rubrics": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "rubric": {
                                            "type": "string",
                                            "enum": content["rubrics"].keys(),
                                            "description": f"ID of the rubric inside the field {field}"
                                        },
                                        "new_information_summary": {
                                            "type": "string",
                                            "description": "updated information summary of the rubric, based on the user answer and the already extracted information regarding the rubric"
                                        },
                                        "new_status": {
                                            "type": "string",
                                            "enum": ["empty", "in_progress", "complete"],
                                            "description": "updated status of the rubric, based on the new information summary and the rubric description."
                                        }
                                    },
                                    "required": ["rubric", "new_information_summary", "new_status"],
                                    "additionalProperties": False
                                },
                                "description": "the updated information/status for all rubric of the field"
                            }
                        },
                        "required": ["field", "rubrics"],
                        "additionalProperties": False
                    }
                    for field, content in self.SLOTS_BY_FIELD.items()
                ]
            }
        }
        main_prompt = f"""
Your task now is to extract relevant information from the user answer in order to fill the 4 quantum readiness fields described in your system prompt.

Here is a summary of the information already extracted for each field and each rubric :

{information_status}

The rubric currently being discussed in the conversation is : {current_rubric} (field: {current_field}).

Your last message was : {state['stepData']['messages'][-1]["content"]}

The user answered : {state['stepData']['last_user_answer']}

For each field f, for each rubric r of field f :
1) If it exists, extract relevant information regarding r from the user answer based on the description of r, and update the information summary of r with it.
2) Compare the new information summary of the rubric r with their description in your system prompt. If there is enough information, set r status to "complete". If there is not enough information and r was "empty", set r status to "in_progress".
Output STRICT JSON with this schema:
{output_format}
"""

        step_messages = [
            {"role": "user", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": main_prompt},
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output get_information : {text}")
        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            data = json.loads(text[start:end])
            for field_item in data:
                field_key = field_item.get("field")
                rubrics_list = field_item.get("rubrics")
                if field_key is None or field_key not in self.SLOTS_BY_FIELD.keys() or rubrics_list is None:
                    print("[DATA COLLECTOR] ⚠ INFO - invalid field item in get_information AI output")
                else:
                    for rubric_item in rubrics_list:
                        rubric_name = rubric_item.get("rubric")
                        rubric_summary = rubric_item.get("new_information_summary")
                        rubric_status = rubric_item.get("new_status")
                        if rubric_name is None or rubric_name not in self.SLOTS_BY_FIELD[field_key]["rubrics"].keys() or rubric_summary is None or rubric_status is None:
                            print("[DATA COLLECTOR] ⚠ INFO - invalid rubric item in get_information AI output")
                        else:
                            if state["stepData"]["field_status"][field_key][rubric_name] != "complete":
                                state["stepData"]["field_status"][field_key][rubric_name] = rubric_status
                                state["stepData"]["field_information"][field_key][rubric_name] = rubric_summary
        except Exception:
            # Fail-safe: no update on other fields
            print("[DATA_COLLECTOR] DEBUG - Parsing of get_information AI output has failed.")

        state["stepData"]["iterations_count"][current_field][current_rubric] += 1
        if state["stepData"]["iterations_count"][current_field][current_rubric] >= self.MAX_RETRIES_PER_FIELD:
            state["stepData"]["field_status"][current_field][current_rubric] = "complete"

        # Determine next step
        state["pending_prompt_id"] = None
        if state["stepData"]["field_status"][current_field][current_rubric] == "complete":
            next_field, next_rubric = self._next_unfilled_key(state["stepData"]["field_status"], current_field)
            if next_field != current_field:
                state["stepData"]["step"] += 1
            if next_field == None:
                await adispatch_custom_event("tool_progress", {"step": self.TOTAL_STEPS, "total": self.TOTAL_STEPS})
                state["nextNode"] = "before_analyzer"
                self._log_model_quality_debug(state=state, current_field=current_field)
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["current_rubric"] = next_rubric
            await adispatch_custom_event("tool_progress", {"step": state["stepData"]["step"], "total": self.TOTAL_STEPS})
        self._log_model_quality_debug(state=state, current_field=current_field, current_rubric=current_rubric)
        state["nextNode"] = "generate_question"
        return state
    
    async def before_analyzer_node(self, state: SubgraphState) -> SubgraphState:
        collected = state["stepData"].get("field_information", {})
        step_data = {
            "branch_a_topics": collected,
        }
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": step_data},
        )
        state["stepData"] = step_data
        state["nextNode"] = "analyzer"
        return state

    # --- Utils functions ---

    def _normalized_command(self, text: str) -> Optional[str]:
        v = (text or "").strip().lower()
        if v in {"/skip", "/clarify", "/cancel", "/aicompletion"}:
            return v
        return None
    
    def _next_unfilled_key(self, field_status: Dict[str, str], current_field: str) -> Optional[str]:
        for rubric, status in field_status[current_field].items():
            if status != "complete":
                return current_field, rubric
        for field, value in field_status.items():
            for rubric, status in value.items():
                if status != "complete":
                    return field, rubric
        return None, None

    def _write_information_status(self, stepData: QuantumDataCollectorState) -> str:
        complete_rubrics_str = "Complete or skipped rubrics (No more information needed) :"
        ongoing_rubrics_str = "In progress rubrics (partially filled fields) :"
        empty_rubrics_str = "Empty rubrics :"
        for field, content in self.SLOTS_BY_FIELD.items():
            for rubric in content["rubrics"].keys():
                rubric_status = stepData["field_status"][field][rubric]
                rubric_information = stepData["field_information"][field][rubric]
                if rubric_status == "empty":
                    empty_rubrics_str += f"\n    - field : {field} ; rubric : {rubric}"
                elif rubric_status == "in_progress":
                    ongoing_rubrics_str += f"\n    - field : {field} ; rubric : {rubric} ; information : {rubric_information}"
                elif rubric_status == "complete":
                    complete_rubrics_str += f"\n    - field : {field} ; rubric : {rubric} ; information : {rubric_information}"
        output = f"1. {complete_rubrics_str}\n\n2. {ongoing_rubrics_str}\n\n3. {empty_rubrics_str}"
        return output

    def _log_model_quality_debug(self, state: SubgraphState, current_field: str, current_rubric: str) -> None:
        question = self._latest_assistant_question(state["stepData"].get("messages", []))
        user_answer = state["stepData"].get("last_user_answer", "")
        stored_field_value = state["stepData"].get("field_information", {}).get(current_field, {}).get(current_rubric, "")
        stored_field_status = state["stepData"].get("field_status", {}).get(current_field, {}).get(current_rubric, "unknown")
        print(
            "\n[MODEL_QUALITY_DEBUG]"
            f"\n- model: {self.VALIDATOR_MODEL}"
            f"\n- current_field: {current_field}"
            f"\n- current rubric: {current_rubric}"
            f"\n- rubric_status: {stored_field_status}"
            f"\n- agent_question: {question}"
            f"\n- user_response: {user_answer}"
            f"\n- stored_rubric_information: {stored_field_value}"
            "\n[/MODEL_QUALITY_DEBUG]\n"
        )

    def _latest_assistant_question(self, messages: List[Dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message.get("content", "")
        return "No assistant question found."
    
    async def _ai_completion(self, stepData: QuantumDataCollectorState) -> str:
        field_information = stepData.get("field_information", {})
        ai_question = self._latest_assistant_question(stepData["messages"])
        prompt=f"""You want to assess the quantum readiness of your company, so you asked an assistant to provide you a detailed report on the quantum readiness of your company.
In order to generate a reliable report, this assistant needs your information regarding several rubrics grouped into 4 fields : 
{json.dumps(self.SLOTS_BY_FIELD)}
You already provided the following information :
{json.dumps(field_information)}

Now, the assistant asked you the following question : {ai_question}
Invent a response consistent with the information already given.
Do not include markdown, code fences, or extra keys.
"""
        raw = await self._model_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - AI completion : {text}")
        return text