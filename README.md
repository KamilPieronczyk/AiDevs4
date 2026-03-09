# AiDevs4

Rozwiązania zadań z kursu AiDevs4. Python + OpenAI/OpenRouter.

## Struktura

```
AiDevs4/
├── .env                  # klucze API (nie commitować)
├── shared/               # wspólne narzędzia
│   └── verify.py         # wysyłanie odpowiedzi do hub.ag3nts.org
├── S01/                  # Moduł 1
│   ├── S01E01/
│   ├── S01E02/
│   └── ...
├── S02/                  # Moduł 2
└── ...
```

## Konfiguracja

```bash
cp .env.example .env
# uzupełnij klucze w .env

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uruchamianie lekcji

Zawsze z rootu repozytorium (ścieżki do plików i import `shared/` zakładają root jako CWD):

```bash
source .venv/bin/activate
python S01/S01E01/solution.py
```

## Styl kodu

- Krótki, zwięzły kod
- Max 1-2 linie komentarza na logikę
- Bez nadmiarowych abstrakcji
