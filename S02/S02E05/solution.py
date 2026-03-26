import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import find_dotenv, load_dotenv
from loguru import logger
from openai import OpenAI, RateLimitError

sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.prompts import load_prompt

load_dotenv(find_dotenv())

TASK = "drone"
VERIFY_URL = "https://hub.ag3nts.org/verify"
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
MAX_API_ROUNDS = 8
MAX_REVIEW_ROUNDS = 3
MAX_TOOL_STEPS = 8

SOLVER_PROMPT = load_prompt(str(BASE_DIR / "solver_prompt.md"))
REVIEWER_A_PROMPT = load_prompt(str(BASE_DIR / "reviewer_a_prompt.md"))
REVIEWER_B_PROMPT = load_prompt(str(BASE_DIR / "reviewer_b_prompt.md"))
VISION_PROMPT = load_prompt(str(BASE_DIR / "vision_prompt.md"))


def get_client():
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def compact(value, limit=4000):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... <truncated {len(text) - limit} chars>"


def to_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def strip_html_tags(text):
    text = html.unescape(text)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ensure_relative(path):
    full = (BASE_DIR / path).resolve()
    if BASE_DIR.resolve() not in [full, *full.parents]:
        raise ValueError(f"path outside lesson dir: {path}")
    full.parent.mkdir(parents=True, exist_ok=True)
    return full


def extract_json(text):
    if not text:
        raise ValueError("empty model response")
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"cannot parse json from: {text[:400]}")


def chat_with_retry(model, messages, tools=None, temperature=0):
    delay = 3
    for attempt in range(8):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            return get_client().chat.completions.create(**kwargs)
        except RateLimitError:
            logger.warning(f"rate limit for {model}, retry in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"rate limit retries exhausted for {model}")


def post_verify(answer):
    payload = {
        "apikey": os.environ["AIDEVS_API_KEY"],
        "task": TASK,
        "answer": answer,
    }
    logger.info(f"verify -> {compact(answer, 600)}")
    response = requests.post(VERIFY_URL, json=payload, timeout=60)
    result = response.json()
    logger.info(f"verify <- {compact(result, 600)}")
    return result


def contains_flag(value):
    return "FLG:" in compact(value, 12000)


def insert_before_fly(instructions, command):
    if command in instructions:
        return instructions
    if "flyToLocation" in instructions:
        index = instructions.index("flyToLocation")
        instructions.insert(index, command)
        return instructions
    instructions.append(command)
    return instructions


def normalize_instructions(instructions):
    normalized = []
    for instruction in instructions:
        item = instruction.strip()

        match = re.fullmatch(r"setSector\((\d+)\s*,\s*(\d+)\)", item, flags=re.IGNORECASE)
        if match:
            item = f"set({match.group(1)},{match.group(2)})"

        match = re.fullmatch(r"setAltitude\((\d+)\)", item, flags=re.IGNORECASE)
        if match:
            item = f"set({match.group(1)}m)"

        match = re.fullmatch(r"set\(power\s*=\s*(\d+)\)", item, flags=re.IGNORECASE)
        if match:
            item = f"set({match.group(1)}%)"

        normalized.append(item)

    deduped = []
    for item in normalized:
        if item not in deduped:
            deduped.append(item)
    return deduped


def apply_feedback_mutations(instructions, feedback):
    mutated = normalize_instructions(list(instructions))
    text = compact(feedback, 4000).lower()

    if "power set to 0%" in text or "engine power" in text:
        mutated = insert_before_fly(mutated, "set(engineON)")
        mutated = insert_before_fly(mutated, "set(50%)")

    if "without a return instruction" in text or "return instruction" in text:
        mutated = insert_before_fly(mutated, "set(return)")

    if "not properly configured" in text:
        if "hardReset" not in mutated:
            mutated.insert(0, "hardReset")
        mutated = insert_before_fly(mutated, "set(destroy)")

    if mutated and stateful_attempt(mutated):
        if "hardReset" not in mutated:
            mutated.insert(0, "hardReset")

    return mutated


def stateful_attempt(instructions):
    return any(
        item.startswith("setDestinationObject(") or item == "flyToLocation"
        for item in instructions
    )


def tool_read_file(path):
    full = ensure_relative(path)
    if not full.exists():
        return {"ok": False, "error": f"missing file: {path}"}

    data = full.read_bytes()
    try:
        text = data.decode("utf-8")
        return {
            "ok": True,
            "path": str(full.relative_to(BASE_DIR)),
            "size": len(data),
            "text": text,
        }
    except UnicodeDecodeError:
        return {
            "ok": True,
            "path": str(full.relative_to(BASE_DIR)),
            "size": len(data),
            "message": "binary file",
        }


def tool_save_file(path, content):
    full = ensure_relative(path)
    full.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(full.relative_to(BASE_DIR)), "size": len(content)}


def tool_download_file(url, path):
    full = ensure_relative(path)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    full.write_bytes(response.content)

    result = {
        "ok": True,
        "path": str(full.relative_to(BASE_DIR)),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "size": len(response.content),
    }

    if "text" in (response.headers.get("content-type") or "") or full.suffix in {".html", ".md", ".txt", ".json"}:
        text = response.text
        result["text_preview"] = strip_html_tags(text)[:3000]

    return result


def tool_analyze_image(image_url, notes=""):
    user_message = [
        {"type": "text", "text": VISION_PROMPT.content},
        {"type": "text", "text": f"Additional notes:\n{notes or 'none'}"},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    response = chat_with_retry(
        VISION_PROMPT.model,
        [{"role": "user", "content": user_message}],
    )
    content = response.choices[0].message.content
    parsed = extract_json(content)
    return parsed


def sample_map(image_url):
    prompts = [
        "Count the grid carefully and find the dam sector.",
        "Focus on the strongest blue water and the spillway or gate structure.",
        "Ignore buildings and look for the dam face next to deep blue water.",
    ]
    samples = []
    votes = {}

    for note in prompts:
        result = tool_analyze_image(image_url, note)
        samples.append(result)
        sector = result.get("target_sector") or {}
        key = (
            result.get("columns"),
            result.get("rows"),
            sector.get("x"),
            sector.get("y"),
        )
        votes[key] = votes.get(key, 0) + 1

    best_key, best_votes = max(votes.items(), key=lambda item: item[1])
    return {
        "columns": best_key[0],
        "rows": best_key[1],
        "target_sector": {"x": best_key[2], "y": best_key[3]},
        "confidence": "high" if best_votes >= 2 else "medium",
        "evidence": f"Best of {len(samples)} GPT-5.4 vision samples.",
        "samples": samples,
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "Download a remote file into the lesson directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["url", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local file from the lesson directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": "Save a UTF-8 text file inside the lesson directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Analyze an image with the dedicated GPT-5.4 vision prompt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["image_url"],
            },
        },
    },
]


def call_tool(name, args):
    if name == "download_file":
        return tool_download_file(args["url"], args["path"])
    if name == "read_file":
        return tool_read_file(args["path"])
    if name == "save_file":
        return tool_save_file(args["path"], args["content"])
    if name == "analyze_image":
        return tool_analyze_image(args["image_url"], args.get("notes", ""))
    raise ValueError(f"unknown tool: {name}")


def run_tool_agent(prompt, payload):
    messages = [
        {"role": "system", "content": prompt.content},
        {"role": "user", "content": to_json(payload)},
    ]

    for step in range(MAX_TOOL_STEPS):
        response = chat_with_retry(prompt.model, messages, tools=TOOLS)
        message = response.choices[0].message

        if not message.tool_calls:
            content = message.content or ""
            logger.info(f"{prompt.model} final -> {compact(content, 800)}")
            return extract_json(content)

        assistant_message = {"role": "assistant", "content": message.content or ""}
        assistant_message["tool_calls"] = []
        for tool_call in message.tool_calls:
            assistant_message["tool_calls"].append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            )
        messages.append(assistant_message)

        for tool_call in message.tool_calls:
            args = extract_json(tool_call.function.arguments or "{}")
            result = call_tool(tool_call.function.name, args)
            logger.info(f"tool {tool_call.function.name} -> {compact(result, 800)}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": to_json(result),
                }
            )

    raise RuntimeError("tool loop exceeded max steps")


def run_json_agent(prompt, payload):
    messages = [
        {"role": "system", "content": prompt.content},
        {"role": "user", "content": to_json(payload)},
    ]
    response = chat_with_retry(prompt.model, messages)
    content = response.choices[0].message.content or ""
    logger.info(f"{prompt.model} final -> {compact(content, 800)}")
    return extract_json(content)


def summarize_feedback(review_a, review_b):
    combined = []
    for label, review in [("reviewer_a", review_a), ("reviewer_b", review_b)]:
        for blocker in review.get("blockers", []):
            combined.append(f"{label}: {blocker}")
        for suggestion in review.get("suggestions", []):
            combined.append(f"{label}: {suggestion}")
    return combined


def has_blockers(review_a, review_b):
    return bool(review_a.get("blockers") or review_b.get("blockers"))


def build_initial_state():
    api_key = os.environ["AIDEVS_API_KEY"]
    return {
        "task": TASK,
        "mission": {
            "real_target": "dam near Zarnowiec power plant",
            "power_plant_id": "PWR6132PL",
            "expected_effect": "drop the bomb on the dam sector, not the power plant buildings",
        },
        "resources": {
            "doc_url": "https://hub.ag3nts.org/dane/drone.html",
            "map_url": f"https://hub.ag3nts.org/data/{api_key}/drone.png",
        },
        "known_facts": {
            "map": None,
        },
        "attempts": [],
        "latest_api_feedback": None,
        "latest_reviews": [],
        "latest_candidate": None,
    }


def fallback_sectors(state):
    sectors = []
    known_map = state["known_facts"].get("map") or {}
    target_sector = known_map.get("target_sector") or {}
    if target_sector.get("x") and target_sector.get("y"):
        sectors.append((target_sector["x"], target_sector["y"]))

    for sector in [(2, 4), (3, 4)]:
        if sector not in sectors:
            sectors.append(sector)
    return sectors


def fallback_instructions(sector):
    x, y = sector
    return [
        "hardReset",
        "setDestinationObject(PWR6132PL)",
        f"set({x},{y})",
        "set(engineON)",
        "set(50%)",
        "set(10m)",
        "set(destroy)",
        "set(return)",
        "flyToLocation",
    ]


def run_fallback_search(state):
    logger.warning("switching to deterministic fallback search")
    for sector in fallback_sectors(state):
        instructions = fallback_instructions(sector)
        response = post_verify({"instructions": instructions})
        state["attempts"].append(
            {
                "round": f"fallback-{sector[0]}-{sector[1]}",
                "instructions": instructions,
                "response": response,
            }
        )
        if contains_flag(response):
            print(response)
            return response
        state["latest_api_feedback"] = {"source": "verify", "payload": response}
    raise RuntimeError("fallback search exhausted without flag")


def solve():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    state = build_initial_state()
    state["known_facts"]["map"] = sample_map(state["resources"]["map_url"])
    target_sector = (state["known_facts"]["map"] or {}).get("target_sector") or {}
    if not target_sector.get("x") or not target_sector.get("y"):
        return run_fallback_search(state)

    for api_round in range(1, MAX_API_ROUNDS + 1):
        logger.info(f"api round {api_round}")

        candidate = None
        for review_round in range(1, MAX_REVIEW_ROUNDS + 1):
            logger.info(f"review round {review_round}")
            solver_input = {
                "state": state,
                "instructions_requirements": {
                    "return_json_shape": {
                        "instructions": ["string"],
                        "summary": "string",
                        "state_patch": {
                            "known_facts": {},
                        },
                    }
                },
            }
            try:
                candidate = run_tool_agent(SOLVER_PROMPT, solver_input)
            except Exception as exc:
                logger.warning(f"solver failed, using fallback search: {exc}")
                return run_fallback_search(state)
            candidate["instructions"] = normalize_instructions(candidate.get("instructions", []))

            if state["latest_api_feedback"]:
                candidate["instructions"] = apply_feedback_mutations(
                    candidate["instructions"],
                    state["latest_api_feedback"],
                )

            state["latest_candidate"] = candidate

            patch = candidate.get("state_patch") or {}
            if patch.get("known_facts"):
                state["known_facts"].update(patch["known_facts"])

            with ThreadPoolExecutor(max_workers=2) as pool:
                future_a = pool.submit(
                    run_json_agent,
                    REVIEWER_A_PROMPT,
                    {"state": state, "candidate": candidate},
                )
                future_b = pool.submit(
                    run_json_agent,
                    REVIEWER_B_PROMPT,
                    {"state": state, "candidate": candidate},
                )
                review_a = future_a.result()
                review_b = future_b.result()

            state["latest_reviews"] = [review_a, review_b]

            if not has_blockers(review_a, review_b):
                break

            state["latest_api_feedback"] = {
                "source": "internal_review",
                "items": summarize_feedback(review_a, review_b),
            }

        if not candidate or not candidate.get("instructions"):
            raise RuntimeError("solver returned no instructions")

        answer = {"instructions": candidate["instructions"]}
        response = post_verify(answer)
        state["attempts"].append(
            {
                "round": api_round,
                "instructions": candidate["instructions"],
                "response": response,
            }
        )

        if contains_flag(response):
            print(response)
            return response

        state["latest_api_feedback"] = {
            "source": "verify",
            "payload": response,
        }

    raise RuntimeError("flag not found within max api rounds")


if __name__ == "__main__":
    solve()
