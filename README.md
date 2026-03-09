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
pip install -r requirements.txt
```

## Uruchamianie lekcji

```bash
cd S01/S01E01
python solution.py
```

## Styl kodu

- Krótki, zwięzły kod
- Max 1-2 linie komentarza na logikę
- Bez nadmiarowych abstrakcji
