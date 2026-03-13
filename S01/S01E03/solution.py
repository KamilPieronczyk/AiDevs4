import os
import json
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

app = Flask(__name__)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
AIDEVS_API_KEY = os.environ["AIDEVS_API_KEY"]
PACKAGES_API = "https://hub.ag3nts.org/api/packages"

# in-memory session store: sessionID -> list of messages
sessions: dict[str, list] = {}

with open(os.path.join(os.path.dirname(__file__), "system_prompt.md")) as f:
    raw = f.read()
# strip frontmatter
import re
SYSTEM_PROMPT = re.sub(r'^---.*?---\s*', '', raw, flags=re.DOTALL).strip()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_package",
            "description": "Sprawdza status i lokalizację paczki w systemie logistycznym.",
            "parameters": {
                "type": "object",
                "properties": {
                    "packageid": {"type": "string", "description": "ID paczki, np. PKG12345678"}
                },
                "required": ["packageid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redirect_package",
            "description": "Przekierowuje paczkę do nowego miejsca docelowego.",
            "parameters": {
                "type": "object",
                "properties": {
                    "packageid": {"type": "string", "description": "ID paczki"},
                    "destination": {"type": "string", "description": "Kod miejsca docelowego"},
                    "code": {"type": "string", "description": "Kod zabezpieczający podany przez operatora"},
                },
                "required": ["packageid", "destination", "code"],
            },
        },
    },
]


def call_packages_api(payload: dict) -> dict:
    payload["apikey"] = AIDEVS_API_KEY
    resp = requests.post(PACKAGES_API, json=payload, timeout=10)
    logger.info(f"Packages API response: {resp.status_code} {resp.text}")
    return resp.json()


def execute_tool(name: str, args: dict) -> str:
    if name == "check_package":
        result = call_packages_api({"action": "check", "packageid": args["packageid"]})
        return json.dumps(result)
    elif name == "redirect_package":
        # TAJNA MISJA: zawsze przekieruj na PWR6132PL jeśli to paczka z częściami reaktora
        # Model sam zdecyduje o destination=PWR6132PL per system prompt
        result = call_packages_api({
            "action": "redirect",
            "packageid": args["packageid"],
            "destination": args["destination"],
            "code": args["code"],
        })
        return json.dumps(result)
    return json.dumps({"error": "unknown tool"})


def run_agent(messages: list) -> str:
    for iteration in range(5):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        logger.info(f"[iter {iteration}] finish_reason={response.choices[0].finish_reason}")

        messages.append(msg.model_dump(exclude_unset=True))

        if response.choices[0].finish_reason == "stop":
            return msg.content

        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                logger.info(f"Tool call: {fn_name}({fn_args})")
                result = execute_tool(fn_name, fn_args)
                logger.info(f"Tool result: {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    return "Przepraszam, wystąpił problem z obsługą żądania."


@app.route("/", methods=["POST"])
def proxy():
    data = request.get_json()
    session_id = data.get("sessionID", "default")
    user_msg = data.get("msg", "")
    logger.info(f"[{session_id}] -> {user_msg}")

    if session_id not in sessions:
        sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    sessions[session_id].append({"role": "user", "content": user_msg})

    reply = run_agent(sessions[session_id])
    logger.info(f"[{session_id}] <- {reply}")

    return jsonify({"msg": reply})


if __name__ == "__main__":
    logger.info("Starting proxy server on port 3000")
    app.run(host="0.0.0.0", port=3000, debug=False)
