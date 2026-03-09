import sys
sys.path.append("../..")

from shared.prompts import run_prompt
from shared.verify import verify

answer = run_prompt("prompt.md", variables={"question": "Ile to 2+2?"})
verify(task="nazwa-zadania", answer=answer)
