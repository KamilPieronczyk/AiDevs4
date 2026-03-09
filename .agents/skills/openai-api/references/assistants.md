# Assistants API Reference

## Table of Contents
- [Overview](#overview)
- [Creating Assistants](#creating-assistants)
- [Threads and Messages](#threads-and-messages)
- [Running Assistants](#running-assistants)
- [Tools](#tools)
- [File Search](#file-search)
- [Code Interpreter](#code-interpreter)
- [Streaming](#streaming)

## Overview

The Assistants API manages stateful conversations with:
- **Assistants** - Configured AI with instructions and tools
- **Threads** - Conversation sessions
- **Messages** - User and assistant messages in a thread
- **Runs** - Execution of an assistant on a thread

## Creating Assistants

**Python:**
```python
assistant = client.beta.assistants.create(
    name="Math Tutor",
    instructions="You are a helpful math tutor. Explain concepts clearly.",
    model="gpt-4o",
    tools=[{"type": "code_interpreter"}]
)
print(f"Assistant ID: {assistant.id}")

# Update assistant
assistant = client.beta.assistants.update(
    assistant.id,
    instructions="Updated instructions..."
)

# List assistants
assistants = client.beta.assistants.list(limit=20)

# Delete assistant
client.beta.assistants.delete(assistant.id)
```

**TypeScript:**
```typescript
const assistant = await client.beta.assistants.create({
    name: 'Math Tutor',
    instructions: 'You are a helpful math tutor.',
    model: 'gpt-4o',
    tools: [{ type: 'code_interpreter' }]
});
```

## Threads and Messages

**Python:**
```python
# Create thread
thread = client.beta.threads.create()

# Create thread with initial messages
thread = client.beta.threads.create(
    messages=[
        {"role": "user", "content": "Help me solve x^2 = 4"}
    ]
)

# Add message to thread
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content="What is the derivative of x^3?"
)

# Add message with image
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=[
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
    ]
)

# List messages
messages = client.beta.threads.messages.list(thread_id=thread.id)
for msg in messages.data:
    print(f"{msg.role}: {msg.content[0].text.value}")
```

**TypeScript:**
```typescript
const thread = await client.beta.threads.create();

const message = await client.beta.threads.messages.create(thread.id, {
    role: 'user',
    content: 'What is the derivative of x^3?'
});

const messages = await client.beta.threads.messages.list(thread.id);
```

## Running Assistants

**Python:**
```python
# Create and poll run (blocking)
run = client.beta.threads.runs.create_and_poll(
    thread_id=thread.id,
    assistant_id=assistant.id
)

if run.status == "completed":
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    print(messages.data[0].content[0].text.value)
elif run.status == "requires_action":
    # Handle tool calls
    pass
else:
    print(f"Run status: {run.status}")

# Manual polling
run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id
)

while run.status in ["queued", "in_progress"]:
    run = client.beta.threads.runs.retrieve(
        thread_id=thread.id,
        run_id=run.id
    )
    time.sleep(1)
```

**TypeScript:**
```typescript
const run = await client.beta.threads.runs.createAndPoll(thread.id, {
    assistant_id: assistant.id
});

if (run.status === 'completed') {
    const messages = await client.beta.threads.messages.list(thread.id);
    console.log(messages.data[0].content[0]);
}
```

### Run Statuses

| Status | Description |
|--------|-------------|
| `queued` | Waiting to start |
| `in_progress` | Currently running |
| `requires_action` | Waiting for tool outputs |
| `completed` | Successfully finished |
| `failed` | Error occurred |
| `cancelled` | Cancelled by user |
| `expired` | Timed out |

## Tools

### Custom Functions

**Python:**
```python
assistant = client.beta.assistants.create(
    name="Weather Assistant",
    model="gpt-4o",
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    }]
)

# Handle tool calls
run = client.beta.threads.runs.create_and_poll(thread_id, assistant_id)

if run.status == "requires_action":
    tool_outputs = []
    for tool_call in run.required_action.submit_tool_outputs.tool_calls:
        if tool_call.function.name == "get_weather":
            args = json.loads(tool_call.function.arguments)
            result = get_weather(args["location"])  # Your function
            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": json.dumps(result)
            })

    run = client.beta.threads.runs.submit_tool_outputs_and_poll(
        thread_id=thread.id,
        run_id=run.id,
        tool_outputs=tool_outputs
    )
```

## File Search

Search through uploaded documents:

**Python:**
```python
# Create vector store
vector_store = client.beta.vector_stores.create(name="Knowledge Base")

# Upload files
file = client.files.create(file=open("document.pdf", "rb"), purpose="assistants")
client.beta.vector_stores.files.create(vector_store_id=vector_store.id, file_id=file.id)

# Wait for processing
while True:
    vs = client.beta.vector_stores.retrieve(vector_store.id)
    if vs.file_counts.completed == vs.file_counts.total:
        break
    time.sleep(1)

# Attach to assistant
assistant = client.beta.assistants.create(
    name="Document Q&A",
    model="gpt-4o",
    tools=[{"type": "file_search"}],
    tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
)
```

**TypeScript:**
```typescript
const vectorStore = await client.beta.vectorStores.create({
    name: 'Knowledge Base'
});

const file = await client.files.create({
    file: fs.createReadStream('document.pdf'),
    purpose: 'assistants'
});

await client.beta.vectorStores.files.create(vectorStore.id, {
    file_id: file.id
});
```

## Code Interpreter

Execute Python code and work with files:

**Python:**
```python
assistant = client.beta.assistants.create(
    name="Data Analyst",
    model="gpt-4o",
    tools=[{"type": "code_interpreter"}]
)

# Upload file for analysis
file = client.files.create(file=open("data.csv", "rb"), purpose="assistants")

# Create message with file
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content="Analyze this CSV and create a chart",
    attachments=[{"file_id": file.id, "tools": [{"type": "code_interpreter"}]}]
)

run = client.beta.threads.runs.create_and_poll(thread_id, assistant_id)

# Get generated files
messages = client.beta.threads.messages.list(thread_id)
for msg in messages.data:
    for content in msg.content:
        if content.type == "image_file":
            file_id = content.image_file.file_id
            image_data = client.files.content(file_id)
            with open("chart.png", "wb") as f:
                f.write(image_data.read())
```

## Streaming

Stream assistant responses:

**Python:**
```python
from openai import AssistantEventHandler

class EventHandler(AssistantEventHandler):
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)

    def on_tool_call_created(self, tool_call):
        print(f"\nUsing tool: {tool_call.type}")

    def on_run_step_done(self, run_step):
        print(f"\nStep completed: {run_step.type}")

with client.beta.threads.runs.stream(
    thread_id=thread.id,
    assistant_id=assistant.id,
    event_handler=EventHandler()
) as stream:
    stream.until_done()
```

**TypeScript:**
```typescript
const stream = client.beta.threads.runs.stream(thread.id, {
    assistant_id: assistant.id
});

for await (const event of stream) {
    if (event.event === 'thread.message.delta') {
        const delta = event.data.delta.content?.[0];
        if (delta?.type === 'text') {
            process.stdout.write(delta.text?.value || '');
        }
    }
}
```

## Best Practices

1. **Reuse assistants** - Create once, use across threads
2. **Delete old threads** - Threads persist; clean up when done
3. **Handle all statuses** - Especially `requires_action` and `failed`
4. **Use streaming** - Better UX for long responses
5. **Manage file lifecycle** - Delete files when no longer needed
