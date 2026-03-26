import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

from shared.ai import get_client
from shared.verify import verify

SENSORS_DIR = Path("S03/S03E01/sensors")
CACHE_FILE = Path("S03/S03E01/llm_cache.json")

RANGES = {
    "temperature": {"temperature_K": (553, 873)},
    "pressure": {"pressure_bar": (60, 160)},
    "water": {"water_level_meters": (5.0, 15.0)},
    "voltage": {"voltage_supply_v": (229.0, 231.0)},
    "humidity": {"humidity_percent": (40.0, 80.0)},
}

ALL_FIELDS = ["temperature_K", "pressure_bar", "water_level_meters", "voltage_supply_v", "humidity_percent"]

SENSOR_FIELDS = {
    "temperature": ["temperature_K"],
    "pressure": ["pressure_bar"],
    "water": ["water_level_meters"],
    "voltage": ["voltage_supply_v"],
    "humidity": ["humidity_percent"],
}


def validate_sensor(data: dict) -> bool:
    """Returns True if sensor data is valid (no anomalies), False if anomalous."""
    active_types = [t.strip() for t in data["sensor_type"].split("/")]
    active_fields = set()
    for t in active_types:
        active_fields.update(SENSOR_FIELDS.get(t, []))

    for field in ALL_FIELDS:
        val = data.get(field, 0)
        if field in active_fields:
            # Must be non-zero and within range
            sensor_name = next(t for t in active_types if field in SENSOR_FIELDS.get(t, []))
            lo, hi = RANGES[sensor_name][field]
            if val == 0 or not (lo <= val <= hi):
                return False
        else:
            # Inactive sensors must be exactly 0
            if val != 0:
                return False
    return True


def load_llm_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def save_llm_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def classify_notes_batch(batch: list[tuple[str, str]], client) -> dict[str, int]:
    """Send batch of (file_id, note) to LLM. Returns {file_id: 1|0}."""
    lines = "\n".join(f"{fid}|{note}" for fid, note in batch)
    prompt = (
        "Classify each operator note as OK (1) or NOT OK (0).\n"
        "1 = operator says data/readings are fine/normal/stable\n"
        "0 = operator reports errors, anomalies, issues, failures, unexpected\n"
        "Format: one line per entry: ID|SCORE\n\n"
        f"{lines}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    result = {}
    for line in response.choices[0].message.content.strip().split("\n"):
        line = line.strip()
        if "|" in line:
            parts = line.split("|")
            fid = parts[0].strip()
            score_str = parts[-1].strip()
            try:
                result[fid] = int(score_str)
            except ValueError:
                pass
    return result


def main():
    logger.info("Loading all sensor files...")
    files = sorted(SENSORS_DIR.glob("*.json"))
    logger.info(f"Found {len(files)} files")

    # Step 1: Programmatic validation
    logger.info("Running programmatic sensor validation...")
    sensor_ok = {}   # file_id -> True (data ok) / False (data anomalous)
    notes_list = []  # [(file_id, note), ...]

    for f in files:
        fid = f.stem
        data = json.loads(f.read_text())
        sensor_ok[fid] = validate_sensor(data)
        notes_list.append((fid, data["operator_notes"]))

    bad_sensor = sum(1 for v in sensor_ok.values() if not v)
    logger.info(f"Programmatic: {bad_sensor} files with sensor anomalies")

    # Step 2: LLM classification of operator notes in batches of 100
    logger.info("Running LLM classification of operator notes...")
    cache = load_llm_cache()
    client = get_client()

    # Find uncached
    uncached = [(fid, note) for fid, note in notes_list if fid not in cache]
    logger.info(f"Uncached notes: {len(uncached)}, cached: {len(cache)}")

    BATCH_SIZE = 100
    for i in range(0, len(uncached), BATCH_SIZE):
        batch = uncached[i:i + BATCH_SIZE]
        logger.info(f"LLM batch {i // BATCH_SIZE + 1}/{(len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE}")
        results = classify_notes_batch(batch, client)
        # Validate we got all back
        for fid, _ in batch:
            if fid not in results:
                logger.warning(f"Missing LLM result for {fid}, defaulting to 1 (OK)")
                results[fid] = 1
        cache.update(results)
        save_llm_cache(cache)
        time.sleep(0.2)

    # Merge operator classification
    operator_ok = {fid: bool(cache.get(fid, 1)) for fid, _ in notes_list}
    bad_operator = sum(1 for v in operator_ok.values() if not v)
    logger.info(f"LLM: {bad_operator} files where operator reports issues")

    # Step 3: Find anomalies
    # Anomaly if:
    # - sensor data is bad (sensor_ok=False)
    # - operator says OK but data is bad (operator_ok=True AND sensor_ok=False)
    # - operator says bad but data is OK (operator_ok=False AND sensor_ok=True)
    anomalies = set()
    for fid in sensor_ok:
        s_ok = sensor_ok[fid]
        o_ok = operator_ok.get(fid, True)
        if not s_ok or (o_ok != s_ok):
            anomalies.add(fid)

    logger.info(f"Total anomalies: {len(anomalies)}")

    # Breakdown
    mismatch_op_ok_data_bad = sum(1 for fid in sensor_ok if not sensor_ok[fid] and operator_ok.get(fid, True))
    mismatch_op_bad_data_ok = sum(1 for fid in sensor_ok if sensor_ok[fid] and not operator_ok.get(fid, True))
    both_bad = sum(1 for fid in sensor_ok if not sensor_ok[fid] and not operator_ok.get(fid, True))
    logger.info(f"  Operator OK but data bad: {mismatch_op_ok_data_bad}")
    logger.info(f"  Operator bad but data OK: {mismatch_op_bad_data_ok}")
    logger.info(f"  Both bad: {both_bad}")

    answer = sorted(anomalies)
    logger.info(f"Submitting {len(answer)} anomalies...")
    result = verify(task="evaluation", answer={"recheck": answer})
    logger.info(f"Result: {result}")


if __name__ == "__main__":
    main()
