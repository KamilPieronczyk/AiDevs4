import os
import json
import base64
import time
import requests
from openai import OpenAI, RateLimitError
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

API_KEY = os.environ["AIDEVS_API_KEY"]
BASE_URL = "https://hub.ag3nts.org"
BOARD_URL = f"{BASE_URL}/data/{API_KEY}/electricity.png"
TARGET_URL = f"{BASE_URL}/i/solved_electricity.png"
VERIFY_URL = f"{BASE_URL}/verify"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
AGENT_MODEL = "gpt-5.4"
VISION_MODEL = "gpt-5.4"

# In-memory board state — reset on every script run, updated via rotation math
_board_state: dict = {}
_target_state: dict = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CW_ROTATION = {"top": "right", "right": "bottom", "bottom": "left", "left": "top"}

def rotate_connections(connections: list, turns: int) -> list:
    """Apply `turns` clockwise 90° rotations to a list of connection sides."""
    result = list(connections)
    for _ in range(turns % 4):
        result = [CW_ROTATION[c] for c in result]
    return sorted(result)


def fetch_image_b64(url: str) -> str:
    for attempt in range(8):
        resp = requests.get(url, timeout=30)
        if resp.status_code == 429:
            wait = min(2 ** attempt, 60)
            logger.warning(f"429 fetching image, waiting {wait}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
    raise RuntimeError(f"Image fetch failed after retries: {url}")


def vision_analyze_board(url: str, label: str) -> dict:
    """Call vision model to get board state as JSON dict. Retries on rate limit."""
    b64 = fetch_image_b64(url)
    prompt = (
        "This is a 3x3 electrical puzzle grid. Each cell has a cable connector.\n"
        "Connector types: I (2 opposite sides), L (2 adjacent sides), T (3 sides), X (4 sides).\n"
        "Grid: row 1 = top, col 1 = left. Cells addressed as RxC e.g. '2x3'.\n"
        "Use only: top, right, bottom, left for connection directions.\n"
        "Respond ONLY with JSON:\n"
        '{"1x1":{"connections":["top","right"]},"1x2":{...},...,"3x3":{...}}'
    )
    for attempt in range(6):
        try:
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]}],
                response_format={"type": "json_object"}
            )
            break
        except RateLimitError:
            wait = min(2 ** attempt * 3, 60)
            logger.warning(f"OpenAI 429 (vision), waiting {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError("Vision API rate limit — all retries exhausted")

    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    for cell in parsed:
        parsed[cell]["connections"] = sorted(parsed[cell]["connections"])
    logger.info(f"{label}: {json.dumps(parsed)}")
    return parsed


def post_rotate(cell: str) -> dict:
    """Single 90° CW rotation API call with retry on 429."""
    payload = {"apikey": API_KEY, "task": "electricity", "answer": {"rotate": cell}}
    for attempt in range(6):
        resp = requests.post(VERIFY_URL, json=payload, timeout=30)
        if resp.status_code == 429:
            wait = min(2 ** attempt, 30)
            logger.warning(f"429 on rotate {cell}, waiting {wait}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Rotate {cell} failed after retries")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_get_target_board(_args=None) -> str:
    global _target_state
    if not _target_state:
        _target_state = vision_analyze_board(TARGET_URL, "Target")
    return json.dumps(_target_state)


def tool_get_current_board(_args=None) -> str:
    """Fetch fresh vision analysis of current board. Updates internal state."""
    global _board_state
    _board_state = vision_analyze_board(BOARD_URL, "Current")
    return json.dumps(_board_state)


def tool_rotate_cell(args: dict) -> str:
    """
    Rotate a cell by 90/180/270 degrees clockwise or counterclockwise.
    - Sends the required number of API requests internally (with delays).
    - Updates internal board state using rotation math (no extra vision call).
    - Returns: api_response, updated_board (derived from math, not vision).
    - If ANY api_response contains 'FLG:' it is included in the result.
    """
    global _board_state
    cell = args["cell"]
    degrees = int(args.get("degrees", 90))
    direction = args.get("direction", "clockwise").lower()

    cw_map = {90: 1, 180: 2, 270: 3}
    cw_turns = cw_map.get(degrees, 1)
    if direction in ("counterclockwise", "ccw", "left"):
        cw_turns = (4 - cw_turns) % 4

    logger.info(f"Rotating {cell} {degrees}° {direction} → {cw_turns} CW API call(s)")

    last_response = {}
    flag = None

    for i in range(cw_turns):
        if i > 0:
            time.sleep(0.5)
        last_response = post_rotate(cell)
        logger.info(f"  turn {i+1}/{cw_turns} → {last_response}")
        if "FLG:" in str(last_response):
            flag = last_response
            break

    # Update internal board state via rotation math (no API cost)
    if cell in _board_state:
        old = _board_state[cell]["connections"]
        new = rotate_connections(old, cw_turns)
        _board_state[cell]["connections"] = new
        logger.info(f"  {cell}: {old} → {new}")
    else:
        logger.warning(f"Cell {cell} not in board state cache — run get_current_board first")

    result = {
        "rotated": cell,
        "degrees": degrees,
        "direction": direction,
        "api_response": last_response,
        "updated_board": _board_state,
    }
    if flag:
        result["FLAG"] = flag

    return json.dumps(result)


def tool_reset_board(_args=None) -> str:
    global _board_state
    logger.info("Resetting board")
    requests.get(f"{BOARD_URL}?reset=1", timeout=30)
    time.sleep(2)
    _board_state = {}
    return json.dumps({"status": "reset done — call get_current_board to refresh state"})


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_target_board",
            "description": (
                "Fetch and vision-analyze the TARGET (solution) board. "
                "Returns JSON with required connections per cell. Call this FIRST."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_board",
            "description": (
                "Fetch and vision-analyze the CURRENT board state. "
                "Use at start and when you suspect the internal state is stale. "
                "Returns JSON with connections per cell."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rotate_cell",
            "description": (
                "Rotate a single cell by 90, 180, or 270 degrees. "
                "Internally sends 1–3 API calls. "
                "Returns: api_response (check for 'FLG:'), updated_board (all 9 cells after rotation). "
                "The updated_board is computed from rotation math — always accurate unless vision was wrong."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cell": {
                        "type": "string",
                        "description": "Cell address RxC e.g. '1x1', '2x3'"
                    },
                    "degrees": {
                        "type": "integer",
                        "enum": [90, 180, 270],
                        "description": "Degrees to rotate"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["clockwise", "counterclockwise"],
                        "default": "clockwise"
                    }
                },
                "required": ["cell", "degrees"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reset_board",
            "description": "Reset board to initial state. Then call get_current_board to refresh.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]

TOOL_MAP = {
    "get_target_board": tool_get_target_board,
    "get_current_board": tool_get_current_board,
    "rotate_cell": tool_rotate_cell,
    "reset_board": tool_reset_board,
}

SYSTEM = """You solve 3x3 electrical cable puzzles via function calling.

Grid: rows 1-3 (top→bottom), cols 1-3 (left→right), cell = RxC.

Rotation math — clockwise 90°: top→right, right→bottom, bottom→left, left→top.

Workflow:
1. get_target_board() — memorise target connections for all 9 cells.
2. get_current_board() — see current state.
3. For each cell, compute CW rotations (0–3) needed to match target.
   Example: current ["left","top"], target ["right","bottom"] → 1 CW rotation.
4. rotate_cell(cell, degrees, direction) — execute rotations.
   After each call you get updated_board reflecting all 9 cells. Compare to target.
5. If any cell still differs, correct it with another rotate_cell call.
6. When api_response or FLAG contains "FLG:" — report it and stop.

Correction strategy: if updated_board diverges from target, call get_current_board()
to get a fresh vision snapshot, then recalculate and fix."""


def run_agent():
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Solve the puzzle. Start with get_target_board, then get_current_board, then rotate cells as needed."}
    ]

    for iteration in range(1, 31):
        logger.info(f"=== Iteration {iteration}/30 ===")

        response = client.chat.completions.create(
            model=AGENT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            content = msg.content or ""
            logger.info(f"Agent: {content}")
            print(f"\nAgent:\n{content}")
            if "FLG:" in content:
                return content
            break

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            result = TOOL_MAP[name](args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })

            if "FLG:" in str(result):
                logger.success(f"FLAG: {result}")
                print(f"\n=== SOLVED! {result} ===")
                return result

    logger.warning("Max iterations reached")
    return None


if __name__ == "__main__":
    result = run_agent()
    print(f"\nResult: {result}")
