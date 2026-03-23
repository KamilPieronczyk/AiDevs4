import os
import re
import json
import time
import requests
import tiktoken
from openai import OpenAI, RateLimitError
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

API_KEY = os.environ["AIDEVS_API_KEY"]
LOG_URL = f"https://hub.ag3nts.org/data/{API_KEY}/failure.log"
VERIFY_URL = "https://hub.ag3nts.org/verify"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MAIN_MODEL = "gpt-5.4-mini"
SUB_MODEL = "gpt-5.4-mini"

_log_lines: list[str] = []
enc = tiktoken.get_encoding("cl100k_base")
TOKEN_LIMIT = 1500

# Pre-computed at startup: {component_id: [normalized_lines]}
_component_map: dict[str, list[str]] = {}
# Pre-compressed by sub-agent: {component_id: compressed_str}
_compressed_cache: dict[str, str] = {}

SEVERITY_PAT = re.compile(r"\[(CRIT|ERRO|ERROR|WARN)\]")
TS_PAT = re.compile(r"\[(\d{4}-\d{2}-\d{2}) (\d{1,2}:\d{2}):\d{2}\]")
COMP_PAT = re.compile(r"\[\w+\]\s+(\S+)")


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


def sort_by_ts(lines: list[str]) -> list[str]:
    def key(l):
        m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2})\]", l)
        return m.group(1) if m else ""
    return sorted(lines, key=key)


def normalize_line(raw: str):
    m_ts = TS_PAT.search(raw)
    m_sev = SEVERITY_PAT.search(raw)
    if not m_ts or not m_sev:
        return None
    date, hm = m_ts.group(1), m_ts.group(2)
    level = m_sev.group(1)
    rest = re.sub(r"^\[.*?\]\s*\[.*?\]\s*\[.*?\]\s*", "", raw).strip()
    return f"[{date} {hm}] [{level}] {rest}"


def chat_with_retry(model, messages, tools=None):
    for attempt in range(8):
        try:
            kwargs = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            wait = min(3 * 2 ** attempt, 120)
            logger.warning(f"Rate limit {wait}s ({attempt+1}/8)")
            time.sleep(wait)
    raise RuntimeError("Rate limit retries exhausted")


# ---------------------------------------------------------------------------
# Startup: Python pre-processing (zero LLM cost)
# ---------------------------------------------------------------------------

def build_component_map():
    """Filter all CRIT/ERRO/WARN lines and group by component ID."""
    global _component_map
    # Raw format: [2026-03-18 06:04:52] [CRIT] COMPONENT_ID rest of message
    raw_comp_pat = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}\] \[\w+\] (\S+)")
    for line in _log_lines:
        if not SEVERITY_PAT.search(line):
            continue
        normalized = normalize_line(line)
        if not normalized:
            continue
        m = raw_comp_pat.search(line)
        comp = m.group(1) if m else "UNKNOWN"
        _component_map.setdefault(comp, []).append(normalized)

    for comp in _component_map:
        _component_map[comp] = sort_by_ts(_component_map[comp])

    total = sum(len(v) for v in _component_map.values())
    logger.info(f"Component map: {len(_component_map)} components, {total} CRIT/ERRO/WARN lines")


# ---------------------------------------------------------------------------
# Sub-agent: compress lines for one component (called on-demand)
# ---------------------------------------------------------------------------

SUB_SYSTEM = """You compress power plant log entries into a minimal set.

Given raw log lines for one component:
- Select ≤5 most failure-relevant lines (prefer CRIT > ERRO > WARN)
- Compress each description to ≤6 words, keeping key info (trip, fault, threshold, runaway, etc.)
- Format: [YYYY-MM-DD HH:MM] [LEVEL] COMPONENT short_desc
- Return ONLY the log lines — no explanations, no headers
- Sorted chronologically"""


def compress_component_llm(component_id: str, lines: list[str]) -> str:
    if component_id in _compressed_cache:
        return _compressed_cache[component_id]
    if not lines:
        return ""
    sample = "\n".join(lines[:40])
    prompt = f"Component: {component_id}\n\nLines:\n{sample}"
    messages = [{"role": "system", "content": SUB_SYSTEM}, {"role": "user", "content": prompt}]
    resp = chat_with_retry(SUB_MODEL, messages)
    result = (resp.choices[0].message.content or "").strip()
    _compressed_cache[component_id] = result
    logger.info(f"Compressed {component_id}: {len(lines)} lines → {count_tokens(result)} tokens")
    return result


# ---------------------------------------------------------------------------
# Main agent tools
# ---------------------------------------------------------------------------

def tool_list_components(_args=None) -> str:
    """Return all components with CRIT/ERRO/WARN events and their line counts."""
    rows = []
    for comp, lines in sorted(_component_map.items()):
        levels = {"CRIT": 0, "ERRO": 0, "ERROR": 0, "WARN": 0}
        for l in lines:
            for sev in levels:
                if f"[{sev}]" in l:
                    levels[sev] += 1
        crit = levels["CRIT"]
        erro = levels["ERRO"] + levels["ERROR"]
        warn = levels["WARN"]
        rows.append(f"{comp}: {len(lines)} lines (CRIT={crit} ERRO={erro} WARN={warn})")
    return f"# {len(_component_map)} components with CRIT/ERRO/WARN events:\n" + "\n".join(rows)


def tool_compress_component(args: dict) -> str:
    """Compress a component's log lines via sub-agent. Returns ready-to-use log lines."""
    comp = args["component_id"]
    if comp not in _component_map:
        return f"Component '{comp}' not found. Check list_components for valid IDs."
    lines = _component_map[comp]
    result = compress_component_llm(comp, lines)
    tokens = count_tokens(result)
    return f"# {comp} compressed ({tokens} tokens):\n{result}"


def tool_count_tokens(args: dict) -> str:
    """Count tokens in a text. Use before send_to_central to verify under limit."""
    text = args["text"]
    n = count_tokens(text)
    remaining = TOKEN_LIMIT - n
    status = "OK" if n <= TOKEN_LIMIT else "OVER LIMIT"
    return json.dumps({"tokens": n, "limit": TOKEN_LIMIT, "remaining": remaining, "status": status})


def tool_sort_logs(args: dict) -> str:
    """Sort log lines chronologically and return sorted string with token count."""
    text = args["logs"]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    sorted_lines = sort_by_ts(lines)
    result = "\n".join(sorted_lines)
    n = count_tokens(result)
    return json.dumps({"sorted_logs": result, "tokens": n, "lines": len(sorted_lines), "status": "OK" if n <= TOKEN_LIMIT else "OVER LIMIT"})


def tool_send_to_central(args: dict) -> str:
    """Send logs to Central. Auto-sorts chronologically. Rejects if over 1500 tokens."""
    logs = args["logs"].strip()

    # Auto-sort before sending
    lines = [l.strip() for l in logs.split("\n") if l.strip()]
    lines = sort_by_ts(lines)
    logs = "\n".join(lines)

    n = count_tokens(logs)
    if n > TOKEN_LIMIT:
        return json.dumps({"error": f"Over limit: {n}/{TOKEN_LIMIT} tokens. Remove lines to fit."})

    payload = {"apikey": API_KEY, "task": "failure", "answer": {"logs": logs}}
    resp = requests.post(VERIFY_URL, json=payload, timeout=30)
    result = resp.json()
    logger.info(f"Central ({n} tokens, {len(lines)} lines): {result}")
    return json.dumps({"response": result, "tokens_sent": n, "lines_sent": len(lines)})


MAIN_TOOLS = [
    {"type": "function", "function": {
        "name": "list_components",
        "description": "List all components that have CRIT/ERRO/WARN events, with counts. Call once to see what's available.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "compress_component",
        "description": "Get compressed log lines for one component (≤5 lines, ≤6 words each). Results are cached. Use for each component you want to include.",
        "parameters": {"type": "object", "properties": {
            "component_id": {"type": "string", "description": "Exact component ID from list_components"}
        }, "required": ["component_id"]}
    }},
    {"type": "function", "function": {
        "name": "count_tokens",
        "description": "Count tokens in a text. ALWAYS call this before send_to_central to verify you're under 1500.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Text to count tokens for"}
        }, "required": ["text"]}
    }},
    {"type": "function", "function": {
        "name": "sort_logs",
        "description": "Sort log lines chronologically and get token count. Use when you've assembled a draft.",
        "parameters": {"type": "object", "properties": {
            "logs": {"type": "string", "description": "Newline-separated log lines to sort"}
        }, "required": ["logs"]}
    }},
    {"type": "function", "function": {
        "name": "send_to_central",
        "description": "Send final logs to Central API. Auto-sorts chronologically. Returns technician feedback — use it to identify missing components.",
        "parameters": {"type": "object", "properties": {
            "logs": {"type": "string", "description": "Compressed log string, one event per line"}
        }, "required": ["logs"]}
    }},
]

MAIN_TOOL_MAP = {
    "list_components": tool_list_components,
    "compress_component": tool_compress_component,
    "count_tokens": tool_count_tokens,
    "sort_logs": tool_sort_logs,
    "send_to_central": tool_send_to_central,
}

MAIN_SYSTEM = f"""You are a power plant failure analyst. Build a compressed log (≤{TOKEN_LIMIT} tokens) and get {{FLG:...}} from Central.

OPTIMAL WORKFLOW:
1. list_components — see all components with CRIT/ERRO/WARN events
2. compress_component for each important component (prioritize CRIT > ERRO > WARN count)
   Focus on: power (PWR*), cooling (ECCS*), water/pumps (WTANK*, WTRPMP*), turbines (STMTURB*), FIRMWARE, reactor
3. Assemble your draft string by concatenating compressed results
4. count_tokens on your draft — if over {TOKEN_LIMIT}, drop lowest-priority components (WARN-only ones)
5. sort_logs on your draft to ensure chronological order
6. send_to_central — read feedback carefully
7. If feedback mentions missing component → compress_component(THAT_ID) → add to draft → count_tokens → send_to_central
8. Repeat until {{FLG:...}}

TOKEN BUDGET STRATEGY:
- Each component compresses to ~120 tokens
- {TOKEN_LIMIT} tokens ÷ ~120 = ~12 components max
- Start with CRIT-heavy components, add WARN-only if space allows
- Always count_tokens BEFORE send_to_central

RULES:
- send_to_central auto-sorts, but sort_logs first to see final token count
- Never guess token count — always use count_tokens tool
- compress_component results are cached — calling twice is free"""


def run_main_agent():
    messages = [
        {"role": "system", "content": MAIN_SYSTEM},
        {"role": "user", "content": "Start: list_components, then compress the most critical ones, assemble under 1500 tokens, send to Central."}
    ]

    for iteration in range(1, 40):
        logger.info(f"=== Iteration {iteration}/40 ===")

        if len(messages) > 22:
            tail = messages[-18:]
            # Don't start on a 'tool' message — it would orphan the preceding tool_calls
            while tail and isinstance(tail[0], dict) and tail[0].get("role") == "tool":
                tail = tail[1:]
            messages = messages[:2] + tail

        resp = chat_with_retry(MAIN_MODEL, messages, MAIN_TOOLS)
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            content = msg.content or ""
            logger.info(f"Agent text: {content[:150]}")
            print(f"\nAgent:\n{content}")
            if "FLG:" in content:
                return content
            messages.append({"role": "user", "content": "Continue — use tools to fix and resubmit."})
            continue

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            logger.info(f"→ {name}({', '.join(f'{k}={str(v)[:30]}' for k,v in args.items())})")
            result = MAIN_TOOL_MAP[name](args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            if "FLG:" in str(result):
                logger.success(f"FLAG: {result}")
                print(f"\n=== FLAG ===\n{result}")
                return result

    logger.warning("Max iterations reached")
    return None


if __name__ == "__main__":
    logger.info(f"Downloading log...")
    resp = requests.get(LOG_URL, timeout=60)
    resp.raise_for_status()
    _log_lines = resp.text.splitlines()
    logger.info(f"Downloaded {len(_log_lines)} lines")

    logger.info("Building component map (Python, no LLM)...")
    build_component_map()

    result = run_main_agent()
    print(f"\nResult: {result}")
