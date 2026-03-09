import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def get_client(use_openrouter=False) -> OpenAI:
    if use_openrouter:
        return OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def chat(prompt: str, system: str = "", model: str = "gpt-4o-mini", **kwargs) -> str:
    client = get_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(model=model, messages=messages, **kwargs)
    return response.choices[0].message.content
