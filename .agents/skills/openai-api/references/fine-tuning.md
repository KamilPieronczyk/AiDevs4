# Fine-Tuning Reference

## Table of Contents
- [Overview](#overview)
- [Preparing Training Data](#preparing-training-data)
- [Creating Fine-Tuning Jobs](#creating-fine-tuning-jobs)
- [Monitoring Jobs](#monitoring-jobs)
- [Using Fine-Tuned Models](#using-fine-tuned-models)
- [Best Practices](#best-practices)

## Overview

Fine-tuning customizes a model for specific tasks by training on example data. Use when:
- Prompting alone doesn't achieve desired quality
- Need consistent style/format
- Want to reduce prompt length
- Require specialized domain knowledge

## Preparing Training Data

Training data format (JSONL file):

```jsonl
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]}
{"messages": [{"role": "user", "content": "What is 2+2?"}, {"role": "assistant", "content": "4"}]}
```

**Python - Create training file:**
```python
import json

training_examples = [
    {
        "messages": [
            {"role": "system", "content": "You are a customer service agent for Acme Corp."},
            {"role": "user", "content": "I want to return my order"},
            {"role": "assistant", "content": "I'd be happy to help with your return. Could you please provide your order number?"}
        ]
    },
    {
        "messages": [
            {"role": "system", "content": "You are a customer service agent for Acme Corp."},
            {"role": "user", "content": "Where is my package?"},
            {"role": "assistant", "content": "I can help track your package. Please share your order number or tracking ID."}
        ]
    }
]

with open("training_data.jsonl", "w") as f:
    for example in training_examples:
        f.write(json.dumps(example) + "\n")
```

### Data Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Examples | 10 | 50-100+ |
| Epochs | 1 | 3-4 |
| Max tokens per example | 16,385 (gpt-4o-mini) | Varies by model |

### Validation Data (Optional)

Separate file for validation (same format):
```python
# 10-20% of data for validation
validation_examples = training_examples[:len(training_examples)//5]
with open("validation_data.jsonl", "w") as f:
    for example in validation_examples:
        f.write(json.dumps(example) + "\n")
```

## Creating Fine-Tuning Jobs

**Python:**
```python
# Upload training file
training_file = client.files.create(
    file=open("training_data.jsonl", "rb"),
    purpose="fine-tune"
)

# Optional: Upload validation file
validation_file = client.files.create(
    file=open("validation_data.jsonl", "rb"),
    purpose="fine-tune"
)

# Create fine-tuning job
job = client.fine_tuning.jobs.create(
    training_file=training_file.id,
    validation_file=validation_file.id,  # Optional
    model="gpt-4o-mini-2024-07-18",
    hyperparameters={
        "n_epochs": 3,
        "batch_size": "auto",
        "learning_rate_multiplier": "auto"
    },
    suffix="my-custom-model"  # Optional: custom name suffix
)
print(f"Job ID: {job.id}")
```

**TypeScript:**
```typescript
const trainingFile = await client.files.create({
    file: fs.createReadStream('training_data.jsonl'),
    purpose: 'fine-tune'
});

const job = await client.fineTuning.jobs.create({
    training_file: trainingFile.id,
    model: 'gpt-4o-mini-2024-07-18',
    hyperparameters: {
        n_epochs: 3
    }
});
```

### Supported Base Models

| Model | Fine-Tuning Support |
|-------|---------------------|
| `gpt-4o-2024-08-06` | Yes |
| `gpt-4o-mini-2024-07-18` | Yes |
| `gpt-4-0613` | Yes |
| `gpt-3.5-turbo-0125` | Yes |

## Monitoring Jobs

**Python:**
```python
# Get job status
job = client.fine_tuning.jobs.retrieve(job.id)
print(f"Status: {job.status}")
print(f"Model: {job.fine_tuned_model}")  # Available when completed

# List events
events = client.fine_tuning.jobs.list_events(job.id, limit=10)
for event in events.data:
    print(f"{event.created_at}: {event.message}")

# List all jobs
jobs = client.fine_tuning.jobs.list(limit=10)

# Cancel job
client.fine_tuning.jobs.cancel(job.id)
```

**TypeScript:**
```typescript
const job = await client.fineTuning.jobs.retrieve(jobId);
console.log(`Status: ${job.status}`);

const events = await client.fineTuning.jobs.listEvents(jobId);
```

### Job Statuses

| Status | Description |
|--------|-------------|
| `validating_files` | Checking training data |
| `queued` | Waiting to start |
| `running` | Training in progress |
| `succeeded` | Completed successfully |
| `failed` | Error occurred |
| `cancelled` | Cancelled by user |

## Using Fine-Tuned Models

**Python:**
```python
# Use the fine-tuned model
response = client.chat.completions.create(
    model="ft:gpt-4o-mini-2024-07-18:org-name::job-id",  # Your fine-tuned model ID
    messages=[
        {"role": "system", "content": "You are a customer service agent for Acme Corp."},
        {"role": "user", "content": "I need to return something"}
    ]
)
```

**TypeScript:**
```typescript
const response = await client.chat.completions.create({
    model: 'ft:gpt-4o-mini-2024-07-18:org-name::job-id',
    messages: [
        { role: 'user', content: 'I need to return something' }
    ]
});
```

### Delete Fine-Tuned Model

```python
client.models.delete("ft:gpt-4o-mini-2024-07-18:org-name::job-id")
```

## Best Practices

### Data Quality

1. **Diverse examples** - Cover all expected use cases
2. **Consistent format** - Same structure across examples
3. **High quality** - Examples should represent ideal outputs
4. **Realistic inputs** - Match expected production queries
5. **No contradictions** - Consistent answers for similar questions

### Hyperparameters

| Parameter | Default | When to Adjust |
|-----------|---------|----------------|
| `n_epochs` | auto | Increase if underfitting, decrease if overfitting |
| `batch_size` | auto | Larger = faster but may reduce quality |
| `learning_rate_multiplier` | auto | Lower if training is unstable |

### Evaluation

```python
# Compare base vs fine-tuned
test_prompts = [
    "How do I track my order?",
    "Can I change my shipping address?"
]

for prompt in test_prompts:
    # Base model
    base_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    # Fine-tuned model
    ft_response = client.chat.completions.create(
        model="ft:gpt-4o-mini-2024-07-18:org::id",
        messages=[{"role": "user", "content": prompt}]
    )

    print(f"Prompt: {prompt}")
    print(f"Base: {base_response.choices[0].message.content}")
    print(f"Fine-tuned: {ft_response.choices[0].message.content}")
```

### Cost Considerations

- Training costs: Per token in training data
- Inference costs: Higher than base model
- Consider: Start with prompting, fine-tune only if needed
- Iterate: Start with fewer examples, add more if quality insufficient

### When NOT to Fine-Tune

- Few-shot prompting achieves good results
- Need to update behavior frequently
- Limited training data available
- Task is well-covered by base model
