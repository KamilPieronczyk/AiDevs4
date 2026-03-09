# Claude Instructions – AiDevs4

## Projekt

Rozwiązania zadań z kursu AiDevs4. Python + OpenAI SDK lub OpenRouter.

## Konwencje kodu

- Krótki, zwięzły kod – bez zbędnych abstrakcji
- Max 1-2 linie komentarza na blok logiki
- Bez docstringów i type annotations tam, gdzie nie są potrzebne
- Każda lekcja to samodzielny skrypt `solution.py` w swoim folderze

## Struktura plików

- `.env` w root – przechowuje klucze API (AIDEVS_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY)
- `shared/verify.py` – helper do wysyłania odpowiedzi
- `shared/ai.py` – helper do wywołań LLM
- Lekcje w `S0X/S0XE0Y/solution.py`

## Klucze API

Ładuj przez `python-dotenv` z rootu repozytorium:
```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
```

## Odpowiedź do API

Każda lekcja kończy się wywołaniem `verify()` z `shared/verify.py`:
```python
from shared.verify import verify
verify(task="nazwa-zadania", answer="odpowiedź")
```

## Zarządzanie promptami

Prompty trzymaj w plikach `.md` w katalogu lekcji z frontmatter YAML:

```markdown
---
model: gpt-4o-mini
---
Treść promptu.
```

Wczytanie zwraca `Prompt(model, content)`:
```python
from shared.prompts import load_prompt

p = load_prompt("prompt.md")
# p.model, p.content
```

## Zależności i uruchamianie

Używaj venv — nigdy systemowego Pythona:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Skrypty uruchamiaj zawsze z rootu repozytorium (import `shared/` i ścieżki do plików zakładają root jako CWD):
```bash
python S01/S01E01/solution.py
```

Główne paczki:
- `openai` – klient OpenAI/OpenRouter
- `python-dotenv` – ładowanie .env
- `requests` – HTTP calls
- `python-frontmatter` – parsowanie frontmatter w promptach
- `loguru` – logi (preferowane nad print)
