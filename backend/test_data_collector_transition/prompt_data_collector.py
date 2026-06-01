import json

def create_system_prompt_data_collector(context):
    FIELD_SPECS = [
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
    return SYSTEM_PROMPT


def create_prompt_build_transition_feedback(context):
    vars = context['vars']
    done = vars.get('done') or "no completed section provided"
    nxt = vars.get('nxt') or "no next section provided"
    done_info = vars.get('done_info') or ""
    temperature = vars.get('temperature') or 0.3
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
    return {
        "prompt": prompt,
        "config": {
            "temperature": temperature
        }
    }


def create_prompt_auto_clarify_question_for_user(context):
    vars = context['vars']
    question = vars.get('current_question') or "no current question provided"
    temperature = vars.get('temperature') or 0.2
    prompt = f"""Rephrase the following question to make it easier to understand.
Original question: {question}

Rules:
- Keep the same intent.
- Make it concrete and user-friendly.
- Use plain language.
- Keep it to one sentence.
- No markdown, no bullet points, no extra text.
"""
    return {
        "prompt": prompt,
        "config": {
            "temperature": temperature
        }
    }

# To continue...