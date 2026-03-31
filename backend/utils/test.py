import requests
import json

# Base URL for local Ollama API
url = "http://localhost:11434/api/chat"

MODEL = "qwen3:latest"


def chat(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the Ollama /api/chat endpoint and return the reply."""
    messages = []

    if system:
        messages.append({"role": "system", "content": system})

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,   # get the full reply in one response
    }

    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    return data["message"]["content"]


if __name__ == "__main__":
    reply = chat("Hello")
    print(reply)
