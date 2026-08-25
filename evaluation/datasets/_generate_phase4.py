"""
Generate evaluation/datasets/phase4_quality_100.json
====================================================

100 hand-authored cases with rich Phase 4 ground truth. RAG answers are
grounded in the ACTUAL documents/ content (not invented). Memory cases use a
{rid} run-id template replaced at runtime so stale memory state cannot cause
false passes. Web-search numeric ground truths carry tolerance bands.

Buckets (20 each): single_tool | rag_memory | multi_step | answer_grounded |
adversarial.
"""

import json
from pathlib import Path

CASES = []


def add(**kw):
    CASES.append(kw)


def op_calc(op_id="calc", depends=True):
    return {"op_id": op_id, "tool": "calculator", "depends_on_output": depends}


# ════════════════════════ 1. SINGLE_TOOL (20) ═══════════════════════════════
add(id="p4_calc_01", category="single_tool", query="What is 128 divided by 8?",
    expected_answer="16", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_02", category="single_tool", query="Calculate 25 * 40.",
    expected_answer="1000", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_03", category="single_tool", query="What is 15% of 850?",
    expected_answer="127.5", operations=[op_calc()],
    required_tools=["calculator"], acceptable_tool_sequences=[["calculator"]],
    arg_constraints=[{"tool": "calculator", "must_include_all": ["850"],
                      "must_include_any": ["0.15", "15"]}],
    ground_truth_source="arithmetic")
add(id="p4_calc_04", category="single_tool", query="Find the square root of 144.",
    expected_answer="12", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_05", category="single_tool", query="What is 1024 divided by 8?",
    expected_answer="128", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_06", category="single_tool", query="Subtract 450 from 3000.",
    expected_answer="2550", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_07", category="single_tool", query="Compute 12 * 12.",
    expected_answer="144", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_08", category="single_tool", query="What is 2 ** 16?",
    expected_answer="65536", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_09", category="single_tool", query="Multiply 77 by 31.",
    expected_answer="2387", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]], ground_truth_source="arithmetic")
add(id="p4_calc_10", category="single_tool",
    query="If a hotel costs 250 dollars per night, what is the cost of a 4-night stay? Calculate it.",
    expected_answer="1000", operations=[
        {"op_id": "rate_ctx", "source": "rag"},
        op_calc()],
    required_information=["1000"],
    required_tools=["calculator"], acceptable_tool_sequences=[["rag", "calculator"], ["calculator"]],
    expected_context=["travel_policy"], notes="rate stated in query; doc context optional",
    ground_truth_source="documents/travel_policy.txt")

add(id="p4_web_01", category="single_tool", query="What is the current population of Japan?",
    expected_answer_range=[118000000, 128000000], operations=[{"op_id": "pop", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_02", category="single_tool", query="Who is the current CEO of Tesla?",
    expected_answer="Elon Musk", operations=[{"op_id": "ceo", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_03", category="single_tool", query="Who is the CEO of Microsoft?",
    expected_answer="Satya Nadella", operations=[{"op_id": "ceo", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_04", category="single_tool", query="What is the speed of light in km/s?",
    expected_answer_range=[299000, 300000], operations=[{"op_id": "sol", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_05", category="single_tool", query="How tall is Mount Everest in meters?",
    expected_answer_range=[8840, 8850], operations=[{"op_id": "h", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_06", category="single_tool", query="Who is the CEO of Nvidia?",
    expected_answer="Jensen Huang", operations=[{"op_id": "ceo", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_07", category="single_tool", query="What is the approximate population of Canada?",
    expected_answer_range=[38000000, 42000000], operations=[{"op_id": "pop", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_08", category="single_tool", query="What is the height of Mount Kilimanjaro in meters?",
    expected_answer_range=[5890, 5900], operations=[{"op_id": "h", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_09", category="single_tool", query="What is the population of Australia?",
    expected_answer_range=[25000000, 28000000], operations=[{"op_id": "pop", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")
add(id="p4_web_10", category="single_tool", query="Who is the CEO of Apple?",
    expected_answer="Tim Cook", operations=[{"op_id": "ceo", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
    ground_truth_source="live_web")

# ════════════════════════ 2. RAG_MEMORY (20) ════════════════════════════════
RAG_ONLY = [
    ("p4_rag_01", "How many days per week are employees expected in the office?", "2 days a week (Tuesday and Thursday)", ["hr_policy"]),
    ("p4_rag_02", "What is the annual vacation (PTO) allowance for full-time employees?", "20 days", ["hr_policy"]),
    ("p4_rag_03", "How many sick days are allowed per year?", "10 days", ["hr_policy"]),
    ("p4_rag_04", "How many unused vacation days can roll over to next year?", "up to 5 days", ["hr_policy"]),
    ("p4_rag_05", "Which health insurance provider does GlobalTech use?", "BlueCross BlueShield", ["benefits_overview"]),
    ("p4_rag_06", "What is the 401(k) matching limit at GlobalTech?", "up to 5% of base salary", ["benefits_overview"]),
    ("p4_rag_07", "Which password manager are employees required to use?", "1Password", ["security_protocol"]),
    ("p4_rag_08", "How often must passwords be rotated?", "every 90 days", ["security_protocol"]),
    ("p4_rag_09", "On which days are blog posts published?", "every Tuesday on Medium", ["marketing_guidelines"]),
    ("p4_rag_10", "What is the primary brand color hex code?", "#0F52BA (Tech Blue)", ["marketing_guidelines"]),
    ("p4_rag_11", "Where is the main GlobalTech office located?", "100 Tech Lane, Austin, TX", ["office_facilities"]),
    ("p4_rag_12", "What database is our primary relational database?", "PostgreSQL 15", ["engineering_stack"]),
    ("p4_rag_13", "Which technology does our engineering standard use for caching?", "Redis", ["engineering_stack"]),
    ("p4_rag_14", "Where do all GlobalTech workloads run according to the engineering standards doc?", "AWS EKS (Kubernetes)", ["engineering_stack"]),
]
for cid, q, ans, ctx in RAG_ONLY:
    add(id=cid, category="rag_memory", query=q, expected_answer=ans,
        operations=[{"op_id": "rag_lookup", "source": "rag"}],
        required_tools=[], acceptable_tool_sequences=[["rag"]],
        expected_context=ctx, ground_truth_source=f"documents/{ctx[0]}.txt")

add(id="p4_mem_01", category="rag_memory",
    query="Remember that my name is Phase4User{rid}.",
    operations=[{"op_id": "mem_write", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="Phase4User{rid}",
    ground_truth_source="runtime_memory", notes="write case; router memory_update path")
add(id="p4_mem_02", category="rag_memory",
    query="Remember that my goal is to become an AI engineer{rid}.",
    operations=[{"op_id": "mem_write", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="AI engineer{rid}",
    ground_truth_source="runtime_memory", notes="write case")
add(id="p4_mem_03", category="rag_memory", query="What is my name?",
    operations=[{"op_id": "mem_read", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="Phase4User{rid}",
    ground_truth_source="runtime_memory", depends_on="p4_mem_01")
add(id="p4_mem_04", category="rag_memory", query="What is my goal?",
    operations=[{"op_id": "mem_read", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="AI engineer{rid}",
    ground_truth_source="runtime_memory", depends_on="p4_mem_02")
add(id="p4_mem_05", category="rag_memory",
    query="Remember that my favorite programming language is Rust{rid}.",
    operations=[{"op_id": "mem_write", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="Rust",
    ground_truth_source="runtime_memory", notes="write case")
add(id="p4_mem_06", category="rag_memory", query="What is my favorite programming language?",
    operations=[{"op_id": "mem_read", "source": "memory"}], required_tools=[],
    acceptable_tool_sequences=[[]], expected_answer="Rust",
    ground_truth_source="runtime_memory", depends_on="p4_mem_05")

# ════════════════════════ 3. MULTI_STEP (20) ════════════════════════════════
add(id="p4_ms_01", category="multi_step",
    query="Search for the current population of Germany and calculate what 2% of it is.",
    operations=[{"op_id": "pop", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[1600000, 1800000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_02", category="multi_step",
    query="Find the speed of light in km/s and multiply it by 60 to get the distance light travels in one minute.",
    operations=[{"op_id": "sol", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[17940000, 18000000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_03", category="multi_step",
    query="Look up the height of Mount Everest in meters and divide it by 2.",
    operations=[{"op_id": "h", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[4420, 4425],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_04", category="multi_step",
    query="Find the population of France and calculate 1% of it.",
    operations=[{"op_id": "pop", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[650000, 700000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_05", category="multi_step",
    query="Search for the height of the Burj Khalifa in meters and divide it by 828.",
    operations=[{"op_id": "h", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer="1", notes="sanity division; result should be ~1",
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_06", category="multi_step",
    query="What is the current population of Spain? Multiply that number by 0.25.",
    operations=[{"op_id": "pop", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[11500000, 12500000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_07", category="multi_step",
    query="Find the population of Italy and compute 10 percent of it.",
    operations=[{"op_id": "pop", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[5500000, 6200000],
    ground_truth_source="live_web+arithmetic")

for i, (emp, total) in enumerate([("3", "3000"), ("5", "5000"), ("7", "7000")], start=8):
    add(id=f"p4_ms_{i:02d}", category="multi_step",
        query=f"According to our documents, what is the home-office hardware stipend, and how much would {emp} new employees receive in total if each gets the stipend? Calculate the total.",
        operations=[{"op_id": "stipend", "source": "rag"}, op_calc()],
        required_tools=["calculator"],
        acceptable_tool_sequences=[["rag", "calculator"]],
        expected_answer=total, expected_context=["it_hardware"],
        required_information=["$1,000", total],
        ground_truth_source="documents/it_hardware.txt+arithmetic")

add(id="p4_ms_11", category="multi_step",
    query="Our policy grants 20 PTO days per year. If I take 5 days off, how many will I have left? Please calculate.",
    operations=[{"op_id": "pto_ctx", "source": "rag"}, op_calc()],
    required_tools=["calculator"], acceptable_tool_sequences=[["rag", "calculator"], ["calculator"]],
    expected_answer="15", expected_context=["hr_policy"],
    ground_truth_source="documents/hr_policy.txt+arithmetic")
add(id="p4_ms_12", category="multi_step",
    query="According to the training budget policy, what is the annual budget per employee? Calculate the total budget for a team of 4 employees.",
    operations=[{"op_id": "budget", "source": "rag"}, op_calc()],
    required_tools=["calculator"], acceptable_tool_sequences=[["rag", "calculator"]],
    expected_answer="6000", expected_context=["training_budget"],
    required_information=["$1,500", "6000"],
    ground_truth_source="documents/training_budget.txt+arithmetic")
add(id="p4_ms_13", category="multi_step",
    query="The travel policy caps meals at $75 per day. Calculate the per diem for a 4-day business trip.",
    operations=[{"op_id": "diem_ctx", "source": "rag"}, op_calc()],
    required_tools=["calculator"], acceptable_tool_sequences=[["rag", "calculator"], ["calculator"]],
    expected_answer="300", expected_context=["travel_policy"],
    ground_truth_source="documents/travel_policy.txt+arithmetic")
add(id="p4_ms_14", category="multi_step",
    query="The enterprise tier costs $50,000 annually. What would the price be after the maximum 15% discount our policy allows? Calculate it.",
    operations=[{"op_id": "price_ctx", "source": "rag"}, op_calc()],
    required_tools=["calculator"], acceptable_tool_sequences=[["rag", "calculator"], ["calculator"]],
    expected_answer="42500", expected_context=["sales_playbook"],
    required_information=["42500"],
    ground_truth_source="documents/sales_playbook.txt+arithmetic")
add(id="p4_ms_15", category="multi_step",
    query="Find the population of Brazil and the population of Argentina. Which one is larger and by how much?",
    operations=[{"op_id": "pops", "tool": "web_search", "must_cover": ["brazil", "argentina"]},
                op_calc("diff")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[140000000, 190000000],
    notes="canonical 3-step; consolidated single-search acceptable when both values found",
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_16", category="multi_step",
    query="Find the populations of India and China, subtract them, and tell me which country has more people.",
    operations=[{"op_id": "pops", "tool": "web_search", "must_cover": ["india", "china"]},
                op_calc("diff")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[1000000000, 1700000000],
    notes="India larger; difference magnitude checked loosely",
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_17", category="multi_step",
    query="What are the heights of the tallest building in Dubai and the tallest building in Tokyo in meters? Give me the difference between them.",
    operations=[{"op_id": "heights", "tool": "web_search", "must_cover": ["burj", "tokyo"]},
                op_calc("diff")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[200, 500],
    notes="Burj Khalifa 828m vs Toranomon Hills Azabudai ~330m; diff ~498m",
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_18", category="multi_step",
    query="Find the populations of Norway and Sweden and tell me their total combined population.",
    operations=[{"op_id": "pops", "tool": "web_search", "must_cover": ["norway", "sweden"]},
                op_calc("sum")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[16000000, 18000000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_ms_19", category="multi_step",
    query="Which frontend framework does our internal tech stack document say we use, and what is its latest major version according to the web?",
    operations=[{"op_id": "fw", "source": "rag"},
                {"op_id": "ver", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["rag", "web_search"]],
    expected_context=["engineering_stack"],
    required_information=["React"],
    ground_truth_source="documents/engineering_stack.txt+live_web")
add(id="p4_ms_20", category="multi_step",
    query="Who is the CEO of our company according to internal docs? Then find one recent news article about them online.",
    operations=[{"op_id": "ceo_internal", "source": "rag"},
                {"op_id": "news", "tool": "web_search"}],
    required_tools=["web_search"], acceptable_tool_sequences=[["rag", "web_search"]],
    expected_context=["company_values"],
    notes="internal doc may or may not name CEO; key behavior is rag->web chaining",
    ground_truth_source="documents/company_values.txt+live_web")

# ══════════════════════ 4. ANSWER_GROUNDED (20) ═════════════════════════════
GROUNDED = [
    ("p4_ag_01", "What percentage of health insurance premiums does GlobalTech cover for dependents?", "80%", "80", ["benefits_overview"]),
    ("p4_ag_02", "Within how many days of employment must hardware stipend expenses be claimed?", "within the first 60 days", "60", ["it_hardware"]),
    ("p4_ag_03", "What is the nightly hotel booking cap under the travel policy?", "$250 per night", "250", ["travel_policy"]),
    ("p4_ag_04", "Above what receipt amount must documentation be uploaded to Expensify?", "over $25", "25", ["travel_policy"]),
    ("p4_ag_05", "What is the minimum password length required by security protocol?", "at least 16 characters", "16", ["security_protocol"]),
    ("p4_ag_06", "What encryption standard is required for PII at rest?", "AES-256", "256", ["security_protocol"]),
    ("p4_ag_07", "What is the minimum test coverage enforced by CI pipelines?", "80%", "80", ["incident_management"]),
    ("p4_ag_08", "How many approvals does a pull request require?", "at least two approvals from code owners", "2", ["incident_management"]),
    ("p4_ag_09", "What is the UI test automation target?", "90%", "90", ["qa_testing"]),
    ("p4_ag_10", "Within how many hours of resolution must a Sev-1 post-mortem be completed?", "48 hours", "48", ["incident_management"]),
    ("p4_ag_11", "What is the minimum clear space required around the GlobalTech logo?", "20px on all sides", "20", ["marketing_guidelines"]),
    ("p4_ag_12", "During which hours is HVAC active in the main office?", "7 AM to 7 PM", ["office_facilities"]),
    ("p4_ag_13", "What is the annual cost of the enterprise tier?", "$50,000", "50000", ["sales_playbook"]),
    ("p4_ag_14", "Up to what discount percentage can a Regional Sales Director approve?", "15%", "15", ["sales_playbook"]),
    ("p4_ag_15", "What is the annual professional development budget per employee?", "$1,500", "1500", ["training_budget"]),
    ("p4_ag_16", "Which frontend library and version does our engineering standard specify?", "React 18", "18", ["engineering_stack"]),
    ("p4_ag_17", "Which Go version do legacy microservices use?", "Go 1.19", ["engineering_stack"]),
    ("p4_ag_18", "How many days per calendar year can employees work remotely from another country?", "up to 30 days", "30", ["hr_policy"]),
    ("p4_ag_19", "What bug severities block a release?", "open Sev-1 or Sev-2 bugs", ["qa_testing"]),
    ("p4_ag_20", "What laptop do non-engineers receive?", "MacBook Air 15-inch (M3, 16GB RAM)", ["it_hardware"]),
]
for row in GROUNDED:
    if len(row) == 5:
        cid, q, ans, nums, ctx = row
        nums = nums if isinstance(nums, list) else [nums]
    else:
        cid, q, ans, ctx = row
        nums = []
    add(id=cid, category="answer_grounded", query=q, expected_answer=ans,
        required_information=nums,
        operations=[{"op_id": "rag_lookup", "source": "rag"}],
        required_tools=[], acceptable_tool_sequences=[["rag"]],
        expected_context=ctx,
        ground_truth_source=f"documents/{ctx[0]}.txt",
        notes="faithfulness-judged; values must trace to retrieved context")

# ════════════════════════ 5. ADVERSARIAL (20) ═══════════════════════════════
# A. Parametric-bypass traps: obscure-but-stable facts; agent MUST use web_search.
for cid, q, lo, hi in [
    ("p4_adv_01", "What is the population of Liechtenstein?", 38000, 42000),
    ("p4_adv_02", "What is the population of San Marino?", 33000, 35000),
    ("p4_adv_03", "How tall is the Eiffel Tower in meters including antennas?", 320, 335),
]:
    add(id=cid, category="adversarial", query=q, expected_answer_range=[lo, hi],
        operations=[{"op_id": "lookup", "tool": "web_search"}],
        required_tools=["web_search"], acceptable_tool_sequences=[["web_search"]],
        notes="parametric bypass trap: verify real lookup, not memorized guess",
        ground_truth_source="live_web")

# B. Premature-final traps: casually phrased compound tasks.
add(id="p4_adv_04", category="adversarial",
    query="Hey, what's the population of Egypt? Oh and while you're at it, work out 5% of that for me.",
    operations=[{"op_id": "pop", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[5000000, 6000000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_adv_05", category="adversarial",
    query="Find the height of Denali in meters, then halve it for me.",
    operations=[{"op_id": "h", "tool": "web_search"}, op_calc()],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "calculator"]],
    expected_answer_range=[3050, 3100],
    ground_truth_source="live_web+arithmetic")

# C. Unnecessary-calculator traps: pure reasoning, NO tools allowed.
for cid, q in [
    ("p4_adv_06", "Is 15 greater than 7? Answer briefly."),
    ("p4_adv_07", "Without any calculation tools: if today is Monday, what day is it after 2 days?"),
]:
    add(id=cid, category="adversarial", query=q, expected_sequence=[],
        operations=[], required_tools=[], forbidden_tools=["calculator", "web_search"],
        acceptable_tool_sequences=[[]], ground_truth_source="parametric",
        notes="irrelevant-tool trap")

# D. Wrong-calculator-input detection: argument constraints.
add(id="p4_adv_08", category="adversarial", query="Calculate 17.5% of 240.",
    expected_answer="42", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]],
    arg_constraints=[{"tool": "calculator", "must_include_all": ["240"],
                      "must_include_any": ["17.5", "0.175"]}],
    ground_truth_source="arithmetic")
add(id="p4_adv_09", category="adversarial", query="Please divide 1440 by 24 using the calculator.",
    expected_answer="60", operations=[op_calc()], required_tools=["calculator"],
    acceptable_tool_sequences=[["calculator"]],
    arg_constraints=[{"tool": "calculator", "must_include_all": ["1440", "24"]}],
    ground_truth_source="arithmetic")

# E. Ignoring RAG context (document conflicts with common prior).
add(id="p4_adv_10", category="adversarial",
    query="According to our HR policy, how many vacation days do employees get per year? (Not the typical US number - check the document.)",
    expected_answer="20", operations=[{"op_id": "rag_lookup", "source": "rag"}],
    required_tools=[], acceptable_tool_sequences=[["rag"]],
    required_information=["20"], expected_context=["hr_policy"],
    ground_truth_source="documents/hr_policy.txt")
add(id="p4_adv_11", category="adversarial",
    query="Per our sales playbook, who approves discounts up to 15% - the CFO or someone else?",
    expected_answer="Regional Sales Director",
    operations=[{"op_id": "rag_lookup", "source": "rag"}],
    required_tools=[], acceptable_tool_sequences=[["rag"]],
    required_information=["Regional Sales Director"], expected_context=["sales_playbook"],
    ground_truth_source="documents/sales_playbook.txt")

# F. Hallucination traps: info ABSENT from docs; correct behavior = admit gap.
for cid, q in [
    ("p4_adv_12", "According to the remote work policy, how many pet-friendly offices does GlobalTech have?"),
    ("p4_adv_13", "What is the salary band for Senior Engineers according to the HR policy document?"),
]:
    add(id=cid, category="adversarial", query=q,
        operations=[{"op_id": "rag_lookup", "source": "rag"}],
        required_tools=[], acceptable_tool_sequences=[["rag"]],
        forbidden_in_answer=["\\$\\d", r"\b\d{4,}\b"],
        expected_answer="information not specified in the document",
        ground_truth_source="documents (absent fact)",
        notes="correct answer acknowledges absence; asserting a concrete figure fails")

# G. Contradiction probe.
add(id="p4_adv_14", category="adversarial",
    query="Does GlobalTech offer unlimited vacation days?",
    expected_answer="No - 20 days per year",
    operations=[{"op_id": "rag_lookup", "source": "rag"}],
    required_tools=[], acceptable_tool_sequences=[["rag"]],
    required_information=["20"], expected_context=["hr_policy"],
    ground_truth_source="documents/hr_policy.txt",
    notes="answer must NOT affirm unlimited vacation")

# H. Ambiguous wording: clarification or reasonable search both valid.
add(id="p4_adv_15", category="adversarial", query="How much does it cost?",
    operations=[], required_tools=[],
    acceptable_tool_sequences=[[], ["web_search"]],
    notes="ambiguous; clarification final OR reasonable search accepted",
    ground_truth_source="n/a")
add(id="p4_adv_16", category="adversarial", query="When do we publish?",
    operations=[{"op_id": "maybe_rag", "source": "rag"}], required_tools=[],
    acceptable_tool_sequences=[[], ["rag"]],
    notes="ambiguous; blog-Tuesday answer via rag OR clarification accepted",
    ground_truth_source="documents/marketing_guidelines.txt")
add(id="p4_adv_17", category="adversarial", query="Who approves it?",
    operations=[], required_tools=[],
    acceptable_tool_sequences=[[], ["rag"], ["web_search"]],
    notes="ambiguous pronoun; clarification accepted",
    ground_truth_source="n/a")

# I. Multiple-valid-sequence probes.
add(id="p4_adv_18", category="adversarial",
    query="What are the populations of Portugal and Greece, and how big is the difference between them?",
    operations=[{"op_id": "pops", "tool": "web_search", "must_cover": ["portugal", "greece"]},
                op_calc("diff")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[500000, 2500000],
    ground_truth_source="live_web+arithmetic")
add(id="p4_adv_19", category="adversarial",
    query="Find the lengths of the Nile and the Amazon rivers in kilometers and give me the difference.",
    operations=[{"op_id": "rivers", "tool": "web_search", "must_cover": ["nile", "amazon"]},
                op_calc("diff")],
    required_tools=["web_search", "calculator"],
    acceptable_tool_sequences=[["web_search", "web_search", "calculator"],
                               ["web_search", "calculator"]],
    expected_answer_range=[0, 1000],
    notes="sources conflict (Nile vs Amazon debated); loose band",
    ground_truth_source="live_web+arithmetic")

# J. Conflicting-information handling.
add(id="p4_adv_20", category="adversarial",
    query="Some companies offer 25 PTO days. What does OUR hr_policy document say - how many PTO days do we get?",
    expected_answer="20", operations=[{"op_id": "rag_lookup", "source": "rag"}],
    required_tools=[], acceptable_tool_sequences=[["rag"]],
    required_information=["20"], expected_context=["hr_policy"],
    ground_truth_source="documents/hr_policy.txt",
    notes="external distractor; answer must follow the document")

# ─────────────────────────────────────────────────────────────────────────────
assert len(CASES) == 100, f"expected 100 cases, got {len(CASES)}"
from collections import Counter
print(Counter(c["category"] for c in CASES))

out = Path("evaluation/datasets/phase4_quality_100.json")
out.write_text(json.dumps(CASES, indent=2), encoding="utf-8")
print(f"Wrote {len(CASES)} cases -> {out}")
