import json
from langchain_core.messages import HumanMessage, SystemMessage
from llm import llm

def evaluate_semantic(query, expected_answer, actual_answer, combined_context=None):
    metrics = {}
    
    # 1. Answer Correctness
    if expected_answer:
        prompt = f"""You are an expert evaluator. Compare the ACTUAL ANSWER to the EXPECTED ANSWER for the QUERY.
QUERY: {query}
EXPECTED ANSWER: {expected_answer}
ACTUAL ANSWER: {actual_answer}

Return a JSON object with 'correct' (boolean), 'score' (float 0.0 to 1.0), and 'reason' (string).
Do not return anything except the JSON object.
"""
        try:
            res = llm.invoke([SystemMessage(content=prompt)]).content
            # basic json extraction
            json_str = res[res.find('{'):res.rfind('}')+1]
            correctness_data = json.loads(json_str)
            metrics["answer_correctness"] = correctness_data
        except Exception as e:
            metrics["answer_correctness"] = {"correct": False, "score": 0.0, "reason": f"Evaluation failed: {e}"}

    # 2. Faithfulness
    if combined_context:
        prompt = f"""You are an expert evaluator. Assess if the ACTUAL ANSWER is purely supported by the RETRIEVED CONTEXT.
QUERY: {query}
RETRIEVED CONTEXT: {combined_context}
ACTUAL ANSWER: {actual_answer}

Return a JSON object with 'status' (one of: 'supported', 'unsupported', 'partially_supported'), 'score' (float 0.0 to 1.0), and 'reason' (string).
Do not return anything except the JSON object.
"""
        try:
            res = llm.invoke([SystemMessage(content=prompt)]).content
            json_str = res[res.find('{'):res.rfind('}')+1]
            faith_data = json.loads(json_str)
            metrics["faithfulness"] = faith_data
        except Exception as e:
            metrics["faithfulness"] = {"status": "unsupported", "score": 0.0, "reason": f"Evaluation failed: {e}"}

    return metrics
