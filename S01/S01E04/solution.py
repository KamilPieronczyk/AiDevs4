import os
import json
import base64
import time
import requests
from pathlib import Path
from openai import OpenAI, RateLimitError
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv())

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
AIDEVS_API_KEY = os.environ["AIDEVS_API_KEY"]
BASE_URL = "https://hub.ag3nts.org/dane/doc/"
WORK_DIR = Path("S01/S01E04/docs")
WORK_DIR.mkdir(exist_ok=True)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def fetch_url(filename: str) -> str:
    """Download file from BASE_URL. Saves images locally, returns text content."""
    url = BASE_URL + filename if not filename.startswith("http") else filename
    logger.info(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    ext = Path(filename).suffix.lower()
    local_path = WORK_DIR / Path(filename).name

    if ext in IMAGE_EXTS:
        local_path.write_bytes(resp.content)
        logger.info(f"Saved image: {local_path}")
        return f"Image saved to {local_path}. Use describe_image tool to analyze it."
    else:
        text = resp.text
        local_path.write_text(text, encoding="utf-8")
        logger.info(f"Saved text ({len(text)} chars): {local_path}")
        return text


def read_file(filename: str) -> str:
    """Read a locally saved file."""
    path = WORK_DIR / filename
    if not path.exists():
        return f"File not found: {path}"
    return path.read_text(encoding="utf-8")


def describe_image(filename: str) -> str:
    """Use GPT-4o vision to extract all text and data from an image."""
    path = WORK_DIR / filename
    if not path.exists():
        return f"Image not found: {path}"

    ext = path.suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")

    b64 = base64.b64encode(path.read_bytes()).decode()
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Proszę wypisz WSZYSTKIE dane z tego dokumentu/obrazu dosłownie, łącznie z tabelami, kodami tras, cenami, skrótami i wzorami formularzy. Zachowaj oryginalne formatowanie."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    ]
                }],
                max_tokens=4000,
            )
            break
        except RateLimitError as e:
            wait = 10 * (attempt + 1)
            logger.warning(f"Rate limit, waiting {wait}s... ({e})")
            time.sleep(wait)
    result = response.choices[0].message.content
    logger.info(f"Image described: {filename} -> {len(result)} chars")
    return result


def submit_declaration(declaration: str) -> str:
    """Submit the filled declaration to the verify endpoint."""
    payload = {
        "apikey": AIDEVS_API_KEY,
        "task": "sendit",
        "answer": {"declaration": declaration},
    }
    resp = requests.post("https://hub.ag3nts.org/verify", json=payload, timeout=15)
    result = resp.json()
    logger.info(f"Verify response: {result}")
    return json.dumps(result)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Pobiera plik z dokumentacji SPK (BASE_URL + filename). Dla obrazów zapisuje lokalnie i zwraca informację o ścieżce. Dla plików tekstowych zwraca zawartość.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku, np. 'index.md', 'regulamin.md', 'trasy.png'"}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Czyta lokalnie zapisany plik z katalogu docs/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku lokalnego"}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_image",
            "description": "Używa GPT-4o vision do wypisania WSZYSTKICH danych z pliku graficznego (tabele, kody, wzory).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa lokalnego pliku graficznego"}
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_declaration",
            "description": "Wysyła wypełnioną deklarację do weryfikacji. Używaj tylko gdy masz kompletną, poprawnie sformatowaną deklarację.",
            "parameters": {
                "type": "object",
                "properties": {
                    "declaration": {"type": "string", "description": "Pełny tekst wypełnionej deklaracji, sformatowany dokładnie jak wzór z dokumentacji"}
                },
                "required": ["declaration"],
            },
        },
    },
]

SYSTEM = """Jesteś agentem wypełniającym deklarację transportową w Systemie Przesyłek Konduktorskich (SPK).

Twoje zadanie:
1. Pobierz i przeczytaj CAŁĄ dokumentację SPK zaczynając od index.md
2. Pobierz WSZYSTKIE pliki do których odsyła dokumentacja (w tym graficzne!)
3. Dla plików graficznych użyj describe_image aby wyciągnąć dane
4. Znajdź wzór deklaracji i wypełnij go danymi:
   - Nadawca (identyfikator): 450202122
   - Punkt nadawczy: Gdańsk
   - Punkt docelowy: Żarnowiec
   - Waga: 2800 kg
   - Budżet: 0 PP (przesyłka MUSI być darmowa lub finansowana przez System)
   - Zawartość: kasety z paliwem do reaktora
   - Uwagi specjalne: BRAK (nie dodawaj żadnych uwag)
5. Ustal prawidłowy kod trasy Gdańsk-Żarnowiec z listy tras
6. Dobierz kategorię przesyłki tak, aby koszt wynosił 0 PP (szukaj kategorii finansowanych przez System)
7. Zachowaj DOKŁADNE formatowanie wzoru (separatory, kolejność pól, etc.)
8. Wyślij gotową deklarację przez submit_declaration

WAŻNE: Czytaj uważnie każdy plik. Odpowiedzi mogą być w różnych plikach. Nie pomijaj plików graficznych."""


def run_agent():
    messages = [{"role": "system", "content": SYSTEM}]
    messages.append({"role": "user", "content": "Zacznij od pobrania index.md i przeczytania całej dokumentacji, potem wypełnij i wyślij deklarację."})

    for i in range(30):
        for attempt in range(5):
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                break
            except RateLimitError as e:
                wait = 10 * (attempt + 1)
                logger.warning(f"Rate limit on main call, waiting {wait}s...")
                time.sleep(wait)
        msg = resp.choices[0].message
        finish = resp.choices[0].finish_reason
        logger.info(f"[iter {i}] finish={finish}")

        messages.append(msg.model_dump(exclude_unset=True))

        if finish == "stop":
            logger.info(f"Agent done: {msg.content}")
            return msg.content

        if msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                logger.info(f"Tool: {name}({args})")

                if name == "fetch_url":
                    result = fetch_url(args["filename"])
                elif name == "read_file":
                    result = read_file(args["filename"])
                elif name == "describe_image":
                    result = describe_image(args["filename"])
                elif name == "submit_declaration":
                    result = submit_declaration(args["declaration"])
                else:
                    result = json.dumps({"error": f"unknown tool: {name}"})

                logger.info(f"Result preview: {result[:200]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    return "Agent exceeded max iterations"


if __name__ == "__main__":
    result = run_agent()
    print(result)
