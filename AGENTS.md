# Agent Instructions – AiDevs4

## Project

AiDevs4 course solutions. Python + OpenAI SDK or OpenRouter.

## Code Style

- Short, concise code – no unnecessary abstractions
- Max 1-2 comment lines per logic block
- No docstrings or type annotations unless required
- Each lesson is a standalone `solution.py` in its folder

## File Structure

- `.env` at root – API keys (AIDEVS_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY)
- `shared/verify.py` – helper for submitting answers to hub.ag3nts.org
- `shared/ai.py` – helper for LLM calls
- Lessons at `S0X/S0XE0Y/solution.py`

## API Keys

Load via `python-dotenv` using `find_dotenv()` to locate root `.env` from any subdirectory:
```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
```

## Submitting Answers

Every lesson ends with a call to `verify()`:
```python
from shared.verify import verify
verify(task="task-name", answer="answer")
```

Endpoint: `POST https://hub.ag3nts.org/verify`
Payload: `{"apikey": AIDEVS_API_KEY, "task": task, "answer": answer}`

## Prompt Management

Store prompts as `.md` files in the lesson directory using YAML frontmatter:

```markdown
---
model: gpt-4o-mini
system: You are a helpful assistant.
---
Prompt body with optional {{variable}} placeholders.
```

Frontmatter fields:
- `model` – model version (required)
- `system` – system prompt (optional)

Usage in `solution.py`:
```python
from shared.prompts import run_prompt, load_prompt

# run and get response directly
answer = run_prompt("prompt.md", variables={"variable": "value"})

# just load (post.content, post["model"], post["system"])
post = load_prompt("prompt.md")
```

## Dependencies

See `requirements.txt`. Key packages:
- `openai` – OpenAI/OpenRouter client
- `python-dotenv` – .env loading
- `requests` – HTTP calls
- `python-frontmatter` – frontmatter parsing for prompt files
