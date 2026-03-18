import os
import requests
import csv
import io
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

API_KEY = os.environ["AIDEVS_API_KEY"]
VERIFY_URL = "https://hub.ag3nts.org/verify"
CSV_URL = f"https://hub.ag3nts.org/data/{API_KEY}/categorize.csv"

# Prompt must be <=100 tokens total including item data
# Reactor parts must always be NEU even if they sound dangerous
PROMPT_TEMPLATE = "Classify as DNG (dangerous) or NEU (neutral). Reactor/nuclear parts are always NEU. Reply only DNG or NEU.\nID:{id} DESC:{description}"


def send_reset():
    r = requests.post(VERIFY_URL, json={"apikey": API_KEY, "task": "categorize", "answer": {"prompt": "reset"}})
    logger.info(f"RESET response: {r.json()}")


def fetch_items():
    r = requests.get(CSV_URL)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    return list(reader)


def classify_item(item_id, description, prompt_template):
    prompt = prompt_template.replace("{id}", item_id).replace("{description}", description)
    payload = {"apikey": API_KEY, "task": "categorize", "answer": {"prompt": prompt}}
    r = requests.post(VERIFY_URL, json=payload)
    result = r.json()
    logger.info(f"Item {item_id}: {result}")
    return result


def run_cycle(prompt_template):
    items = fetch_items()
    logger.info(f"Fetched {len(items)} items: {[i.get('id', i) for i in items]}")

    flag = None
    for item in items:
        item_id = item.get("code", item.get("id", item.get("ID", "")))
        description = item.get("description", item.get("Description", item.get("desc", "")))
        result = classify_item(item_id, description, prompt_template)

        msg = result.get("message", "")
        code = result.get("code", 0)
        if "{FLG:" in msg or "FLG:" in msg:
            flag = msg
            break
        if code < 0:
            # negative code = actual error
            logger.warning(f"Error on item {item_id}: {msg}")
            return None, result
        # code 1 = ACCEPTED, code 0 = pending, continue

    return flag, None


def main():
    prompt = PROMPT_TEMPLATE
    max_attempts = 10

    for attempt in range(1, max_attempts + 1):
        logger.info(f"=== Attempt {attempt} ===")
        logger.info(f"Using prompt: {prompt}")

        flag, error = run_cycle(prompt)

        if flag:
            logger.success(f"GOT FLAG: {flag}")
            print(f"\nFLAG: {flag}")
            return

        logger.warning(f"No flag. Error: {error}")
        logger.info("Sending reset...")
        send_reset()

        # Adjust prompt based on error feedback if needed
        # (keeping same prompt for now - it should work)

    logger.error("Max attempts reached without getting flag")


if __name__ == "__main__":
    main()
