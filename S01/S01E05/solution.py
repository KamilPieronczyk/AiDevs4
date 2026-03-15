import os
import json
import time
import re
import requests
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

AIDEVS_API_KEY = os.environ["AIDEVS_API_KEY"]
ENDPOINT = "https://hub.ag3nts.org/verify"
MAX_AGENT_ITERATIONS = 25
MAX_503_RETRIES = 6

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

with open(os.path.join(os.path.dirname(__file__), "system_prompt.md")) as f:
    raw = f.read()
SYSTEM_PROMPT = re.sub(r'^---.*?---\s*', '', raw, flags=re.DOTALL).strip()
MODEL = "gpt-5.4"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "api_call",
            "description": (
                "POST to the railway API. The tool automatically adds apikey and task='railway'. "
                "You control the full 'answer' body. "
                "Handles 503 retries automatically. "
                "Returns: status_code, all response headers, full response body."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "object",
                        "description": (
                            "The full 'answer' field of the request body. "
                            "E.g. {\"action\": \"help\"} or {\"action\": \"activate\", \"route\": \"X-01\"}. "
                            "Use exactly the field names and values documented by the API."
                        ),
                    },
                    "delay": {
                        "type": "number",
                        "description": "Seconds to wait BEFORE the call. Use to respect rate-limit resets.",
                    },
                },
                "required": ["answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "api_batch",
            "description": (
                "Execute a sequence of API calls one after another. "
                "Useful when you already know the required sequence from the docs. "
                "Stops early if a flag {FLG:...} is found."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "calls": {
                        "type": "array",
                        "description": "Ordered list of calls to execute.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "object"},
                                "delay": {"type": "number"},
                            },
                            "required": ["answer"],
                        },
                    }
                },
                "required": ["calls"],
            },
        },
    },
]


def _do_api_call(answer, delay):
    if delay and delay > 0:
        logger.info(f"Sleeping {delay}s (rate-limit delay)")
        time.sleep(delay)

    payload = {"apikey": AIDEVS_API_KEY, "task": "railway", "answer": answer}
    logger.info(f"→ POST answer={json.dumps(answer)}")

    backoff = 2
    for attempt in range(MAX_503_RETRIES):
        try:
            resp = requests.post(ENDPOINT, json=payload, timeout=30)
        except requests.RequestException as e:
            logger.warning(f"Request error: {e}, retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue

        all_headers = dict(resp.headers)
        logger.info(f"← status={resp.status_code} headers={json.dumps(all_headers)}")
        logger.info(f"← body={resp.text[:500]}")

        if resp.status_code == 503:
            wait = backoff
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = int(retry_after)
                except ValueError:
                    pass
            logger.warning(f"503, waiting {wait}s (attempt {attempt+1}/{MAX_503_RETRIES})")
            time.sleep(wait)
            backoff = min(backoff * 2, 60)
            continue

        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        return {"status_code": resp.status_code, "headers": all_headers, "body": body}

    return {"status_code": 503, "headers": {}, "body": {"error": "Max 503 retries exceeded"}}


def execute_tool(name, args):
    if name == "api_call":
        if "answer" not in args:
            return json.dumps({"error": "Missing required field 'answer'. Example: {\"answer\": {\"action\": \"help\"}}"})
        result = _do_api_call(answer=args["answer"], delay=args.get("delay", 0))
        return json.dumps(result)

    if name == "api_batch":
        results = []
        for call in args.get("calls", []):
            result = _do_api_call(answer=call["answer"], delay=call.get("delay", 0))
            results.append(result)
            if "{FLG:" in json.dumps(result.get("body", "")):
                logger.success("Flag detected in batch, stopping early")
                break
        return json.dumps(results)

    return json.dumps({"error": f"Unknown tool: {name}"})


def run_agent():
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Activate railway route X-01. Start with the help action."},
    ]

    for iteration in range(MAX_AGENT_ITERATIONS):
        logger.info(f"=== iteration {iteration} ===")
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        msg = response.choices[0].message
        finish = response.choices[0].finish_reason
        logger.info(f"finish={finish} content={str(msg.content)[:300]}")
        messages.append(msg.model_dump(exclude_unset=True))

        if msg.content and "{FLG:" in msg.content:
            logger.success(f"FLAG: {msg.content}")
            return msg.content

        if finish == "stop":
            return msg.content

        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                logger.info(f"Tool: {fn_name}({json.dumps(fn_args)[:300]})")
                result = execute_tool(fn_name, fn_args)
                if "{FLG:" in result:
                    logger.success(f"FLAG in tool result: {result}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    logger.error("Max iterations reached")
    return None


if __name__ == "__main__":
    result = run_agent()
    print("\n=== RESULT ===")
    print(result)
