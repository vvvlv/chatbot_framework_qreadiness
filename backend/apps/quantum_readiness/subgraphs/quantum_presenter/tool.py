"""
Quantum Readiness Presenter/RAG Tool - Layer 3.

Retrieves benchmark documents via RAG.
Generates prioritized action list.
Formats final readiness report.
"""
import json
import traceback
from datetime import date
from typing import Dict, List, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.protocols import SubgraphProtocol, ToolProtocol
from core.state import SubgraphState
from core.model_gateway import ModelGateway


class QuantumPresenterState(TypedDict, total=False):
    """State for Quantum Readiness Presenter Tool."""
    
    # Input data (from analyzer)
    user_industry: str
    crypto_risk_score: float
    crypto_risk_level: str
    quantum_opportunity_score: float
    archetype: str
    archetype_narrative: str
    branch_a_topics: Dict
    branch_b_topics: Dict
    branch_a_score: float
    branch_b_score: float
    branch_a_band: Dict[str, str]
    branch_b_band: Dict[str, str]
    risk_breakdown: dict
    opportunity_breakdown: dict
    unknowns: list

    # Output
    benchmark_documents: List[Dict]
    priority_actions: List[Dict]
    timeline_guidance: str
    company_name: str
    industry: str
    readiness_report: str
    next_step: str


class QuantumPresenterTool(SubgraphProtocol):
    """
    Presenter/RAG Tool for Quantum Readiness assessment.
    
    Formats results and retrieves benchmark documents.
    Generates prioritized action list and final report.
    """
    
    name = "quantum_presenter"
    
    def __init__(self, model_gateway: ModelGateway, retriever: ToolProtocol):
        self._model_gateway = model_gateway
        self._retriever = retriever
    
    def describe(self) -> str:
        return "Formats quantum readiness results and generates prioritized action list with benchmark references."
    
    def build(self):
        """Build the presenter tool graph."""
        
        g = StateGraph(SubgraphState)
        g.add_node("init", self.init_node)
        g.add_node("rag", self._retriever.build())
        g.add_node("present", self.present_node)
        g.add_edge(START, "init")
        g.add_edge("init", "rag")
        g.add_edge("rag", "present")
        g.add_edge("present", END)
        return g.compile()
    
    async def init_node(self, state: SubgraphState) -> SubgraphState:
        session_id = state.get("session_id", "unknown")
        print(f"[PRESENTER] Generating report for session: {session_id}")

        print(f"[PRESENTER] Input data keys: {list(state['stepData'].keys())}")

        await adispatch_custom_event(
            "tool_start",
            {"tool_name": self.name, "total_steps": 1},
        )

        stepData : QuantumPresenterState = {
            **(state["stepData"]),
            "benchmark_documents": None,
            "priority_actions": None,
            "timeline_guidance": None,
            "readiness_report": None,
            "next_step": None
        }

        state["currentStep"] = "presenting"
        state["nextNode"] = "present"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None

        # Find company name and user industry from field "a_use_case_identification"
        print(f"[PRESENTER] Retrieving user industry information...")
        industry_prompt = f"""Based on the following user message, identify the company name and the industry of the user. Return "unknown" if the user doesn't contain the information needed.

User message :
{state['stepData'].get('user_industry', 'no user message')}

Return JSON:
{{
"company_name": "<user company name>" or "unknown",
"industry": "<user industry>" or "unknown"
}}
"""
        try:
            industry_response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": industry_prompt}],
                temperature=0.3,
            )
            
            # Try to parse JSON
            if "{" in industry_response and "}" in industry_response:
                json_start = industry_response.find("{")
                json_end = industry_response.rfind("}") + 1
                json_str = industry_response[json_start:json_end]
                industry_result = json.loads(json_str)
                state["stepData"]["industry"] = industry_result.get("industry", "unknown")
                state["stepData"]["company_name"] = industry_result.get("company_name", "unknown")
                print(f"[PRESENTER] ✓ Retrieved user's company name and industry")
            else:
                print(f"[PRESENTER] ⚠ Could not parse actions JSON from LLM response")
                state["stepData"]["industry"] = "unknown"
                state["stepData"]["company_name"] = "unknown"
        except Exception as e:
            print(f"[PRESENTER] ✗ Error finding user industry information: {e}")
            traceback.print_exc()
            state["stepData"]["industry"] = "unknown"
            state["stepData"]["company_name"] = "unknown"

        # Retrieve benchmark documents via RAG
        print(f"[PRESENTER] Retrieving benchmark documents...")
        benchmark_query = f"""Quantum computing timelines, roadmaps, and qubit estimates for {state["stepData"].get('industry', 'unknown')} industry.
Include NIST FIPS 203, CISA advisories, and GRI timeline reports."""
        args_rag = {
            "action": "retrieve",
            "query": benchmark_query,
            "top_k": 5
        }
        state["common_tool_input"] = {
            "nextNode": "present",
            "args": args_rag
        }

        return state

    async def present_node(self, state: SubgraphState) -> SubgraphState:
        """
        Format results and generate final report.
        
        Single-pass function - no user input needed.
        """
        
        crypto_score = state["stepData"].get("crypto_risk_score", 0)
        opp_score = state["stepData"].get("quantum_opportunity_score", 0)
        archetype = state["stepData"].get("archetype", "Unknown")
        print(f"[PRESENTER] Scores - Risk: {crypto_score:.1f}, Opportunity: {opp_score:.1f}, Archetype: {archetype}")

        # process rag tool answer
        if state["common_tool_output"].get("error", False):
            print(f"[PRESENTER] ⚠ Error retrieving benchmarks: {state['error']}")
            state["benchmark_documents"] = []
        else:
            state["stepData"]["benchmark_documents"] = state["common_tool_output"]["answer"]
            state["common_tool_output"] = None
            print(f"[PRESENTER] Retrieved {len(state['stepData']['benchmark_documents'])} benchmark documents")
        
        # Format benchmark context
        benchmark_context = "\n---\n".join(
            doc.get("content", str(doc)) for doc in state["stepData"]["benchmark_documents"]
        ) if state["stepData"]["benchmark_documents"] else "No benchmark documents available."
        
        # Generate prioritized actions
        print(f"[PRESENTER] Generating prioritized actions...")
        actions_prompt = f"""Generate a prioritized action list for quantum readiness.

Company context:
- Industry: {state['stepData'].get('industry', 'Unknown')}
- Archetype: {state['stepData'].get('archetype', 'Unknown')}

Scores:
- Cryptographic Risk: {state['stepData'].get('crypto_risk_score', 0):.1f}/100 ({state['stepData'].get('crypto_risk_level', 'Unknown')})
- Quantum Opportunity: {state['stepData'].get('quantum_opportunity_score', 0):.1f}/100

Benchmark documents:
{benchmark_context[:1000]}  # Truncate for context

Generate:
1. Top 3 priority actions (most urgent first)
2. For each action, provide:
- Specific, concrete action item
- Reference (NIST FIPS 203, CISA advisory, GRI Timeline Report, etc.)
- Urgency level

Return JSON:
{{
"priority_actions": [
    {{
        "action": "...",
        "priority": 1,
        "reference": "NIST FIPS 203",
        "urgency": "high"
    }},
    ...
],
"next_step": "One concrete action for next 30 days"
}}"""
        
        try:
            actions_response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": actions_prompt}],
                temperature=0.3,
            )
            
            # Try to parse JSON
            if "{" in actions_response and "}" in actions_response:
                json_start = actions_response.find("{")
                json_end = actions_response.rfind("}") + 1
                json_str = actions_response[json_start:json_end]
                actions_result = json.loads(json_str)
                state["stepData"]["priority_actions"] = actions_result.get("priority_actions", [])
                state["stepData"]["next_step"] = actions_result.get("next_step", "")
                print(f"[PRESENTER] ✓ Generated {len(state['stepData']['priority_actions'])} priority actions")
            else:
                print(f"[PRESENTER] ⚠ Could not parse actions JSON from LLM response")
                state["stepData"]["priority_actions"] = []
                state["stepData"]["next_step"] = ""
        except Exception as e:
            print(f"[PRESENTER] ✗ Error generating actions: {e}")
            traceback.print_exc()
            state["stepData"]["priority_actions"] = []
            state["stepData"]["next_step"] = ""
        
        # Generate timeline guidance # TODO : UNUSED FOR NOW
        print(f"[PRESENTER] Generating timeline guidance...")
        timeline_prompt = f"""Based on the benchmark documents and company context, provide timeline guidance.

Benchmark context:
{benchmark_context[:1000]}

Company: 
    - name : {state['stepData'].get('company_name', 'Unknown')}
    - industry : {state['stepData'].get('industry', 'Unknown')}
Current scores: Risk {state['stepData'].get('crypto_risk_score', 0):.1f}, Opportunity {state['stepData'].get('quantum_opportunity_score', 0):.1f}

Provide specific timeline recommendations based on the benchmarks."""
        
        # try:
        #     timeline_response = await self._model_gateway.chat(
        #         messages=[{"role": "user", "content": timeline_prompt}],
        #         temperature=0.3,
        #     )
        #     state["stepData"]["timeline_guidance"] = timeline_response.strip()
        #     print(f"[PRESENTER] ✓ Timeline guidance generated")
        # except Exception as e:
        #     print(f"[PRESENTER] ⚠ Error generating timeline: {e}")
        #     state["stepData"]["timeline_guidance"] = "Timeline guidance unavailable."

        # Generate final report
        print(f"[PRESENTER] Formatting final report...")
        state["stepData"]["readiness_report"] = self._format_report(state["stepData"])
        
        # Set output for core graph
        state["output"] = state["stepData"]["readiness_report"]
        print(f"[PRESENTER] ✓ Report generated ({len(state['stepData']['readiness_report'])} chars)")
        
        await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "report_len": len(state["stepData"]["readiness_report"])},
        )
        return state

    def _format_report(self, step_data: Dict) -> str:
        """Format the final quantum readiness report."""
        company = step_data.get("company_name") or "Your Company"
        if company == "unknown":
            company = "Your Company"
        industry = step_data.get("industry") or "Unknown Sector"
        if industry == "unknown":
            industry = "Unknown Sector"
        today = date.today().isoformat()
        risk = step_data.get("crypto_risk_score", 0.0)
        opp = step_data.get("quantum_opportunity_score", 0.0)
        branch_a_score = step_data.get("branch_a_score", opp)
        branch_b_score = step_data.get("branch_b_score", max(0.0, 100.0 - risk))
        branch_a_band = (step_data.get("branch_a_band") or {}).get("name", "Unknown")
        branch_b_band = (step_data.get("branch_b_band") or {}).get("name", "Unknown")
        branch_a_focus = (step_data.get("branch_a_band") or {}).get("recommended_focus", "")
        branch_b_focus = (step_data.get("branch_b_band") or {}).get("recommended_focus", "")
        archetype = step_data.get("archetype", "Unknown")
        narrative = step_data.get("archetype_narrative", "")
        risk_breakdown = step_data.get("risk_breakdown", {})
        opp_breakdown = step_data.get("opportunity_breakdown", {})
        unknowns = step_data.get("unknowns", []) # TODO : not in the report for now
        # unknowns_text = ""
        # for item in unknowns:
        #     unknowns_text += f"  ⚠️ You were unsure about {item["section"]} - {item["dimension"]}\n"
        
        report = f"""
────────────────────────────────────────────  
**QUANTUM READINESS REPORT**  
Company: {company} | Sector: {industry} | Date: {today}  
────────────────────────────────────────────

1. **SCORES AT A GLANCE**  
    - Branch A (Quantum Competitiveness):     {branch_a_score:.0f} / 100  📈 {branch_a_band}
    - Branch B (PQC Readiness):               {branch_b_score:.0f} / 100  🔐 {branch_b_band}
    - Derived Crypto Risk Exposure:           {risk:.0f} / 100  {self._get_risk_emoji(step_data.get('crypto_risk_level', 'low'))} {step_data.get('crypto_risk_level', 'Low').title()}

2. **YOUR ARCHETYPE**  
   → "{archetype}"  
   {narrative}

3. **SCORE BREAKDOWN**  
    1. Branch A (Quantum Competitiveness)
        - Use Case Identification        {opp_breakdown.get('use_case_identification', {}).get('weighted_points', 0):>4.0f} / 35   {self._confidence_marker(opp_breakdown.get('use_case_identification', {}).get('confidence', 'low'))}
        - Tech/Infrastructure Baseline   {opp_breakdown.get('technical_infrastructure_baseline', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(opp_breakdown.get('technical_infrastructure_baseline', {}).get('confidence', 'low'))}
        - Strategic/Org Maturity         {opp_breakdown.get('strategic_organizational_maturity', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(opp_breakdown.get('strategic_organizational_maturity', {}).get('confidence', 'low'))}
        - Roadmap & Ecosystem            {opp_breakdown.get('roadmap_ecosystem', {}).get('weighted_points', 0):>4.0f} / 15   {self._confidence_marker(opp_breakdown.get('roadmap_ecosystem', {}).get('confidence', 'low'))}
    2. Branch B (Cryptographic Risk & PQ Security)
        - Data & Exposure Profile        {risk_breakdown.get('data_exposure_profile', {}).get('weighted_points', 0):>4.0f} / 35   {self._confidence_marker(risk_breakdown.get('data_exposure_profile', {}).get('confidence', 'low'))}
        - Migration Readiness            {risk_breakdown.get('migration_readiness', {}).get('weighted_points', 0):>4.0f} / 30   {self._confidence_marker(risk_breakdown.get('migration_readiness', {}).get('confidence', 'low'))}
        - Supply Chain & Ecosystem       {risk_breakdown.get('supply_chain_ecosystem', {}).get('weighted_points', 0):>4.0f} / 20   {self._confidence_marker(risk_breakdown.get('supply_chain_ecosystem', {}).get('confidence', 'low'))}
        - Governance                     {risk_breakdown.get('governance', {}).get('weighted_points', 0):>4.0f} / 15   {self._confidence_marker(risk_breakdown.get('governance', {}).get('confidence', 'low'))}

4. **WHERE TO FOCUS NEXT**  
   You are currently positioned as "{branch_a_band}" on quantum competitiveness and "{branch_b_band}" on cryptographic readiness.  
   Your most important focus areas are:  
   - Quantum Competitiveness: {branch_a_focus or 'Define focused pilots and decision milestones.'}  
   - Cryptographic Readiness: {branch_b_focus or 'Prioritize inventory, migration planning, and governance.'}  
   If you want a practical action plan, the Roadmap Chatbot can translate these priorities into concrete next steps and timeline options.
"""
        
        report += "  \n────────────────────────────────────────────\n"
        
        return report

    def _confidence_marker(self, level: str) -> str:
        if level == "low":
            return "⚠️"
        if level == "medium":
            return "•"
        return ""
    
    def _get_risk_emoji(self, level: str) -> str:
        """Get emoji for risk level."""
        emoji_map = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }
        return emoji_map.get(level, "⚪")
    
    def _get_opportunity_level(self, score: float) -> str:
        """Get opportunity level description."""
        if score >= 70:
            return "High Opportunity"
        elif score >= 50:
            return "Moderate Opportunity"
        else:
            return "Low Opportunity"
