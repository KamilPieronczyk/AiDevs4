import os
import sys
import json
import math
import time
import requests
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from loguru import logger

sys.path.append("../..")
load_dotenv(find_dotenv())

from shared.verify import verify

API_KEY = os.environ["AIDEVS_API_KEY"]
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "gpt-4o-mini"
PLANTS_CACHE = "S01/S01E02/cache_plants.json"

memory = {"power_plants": [], "suspects": []}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode(city):
    time.sleep(1)  # Nominatim: 1 req/sec
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{city}, Poland", "format": "json", "limit": 1},
        headers={"User-Agent": "AiDevs4-Agent/1.0"},
        timeout=5,
    ).json()
    return (float(resp[0]["lat"]), float(resp[0]["lon"])) if resp else (None, None)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_fetch_power_plants():
    if os.path.exists(PLANTS_CACHE):
        with open(PLANTS_CACHE, encoding="utf-8") as f:
            plants = json.load(f)
        memory["power_plants"] = plants
        logger.info(f"[fetch_power_plants] loaded from cache → {len(plants)} plants")
        return {"count": len(plants), "plants": plants}

    raw = requests.get(f"https://hub.ag3nts.org/data/{API_KEY}/findhim_locations.json").json()
    plants = []
    for city, info in raw["power_plants"].items():
        lat, lon = geocode(city)
        plants.append({"city": city, "code": info["code"], "lat": lat, "lon": lon})
        logger.debug(f"  geocoded {city}: ({lat}, {lon})")

    with open(PLANTS_CACHE, "w", encoding="utf-8") as f:
        json.dump(plants, f, ensure_ascii=False, indent=2)

    memory["power_plants"] = plants
    logger.info(f"[fetch_power_plants] fetched & cached → {len(plants)} plants:\n{json.dumps(plants, indent=2)}")
    return {"count": len(plants), "plants": plants}


def tool_find_suspects_near_plants(top_n: int = 3):
    results = []
    for s in memory["suspects"]:
        locations = requests.post(
            "https://hub.ag3nts.org/api/location",
            json={"apikey": API_KEY, "name": s["name"], "surname": s["surname"]},
        ).json()

        min_dist, best_plant, best_loc = float("inf"), None, None
        for loc in locations:
            for plant in memory["power_plants"]:
                d = haversine(loc["latitude"], loc["longitude"], plant["lat"], plant["lon"])
                if d < min_dist:
                    min_dist, best_plant, best_loc = d, plant, loc

        results.append({
            "name": s["name"],
            "surname": s["surname"],
            "birthYear": s["born"],
            "min_distance_km": round(min_dist, 2) if min_dist != float("inf") else None,
            "plant_code": best_plant["code"] if best_plant else None,
            "plant_city": best_plant["city"] if best_plant else None,
            "nearest_location": best_loc,
        })

    results.sort(key=lambda x: x["min_distance_km"] or float("inf"))
    top = results[:top_n]
    logger.info(f"[find_suspects_near_plants] top_n={top_n} →\n{json.dumps(top, indent=2)}")
    return top


def tool_prepare_and_submit_report(name, surname, birth_year, plant_code):
    access_resp = requests.post(
        "https://hub.ag3nts.org/api/accesslevel",
        json={"apikey": API_KEY, "name": name, "surname": surname, "birthYear": birth_year},
    ).json()
    access_level = access_resp["accessLevel"]
    logger.info(f"[prepare_and_submit_report] accessLevel for {name} {surname}: {access_level}")

    answer = {"name": name, "surname": surname, "accessLevel": access_level, "powerPlant": plant_code}
    result = verify(task="findhim", answer=answer)
    logger.info(f"[prepare_and_submit_report] verify result: {result}")
    return {"accessLevel": access_level, "verifyResult": result}


# ---------------------------------------------------------------------------
# Tool schema & dispatch
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_power_plants",
            "description": "Download the list of nuclear power plants with GPS coordinates and codes. Call this first.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_suspects_near_plants",
            "description": (
                "Fetch location history for all suspects, compute minimum Haversine distance to any plant, "
                "return top N closest sorted ascending. Start with top_n=3; increase if top distances are within 5 km."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "How many suspects to return (default 3)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_and_submit_report",
            "description": "Fetch access level for the suspect and submit the final answer to /verify. Returns the flag.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birth_year": {"type": "integer"},
                    "plant_code": {"type": "string", "description": "e.g. PWR1234PL"},
                },
                "required": ["name", "surname", "birth_year", "plant_code"],
            },
        },
    },
]

TOOL_DISPATCH = {
    "fetch_power_plants": lambda a: tool_fetch_power_plants(),
    "find_suspects_near_plants": lambda a: tool_find_suspects_near_plants(a.get("top_n", 3)),
    "prepare_and_submit_report": lambda a: tool_prepare_and_submit_report(
        a["name"], a["surname"], a["birth_year"], a["plant_code"]
    ),
}

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

SYSTEM = """You are an investigative agent finding which suspect was seen near a nuclear power plant.

1. Call fetch_power_plants.
2. Call find_suspects_near_plants(top_n=3).
3. Pick the suspect with clearly the smallest min_distance_km.
   If the gap between #1 and #2 is less than 5 km, call find_suspects_near_plants(top_n=6) to see more.
4. Call prepare_and_submit_report with that suspect's data.
5. Report the flag."""


def run_agent():
    with open("S01/S01E01/suspects.json", encoding="utf-8") as f:
        memory["suspects"] = json.load(f)
    logger.info(f"Suspects loaded: {[s['name'] + ' ' + s['surname'] for s in memory['suspects']]}")

    messages = [{"role": "system", "content": SYSTEM}]

    for iteration in range(15):
        logger.info(f"── iteration {iteration + 1} ──────────────────────────")
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        msg = response.choices[0].message
        messages.append(msg)

        # Log agent message
        if msg.content:
            logger.info(f"[agent] {msg.content}")
        if msg.tool_calls:
            for tc in msg.tool_calls:
                logger.info(f"[agent] → tool call: {tc.function.name}({tc.function.arguments})")

        if not msg.tool_calls:
            break

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = TOOL_DISPATCH[tc.function.name](args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
    else:
        logger.warning("Max iterations reached.")


if __name__ == "__main__":
    run_agent()
