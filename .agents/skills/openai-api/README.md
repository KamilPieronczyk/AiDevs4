# OpenAI API Skill

> **Install:** `npx skills add diskd-ai/openai-api` | [skills.sh](https://skills.sh)

Integration skill for building AI-powered applications with OpenAI's APIs.

---

## Scope and Purpose

This skill provides guidance and patterns for working with OpenAI's API, covering:

* Chat completions with GPT models
* Reasoning models (o1, o3, o4)
* Vision/image inputs
* Tool use/function calling
* Structured outputs and JSON mode
* Image generation (DALL-E)
* Audio transcription (Whisper) and text-to-speech
* Embeddings
* Assistants API
* Fine-tuning

---

## When to Use This Skill

**Triggers:**
* Mentions of OpenAI, GPT-4, GPT-4o, GPT-5, o1, o3, o4, DALL-E, Whisper, or Sora
* Working with Python SDK (`openai`) or TypeScript SDK (`openai`)
* Any OpenAI API integration task

**Use cases:**
* Implementing chat completions with GPT models
* Building agents with tool use/function calling
* Processing images with vision models
* Generating images with DALL-E
* Transcribing audio with Whisper
* Creating embeddings for RAG or semantic search

---

## Quick Reference

### Installation

```bash
# Python
pip install openai

# TypeScript/JavaScript
npm install openai
```

### Environment

```bash
export OPENAI_API_KEY=<your-api-key>
```

### Basic Usage

**Python:**
```python
from openai import OpenAI

client = OpenAI()  # Uses OPENAI_API_KEY env var

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**TypeScript:**
```typescript
import OpenAI from "openai";

const client = new OpenAI();

const response = await client.chat.completions.create({
    model: "gpt-4o",
    messages: [{ role: "user", content: "Hello" }],
});
```

---

## Model Selection Guide

| Use Case | Model | Notes |
|----------|-------|-------|
| Latest flagship | `gpt-5.2` | Best quality |
| Fast and capable | `gpt-4o` | Vision support |
| Cost-effective | `gpt-4o-mini` | Simpler tasks |
| Complex reasoning | `o4-mini` | Latest reasoning model |
| Strong reasoning | `o3` | Math and code |
| Image generation | `dall-e-3` | High quality images |
| Audio transcription | `whisper-1` | Speech-to-text |
| Text-to-speech | `tts-1-hd` | High quality audio |
| Embeddings | `text-embedding-3-small` | Efficient embeddings |

---

## Skill Structure

```
openai-api/
  SKILL.md          # Full API reference and patterns
  README.md         # This file (overview)
  references/       # Supporting documentation
    chat-completions.md   # Advanced chat patterns
    images.md             # DALL-E image generation
    audio.md              # Whisper and TTS
    embeddings.md         # Text embeddings
    assistants.md         # Assistants API
    fine-tuning.md        # Model fine-tuning
```

---

## Key Patterns

### Streaming Responses

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Structured Outputs

```python
from pydantic import BaseModel

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

response = client.beta.chat.completions.parse(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Create a meeting for tomorrow"}],
    response_format=CalendarEvent
)
event = response.choices[0].message.parsed
```

### Vision (Image from URL)

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
        ]
    }]
)
```

### Image Generation

```python
response = client.images.generate(
    model="dall-e-3",
    prompt="A serene mountain landscape at sunset",
    size="1024x1024",
    quality="hd"
)
```

---

## Error Handling

```python
from openai import APIError, RateLimitError, APIConnectionError

try:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}]
    )
except RateLimitError:
    # Wait and retry with exponential backoff
    pass
except APIConnectionError:
    # Network issue
    pass
except APIError as e:
    # API error (check e.status_code)
    pass
```

---

## Resources

* **Full skill reference**: [SKILL.md](SKILL.md)
* **Chat completions**: [references/chat-completions.md](references/chat-completions.md)
* **Image generation**: [references/images.md](references/images.md)
* **Audio guide**: [references/audio.md](references/audio.md)
* **Embeddings**: [references/embeddings.md](references/embeddings.md)
* **Assistants API**: [references/assistants.md](references/assistants.md)
* **Fine-tuning**: [references/fine-tuning.md](references/fine-tuning.md)
* **Official docs**: https://platform.openai.com/docs
* **Python SDK**: https://github.com/openai/openai-python
* **TypeScript SDK**: https://github.com/openai/openai-node

---

## License

MIT
