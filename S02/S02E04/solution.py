import os
import re
import json
import time
import html
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from openai import OpenAI, RateLimitError
from dotenv import load_dotenv, find_dotenv
from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.prompts import load_prompt

load_dotenv(find_dotenv())

API_KEY = os.environ["AIDEVS_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
ZMAIL_URL = "https://hub.ag3nts.org/api/zmail"
VERIFY_URL = "https://hub.ag3nts.org/verify"
MAX_ITERATIONS = 50
MAX_HTTP_RETRIES = 8

BASE_DIR = Path(__file__).resolve().parent
MAIN_PROMPT = load_prompt(str(BASE_DIR / "system_prompt.md"))
DELEGATE_PROMPT = load_prompt(str(BASE_DIR / "delegate_prompt.md"))


def get_client():
    return OpenAI(api_key=OPENAI_API_KEY)


def safe_json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}


def to_text(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def has_flag(value):
    return "FLG:" in to_text(value)


def compact(value, limit=14000):
    text = to_text(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... <truncated {len(text) - limit} chars>"


def http_post_json(url, payload):
    backoff = 2
    for attempt in range(MAX_HTTP_RETRIES):
        try:
            resp = requests.post(url, json=payload, timeout=45)
        except requests.RequestException as exc:
            logger.warning(f"HTTP error on {url}: {exc}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")
            wait = backoff
            if retry_after:
                try:
                    wait = int(retry_after)
                except ValueError:
                    pass
            logger.warning(f"{url} -> {resp.status_code}, waiting {wait}s")
            time.sleep(wait)
            backoff = min(backoff * 2, 60)
            continue

        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        return {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": body,
        }

    return {"status_code": 599, "headers": {}, "body": {"error": "Max retries exceeded"}}


def chat_with_retry(model, messages, tools=None, response_format=None):
    backoff = 3
    for attempt in range(8):
        try:
            kwargs = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if response_format:
                kwargs["response_format"] = response_format
            return get_client().chat.completions.create(**kwargs)
        except RateLimitError:
            logger.warning(f"OpenAI rate limit, waiting {backoff}s ({attempt + 1}/8)")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
    raise RuntimeError("OpenAI rate limit retries exhausted")


def strip_html_tags(text):
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def collect_strings(node, out):
    if isinstance(node, str):
        cleaned = strip_html_tags(node)
        if cleaned:
            out.append(cleaned)
        return
    if isinstance(node, dict):
        for value in node.values():
            collect_strings(value, out)
        return
    if isinstance(node, list):
        for value in node:
            collect_strings(value, out)


def unique_lines(lines, char_limit=12000):
    seen = set()
    kept = []
    total = 0
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        if total + len(line) + 1 > char_limit:
            break
        kept.append(line)
        total += len(line) + 1
    return "\n".join(kept)


def find_first(node, names):
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in names and isinstance(value, (str, int, float)):
                return str(value)
        for value in node.values():
            found = find_first(value, names)
            if found:
                return found
    if isinstance(node, list):
        for value in node:
            found = find_first(value, names)
            if found:
                return found
    return None


def build_preview(body):
    return {
        "id": find_first(body, {"id", "uid", "messageid", "message_id"}),
        "from": find_first(body, {"from", "sender", "from_email", "fromaddress"}),
        "to": find_first(body, {"to", "recipient", "to_email", "toaddress"}),
        "subject": find_first(body, {"subject", "title"}),
        "date": find_first(body, {"date", "sent_at", "created_at", "timestamp"}),
    }


def infer_delegate_payload(job):
    if job.get("payload"):
        return job["payload"]
    if job.get("message_id"):
        return {"action": "getMessages", "ids": [job["message_id"]]}
    if job.get("message_ids"):
        return {"action": "getMessages", "ids": job["message_ids"]}
    if job.get("thread_id"):
        return {"action": "getThread", "threadID": job["thread_id"]}

    source = " ".join([
        str(job.get("label") or ""),
        str(job.get("goal") or ""),
    ])
    message_ids = re.findall(r"\b[a-f0-9]{32}\b", source, flags=re.IGNORECASE)
    thread_match = re.search(r"\bthread(?:ID)?\s*(\d+)\b", source, flags=re.IGNORECASE)

    if message_ids:
        return {"action": "getMessages", "ids": list(dict.fromkeys(message_ids))}
    if thread_match:
        return {"action": "getThread", "threadID": int(thread_match.group(1))}
    return None


def build_delegate_context(job, fetched):
    strings = []
    collect_strings(fetched, strings)
    normalized = unique_lines(strings, char_limit=12000)
    raw_json = compact(fetched, limit=12000)
    return (
        f"Goal:\n{job['goal']}\n\n"
        f"Fetch payload:\n{json.dumps(job['payload'], ensure_ascii=False)}\n\n"
        f"Normalized text:\n{normalized}\n\n"
        f"Fetched response JSON:\n{raw_json}"
    )


def zmail_request(payload):
    request_payload = dict(payload)
    request_payload["apikey"] = API_KEY
    logger.info(f"zmail -> {json.dumps(payload, ensure_ascii=False)}")
    result = http_post_json(ZMAIL_URL, request_payload)
    logger.info(f"zmail <- {compact(result, 600)}")
    return result


def verify_answer(answer):
    payload = {"apikey": API_KEY, "task": "mailbox", "answer": answer}
    logger.info(f"verify -> {json.dumps(answer, ensure_ascii=False)}")
    result = http_post_json(VERIFY_URL, payload)
    logger.info(f"verify <- {compact(result, 600)}")
    return result


def run_delegate_job(job):
    payload = infer_delegate_payload(job)
    if not payload:
        return {
            "label": job.get("label") or "job",
            "goal": job.get("goal"),
            "analysis": {
                "likely_relevant": False,
                "summary": "missing payload or ids",
                "facts": {"date": None, "password": None, "confirmation_code": None},
                "clues": [],
                "follow_up_queries": [],
            },
        }

    fetched = zmail_request(payload)
    preview = build_preview(fetched.get("body"))

    if fetched.get("status_code", 0) >= 400:
        return {
            "label": job.get("label") or preview.get("subject") or "job",
            "goal": job["goal"],
            "preview": preview,
            "analysis": {"likely_relevant": False, "summary": "fetch failed", "facts": {"date": None, "password": None, "confirmation_code": None}, "clues": [], "follow_up_queries": []},
            "fetch_status": fetched.get("status_code"),
            "fetch_body": fetched.get("body"),
        }

    messages = [
        {"role": "system", "content": DELEGATE_PROMPT.content},
        {"role": "user", "content": build_delegate_context({**job, "payload": payload}, fetched)},
    ]
    resp = chat_with_retry(
        job.get("model") or DELEGATE_PROMPT.model,
        messages,
        response_format={"type": "json_object"},
    )
    analysis = safe_json_loads(resp.choices[0].message.content or "{}")
    return {
        "label": job.get("label") or preview.get("subject") or "job",
        "goal": job["goal"],
        "preview": preview,
        "analysis": analysis,
        "fetch_status": fetched.get("status_code"),
    }


def tool_zmail(args):
    if "payload" not in args:
        return json.dumps({"error": "Missing required field 'payload'."}, ensure_ascii=False)
    action = str(args["payload"].get("action", "")).lower()
    if action in {"getmessage", "getmessages", "getthread"}:
        return json.dumps({
            "error": "Use delegate for full message reads. zmail is for help, inbox, search, and metadata only."
        }, ensure_ascii=False)
    return compact(zmail_request(args["payload"]))


def tool_submit_answer(args):
    if "answer" not in args:
        return json.dumps({"error": "Missing required field 'answer'."}, ensure_ascii=False)
    return compact(verify_answer(args["answer"]))


def tool_delegate(args):
    jobs = args.get("jobs") or []
    if not jobs:
        return json.dumps({"error": "Provide at least one job."}, ensure_ascii=False)

    max_workers = max(1, min(int(args.get("max_workers") or len(jobs)), 6))
    results = [None] * len(jobs)

    # Fetch and analyze each message in parallel to keep main context small.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(run_delegate_job, job): idx
            for idx, job in enumerate(jobs)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = {
                    "label": jobs[idx].get("label") or f"job-{idx + 1}",
                    "goal": jobs[idx].get("goal"),
                    "analysis": {
                        "likely_relevant": False,
                        "summary": f"delegate error: {exc}",
                        "facts": {"date": None, "password": None, "confirmation_code": None},
                        "clues": [],
                        "follow_up_queries": [],
                    },
                }

    return compact({"results": results}, limit=22000)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "zmail",
            "description": (
                "POST any raw payload to the zmail API. "
                "You provide the full payload except apikey, for example "
                "{\"payload\":{\"action\":\"help\",\"page\":1}}. "
                "Use this for help, inbox, search, pagination, and metadata discovery."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "description": "Exact JSON payload for https://hub.ag3nts.org/api/zmail without apikey.",
                    }
                },
                "required": ["payload"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": (
                "Run several mailbox subagents in parallel. "
                "Each job fetches one full message or thread through a raw zmail payload, message_id, message_ids, or thread_id and analyzes it for a focused goal. "
                "Prefer this over pulling full message bodies into the main context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "goal": {"type": "string"},
                                "payload": {
                                    "type": "object",
                                    "description": "Exact zmail payload used to fetch one full message or thread.",
                                },
                                "message_id": {"type": "string"},
                                "message_ids": {"type": "array", "items": {"type": "string"}},
                                "thread_id": {"type": "integer"},
                                "model": {"type": "string"},
                            },
                            "required": ["goal"],
                        },
                    },
                    "max_workers": {
                        "type": "integer",
                        "description": "Optional parallelism limit.",
                    },
                },
                "required": ["jobs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Submit the current candidate answer to the mailbox verifier. "
                "Use the exact answer object shape: password, date, confirmation_code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "object",
                        "properties": {
                            "password": {"type": "string"},
                            "date": {"type": "string"},
                            "confirmation_code": {"type": "string"},
                        },
                        "required": ["password", "date", "confirmation_code"],
                    }
                },
                "required": ["answer"],
            },
        },
    },
]


TOOL_MAP = {
    "zmail": tool_zmail,
    "delegate": tool_delegate,
    "submit_answer": tool_submit_answer,
}


def trim_messages(messages):
    if len(messages) <= 24:
        return messages
    tail = messages[-18:]
    while tail and tail[0].get("role") == "tool":
        tail = tail[1:]
    return messages[:2] + tail


def run_agent():
    messages = [
        {"role": "system", "content": MAIN_PROMPT.content},
        {"role": "user", "content": "Solve mailbox. Start with zmail help, then search and delegate full-message reading."},
    ]

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"=== iteration {iteration}/{MAX_ITERATIONS} ===")
        messages = trim_messages(messages)

        resp = chat_with_retry(MAIN_PROMPT.model, messages, tools=TOOLS)
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_unset=True))

        if msg.content:
            logger.info(f"agent: {msg.content[:400]}")
            if has_flag(msg.content):
                return msg.content

        if not msg.tool_calls:
            messages.append({
                "role": "user",
                "content": "Continue. The mailbox is live, so refresh searches if needed and keep using tools until you get the flag.",
            })
            continue

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = safe_json_loads(tool_call.function.arguments or "{}")
            logger.info(f"tool: {name}({compact(args, 500)})")
            result = TOOL_MAP[name](args)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

            if has_flag(result):
                return result

    return None


if __name__ == "__main__":
    result = run_agent()
    print("\n=== RESULT ===")
    print(result)
