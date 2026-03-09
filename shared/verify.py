import os
import requests
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

VERIFY_URL = "https://hub.ag3nts.org/verify"


def verify(task: str, answer) -> dict:
    payload = {
        "apikey": os.environ["AIDEVS_API_KEY"],
        "task": task,
        "answer": answer,
    }
    response = requests.post(VERIFY_URL, json=payload)
    result = response.json()
    print(result)
    return result
