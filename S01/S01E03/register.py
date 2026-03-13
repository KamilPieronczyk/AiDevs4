import sys
from shared.verify import verify

if len(sys.argv) < 2:
    print("Usage: python S01/S01E03/register.py <ngrok-url>")
    sys.exit(1)

ngrok_url = sys.argv[1].rstrip("/") + "/"
session_id = "s01e03abc"

result = verify(
    task="proxy",
    answer={"url": ngrok_url, "sessionID": session_id},
)
print(result)
