import sys
sys.path.append("../..")

from shared.verify import verify
from shared.ai import chat

# TODO: rozwiąż zadanie i wywołaj verify
answer = chat("Twoje pytanie do modelu")
verify(task="nazwa-zadania", answer=answer)
