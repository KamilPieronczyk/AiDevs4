# Chat Completions Reference

## Table of Contents
- [Multi-turn Conversations](#multi-turn-conversations)
- [Parallel Tool Calls](#parallel-tool-calls)
- [Forcing Tool Use](#forcing-tool-use)
- [Streaming with Tools](#streaming-with-tools)
- [Token Counting](#token-counting)
- [Prompt Caching](#prompt-caching)
- [Reasoning Models (o1, o3)](#reasoning-models-o1-o3)

## Multi-turn Conversations

Maintain conversation history by appending messages:

**Python:**
```python
messages = [{"role": "system", "content": "You are a helpful assistant."}]

def chat(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    assistant_message = response.choices[0].message
    messages.append({"role": "assistant", "content": assistant_message.content})
    return assistant_message.content
```

**TypeScript:**
```typescript
const messages: OpenAI.ChatCompletionMessageParam[] = [
    { role: 'system', content: 'You are a helpful assistant.' }
];

async function chat(userInput: string): Promise<string> {
    messages.push({ role: 'user', content: userInput });
    const response = await client.chat.completions.create({
        model: 'gpt-4o',
        messages
    });
    const content = response.choices[0].message.content || '';
    messages.push({ role: 'assistant', content });
    return content;
}
```

## Parallel Tool Calls

GPT-4o can request multiple tool calls in one response:

**Python:**
```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    parallel_tool_calls=True  # default is True
)

if response.choices[0].message.tool_calls:
    # Handle multiple tool calls
    messages.append(response.choices[0].message)
    for tool_call in response.choices[0].message.tool_calls:
        result = execute_tool(tool_call.function.name, tool_call.function.arguments)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })
```

Disable parallel calls with `parallel_tool_calls=False` if tools have side effects that shouldn't run concurrently.

## Forcing Tool Use

**Python:**
```python
# Force use of a specific tool
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    tool_choice={"type": "function", "function": {"name": "get_weather"}}
)

# Force model to use any tool (not none)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    tool_choice="required"
)

# Let model decide (default)
tool_choice="auto"

# Prevent tool use
tool_choice="none"
```

## Streaming with Tools

**Python:**
```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    stream=True
)

tool_calls = []
for chunk in stream:
    delta = chunk.choices[0].delta

    if delta.content:
        print(delta.content, end="")

    if delta.tool_calls:
        for tc in delta.tool_calls:
            if tc.index >= len(tool_calls):
                tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
            if tc.id:
                tool_calls[tc.index]["id"] = tc.id
            if tc.function.name:
                tool_calls[tc.index]["function"]["name"] = tc.function.name
            if tc.function.arguments:
                tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
```

**TypeScript (using helper):**
```typescript
import { ChatCompletionStreamingRunner } from 'openai/lib/ChatCompletionStreamingRunner';

const runner = client.beta.chat.completions.runTools({
    model: 'gpt-4o',
    messages,
    tools: [{
        type: 'function',
        function: {
            name: 'get_weather',
            description: 'Get weather',
            parameters: { type: 'object', properties: { location: { type: 'string' } } },
            function: async (args: { location: string }) => {
                return JSON.stringify({ temp: 22, condition: 'sunny' });
            },
            parse: JSON.parse
        }
    }]
});

runner.on('message', (msg) => console.log(msg));
const result = await runner.finalChatCompletion();
```

## Token Counting

Count tokens before sending request:

**Python:**
```python
import tiktoken

def count_tokens(messages: list, model: str = "gpt-4o") -> int:
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += 4  # message overhead
        for key, value in message.items():
            num_tokens += len(encoding.encode(str(value)))
    num_tokens += 2  # reply priming
    return num_tokens
```

**Response token usage:**
```python
response = client.chat.completions.create(...)
print(f"Prompt: {response.usage.prompt_tokens}")
print(f"Completion: {response.usage.completion_tokens}")
print(f"Total: {response.usage.total_tokens}")
```

## Prompt Caching

OpenAI automatically caches prompts >1024 tokens. Check cache usage:

```python
response = client.chat.completions.create(...)
if response.usage.prompt_tokens_details:
    cached = response.usage.prompt_tokens_details.cached_tokens
    print(f"Cached tokens: {cached}")
```

Tips for maximizing cache hits:
- Keep static content (system prompts, examples) at the start of messages
- Ensure prompts exceed 1024 tokens for caching to apply
- Cache is shared across requests within same organization

## Reasoning Models (o1, o3)

o1 and o3 models have different behavior:

**Python:**
```python
# o1/o3 don't support system messages - use developer message instead
response = client.chat.completions.create(
    model="o1",
    messages=[
        {"role": "developer", "content": "You are a math tutor."},
        {"role": "user", "content": "Solve x^2 + 5x + 6 = 0"}
    ]
)

# Access reasoning tokens
if response.usage.completion_tokens_details:
    reasoning = response.usage.completion_tokens_details.reasoning_tokens
    print(f"Reasoning tokens: {reasoning}")
```

**Key differences for o1/o3:**
- No `system` role - use `developer` role instead
- No `temperature` parameter (always uses default)
- No `max_tokens` - use `max_completion_tokens`
- No streaming support
- No tool use (as of early 2025)
- Higher latency due to internal reasoning

**TypeScript:**
```typescript
const response = await client.chat.completions.create({
    model: 'o1',
    messages: [
        { role: 'developer', content: 'You are a math tutor.' },
        { role: 'user', content: 'Solve x^2 + 5x + 6 = 0' }
    ],
    max_completion_tokens: 4096
});
```
