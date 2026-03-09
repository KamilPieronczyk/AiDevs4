from pathlib import Path
from dataclasses import dataclass
import frontmatter


@dataclass
class Prompt:
    model: str
    content: str


def load_prompt(path: str) -> Prompt:
    post = frontmatter.load(path)
    return Prompt(model=post["model"], content=post.content)
