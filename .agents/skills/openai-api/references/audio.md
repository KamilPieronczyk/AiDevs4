# Audio Reference (Whisper & TTS)

## Table of Contents
- [Transcription (Whisper)](#transcription-whisper)
- [Translation](#translation)
- [Text-to-Speech](#text-to-speech)
- [Real-time Audio](#real-time-audio)

## Transcription (Whisper)

**Python:**
```python
# Basic transcription
with open("audio.mp3", "rb") as audio_file:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )
print(transcript.text)

# With options
transcript = client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    language="en",  # ISO-639-1 code
    prompt="Technical discussion about AI",  # Helps with context/spelling
    response_format="verbose_json",  # Get timestamps
    temperature=0  # Lower = more deterministic
)

# Access timestamps with verbose_json
for segment in transcript.segments:
    print(f"[{segment.start:.2f}s - {segment.end:.2f}s]: {segment.text}")
```

**TypeScript:**
```typescript
import fs from 'fs';

const transcript = await client.audio.transcriptions.create({
    model: 'whisper-1',
    file: fs.createReadStream('audio.mp3')
});
console.log(transcript.text);

// With timestamps
const verboseTranscript = await client.audio.transcriptions.create({
    model: 'whisper-1',
    file: fs.createReadStream('audio.mp3'),
    response_format: 'verbose_json'
});
```

### Response Formats

| Format | Output |
|--------|--------|
| `json` | `{"text": "..."}` |
| `text` | Plain text |
| `srt` | SubRip subtitle format |
| `vtt` | WebVTT subtitle format |
| `verbose_json` | JSON with timestamps and metadata |

### Supported Audio Formats
mp3, mp4, mpeg, mpga, m4a, wav, webm (max 25MB)

## Translation

Translate audio to English (any language to English):

**Python:**
```python
with open("german_audio.mp3", "rb") as audio_file:
    translation = client.audio.translations.create(
        model="whisper-1",
        file=audio_file
    )
print(translation.text)  # English text
```

**TypeScript:**
```typescript
const translation = await client.audio.translations.create({
    model: 'whisper-1',
    file: fs.createReadStream('german_audio.mp3')
});
```

## Text-to-Speech

**Python:**
```python
# Generate speech
response = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello, how can I help you today?"
)

# Save to file
response.stream_to_file("output.mp3")

# Or get bytes
audio_bytes = response.content

# Streaming for real-time playback
response = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello, how can I help you today?",
    response_format="pcm"  # Raw audio for streaming
)
for chunk in response.iter_bytes():
    # Stream to audio player
    pass
```

**TypeScript:**
```typescript
const response = await client.audio.speech.create({
    model: 'tts-1',
    voice: 'alloy',
    input: 'Hello, how can I help you today!'
});

// Save to file
const buffer = Buffer.from(await response.arrayBuffer());
fs.writeFileSync('output.mp3', buffer);

// Streaming
const streamResponse = await client.audio.speech.create({
    model: 'tts-1',
    voice: 'alloy',
    input: 'Hello!',
    response_format: 'pcm'
});
for await (const chunk of streamResponse.body) {
    // Stream to audio player
}
```

### TTS Models

| Model | Quality | Latency | Cost |
|-------|---------|---------|------|
| `tts-1` | Standard | Low | Lower |
| `tts-1-hd` | High definition | Higher | Higher |

### Voices

| Voice | Description |
|-------|-------------|
| `alloy` | Neutral, balanced |
| `echo` | Warm, conversational |
| `fable` | British, expressive |
| `onyx` | Deep, authoritative |
| `nova` | Friendly, upbeat |
| `shimmer` | Soft, gentle |

### Audio Formats

| Format | Description |
|--------|-------------|
| `mp3` | Default, widely compatible |
| `opus` | Low latency streaming |
| `aac` | Good for mobile |
| `flac` | Lossless compression |
| `wav` | Uncompressed |
| `pcm` | Raw audio, lowest latency |

## Real-time Audio

For real-time voice conversations, use the Realtime API (WebSocket):

**Python:**
```python
import asyncio
import websockets
import json
import base64

async def realtime_audio():
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    async with websockets.connect(url, extra_headers=headers) as ws:
        # Configure session
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": "alloy"
            }
        }))

        # Send audio input
        audio_data = base64.b64encode(audio_bytes).decode()
        await ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": audio_data
        }))

        # Commit and generate response
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await ws.send(json.dumps({"type": "response.create"}))

        # Receive responses
        async for message in ws:
            event = json.loads(message)
            if event["type"] == "response.audio.delta":
                audio_chunk = base64.b64decode(event["delta"])
                # Play audio chunk
```

**Key Realtime API events:**
- `session.update` - Configure session settings
- `input_audio_buffer.append` - Send audio data
- `input_audio_buffer.commit` - Signal end of input
- `response.create` - Request response generation
- `response.audio.delta` - Receive audio output chunks
- `response.text.delta` - Receive text transcription
