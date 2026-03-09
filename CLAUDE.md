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

## Zależności

Instaluj przez `pip install -r requirements.txt`. Główne paczki:
- `openai` – klient OpenAI/OpenRouter
- `python-dotenv` – ładowanie .env
- `requests` – HTTP calls
