import sys
import csv
import json
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel

sys.path.append("../..")
load_dotenv(find_dotenv())

from shared.verify import verify

TAGS = ["IT", "transport", "edukacja", "medycyna", "praca z ludźmi", "praca z pojazdami", "praca fizyczna"]
TAG_LIST = ", ".join(TAGS)
CURRENT_YEAR = 2026


class PersonTags(BaseModel):
    name: str
    tags: list[str]


class BatchTags(BaseModel):
    people: list[PersonTags]


def load_csv():
    with open("S01/S01E01/people.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def filter_people(rows):
    result = []
    for r in rows:
        gender = r.get("gender", "").strip().upper()
        city = r.get("birthPlace", "").strip().lower()
        try:
            born = int(r.get("birthDate", "0")[:4])
        except (ValueError, TypeError):
            continue
        age = CURRENT_YEAR - born
        if gender == "M" and city == "grudziądz" and 20 <= age <= 40:
            result.append(r)
    return result


def tag_batch(client, batch):
    entries = "\n".join(
        f"{i+1}. name={p['name']} {p['surname']}, job={p.get('job','')}"
        for i, p in enumerate(batch)
    )
    prompt = (
        f"Przypisz tagi do każdej osoby na podstawie jej zawodu/stanowiska.\n"
        f"Dostępne tagi: {TAG_LIST}\n"
        f"Jedna osoba może mieć wiele tagów. Zwróć wyniki dla wszystkich {len(batch)} osób.\n\n"
        f"{entries}"
    )
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=BatchTags,
    )
    return response.choices[0].message.parsed.people


def main():
    client = OpenAI()
    rows = load_csv()
    candidates = filter_people(rows)
    print(f"Filtered: {len(candidates)} people")

    # Tag in batches of 10, fresh context each time
    tags_map = {}
    batch_size = 10
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i+batch_size]
        results = tag_batch(client, batch)
        for person_tags in results:
            tags_map[person_tags.name] = person_tags.tags
        print(f"Tagged batch {i//batch_size + 1}: {[r.name for r in results]}")

    # Filter only transport workers
    answer = []
    for p in candidates:
        full_name = f"{p['name']} {p['surname']}"
        tags = tags_map.get(full_name, [])
        if "transport" in tags:
            answer.append({
                "name": p["name"],
                "surname": p["surname"],
                "gender": p.get("gender", "").strip(),
                "born": int(p["birthDate"][:4]),
                "city": p.get("birthPlace", "").strip(),
                "tags": tags,
            })

    print(f"Transport workers: {len(answer)}")
    for a in answer:
        print(a)

    # Save suspects for S01E02
    with open("S01/S01E01/suspects.json", "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)
    print("Suspects saved to S01/S01E01/suspects.json")

    verify(task="people", answer=answer)


if __name__ == "__main__":
    main()
