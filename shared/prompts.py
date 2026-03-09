import os
from pathlib import Path
import frontmatter
from shared.ai import get_client

DEFAULT_MODEL = "gpt-4o-mini"


def load_prompt(path: str) -> frontmatter.Post:
    """Wczytuje plik .md z frontmatter. path względem katalogu wywołującego."""
    caller_dir = Path(os.getcwd())
    full_path = caller_dir / path
    return frontmatter.load(str(full_path))


def run_prompt(path: str, variables: dict = None, use_openrouter=False) -> str:
    """Wczytuje prompt z .md, podmienia zmienne {{var}}, wywołuje model z frontmatter."""
    post = load_prompt(path)

    model = post.get("model", DEFAULT_MODEL)
    system = post.get("system", "")
    content = post.content

    # podmiana zmiennych {{nazwa}} w treści i systemie
    if variables:
        for key, val in variables.items():
            content = content.replace(f"{{{{{key}}}}}", str(val))
            system = system.replace(f"{{{{{key}}}}}", str(val))

    client = get_client(use_openrouter=use_openrouter)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})

    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content
