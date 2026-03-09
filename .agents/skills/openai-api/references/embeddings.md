# Embeddings Reference

## Table of Contents
- [Creating Embeddings](#creating-embeddings)
- [Batch Embeddings](#batch-embeddings)
- [Similarity Search](#similarity-search)
- [Dimensionality Reduction](#dimensionality-reduction)
- [Use Cases](#use-cases)

## Creating Embeddings

**Python:**
```python
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="The quick brown fox jumps over the lazy dog"
)
embedding = response.data[0].embedding  # List of floats
print(f"Dimensions: {len(embedding)}")  # 1536 for text-embedding-3-small
```

**TypeScript:**
```typescript
const response = await client.embeddings.create({
    model: 'text-embedding-3-small',
    input: 'The quick brown fox jumps over the lazy dog'
});
const embedding = response.data[0].embedding;
```

## Batch Embeddings

Embed multiple texts in one request (more efficient):

**Python:**
```python
texts = [
    "First document about AI",
    "Second document about machine learning",
    "Third document about neural networks"
]

response = client.embeddings.create(
    model="text-embedding-3-small",
    input=texts
)

embeddings = [item.embedding for item in response.data]
```

**TypeScript:**
```typescript
const texts = [
    'First document about AI',
    'Second document about machine learning',
    'Third document about neural networks'
];

const response = await client.embeddings.create({
    model: 'text-embedding-3-small',
    input: texts
});

const embeddings = response.data.map(item => item.embedding);
```

## Similarity Search

Calculate cosine similarity between embeddings:

**Python:**
```python
import numpy as np

def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Example: Find most similar document
query_embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input="What is deep learning?"
).data[0].embedding

# Compare to stored embeddings
similarities = [
    cosine_similarity(query_embedding, doc_embedding)
    for doc_embedding in document_embeddings
]
most_similar_idx = np.argmax(similarities)
```

**TypeScript:**
```typescript
function cosineSimilarity(a: number[], b: number[]): number {
    const dotProduct = a.reduce((sum, val, i) => sum + val * b[i], 0);
    const normA = Math.sqrt(a.reduce((sum, val) => sum + val * val, 0));
    const normB = Math.sqrt(b.reduce((sum, val) => sum + val * val, 0));
    return dotProduct / (normA * normB);
}
```

## Dimensionality Reduction

text-embedding-3 models support native dimension reduction:

**Python:**
```python
# Reduce to 256 dimensions (from 1536)
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Sample text",
    dimensions=256
)
embedding = response.data[0].embedding
print(f"Dimensions: {len(embedding)}")  # 256
```

Smaller dimensions = faster similarity search, lower storage costs, slight quality tradeoff.

### Recommended Dimensions

| Use Case | Dimensions | Notes |
|----------|------------|-------|
| High accuracy | 1536 (default) | Best quality |
| Balanced | 512-1024 | Good tradeoff |
| Fast/cheap | 256 | Still reasonable quality |
| Minimal | 64-128 | Significant quality loss |

## Models

| Model | Dimensions | Max Tokens | Notes |
|-------|------------|------------|-------|
| `text-embedding-3-small` | 1536 | 8191 | Best value |
| `text-embedding-3-large` | 3072 | 8191 | Highest quality |
| `text-embedding-ada-002` | 1536 | 8191 | Legacy model |

### Performance Comparison

| Model | MTEB Score | Cost |
|-------|------------|------|
| text-embedding-3-large | 64.6% | Higher |
| text-embedding-3-small | 62.3% | Lower |
| text-embedding-ada-002 | 61.0% | Legacy |

## Use Cases

### Semantic Search

```python
# Index documents
docs = ["doc1 content", "doc2 content", ...]
doc_embeddings = client.embeddings.create(
    model="text-embedding-3-small",
    input=docs
).data

# Search
def search(query: str, top_k: int = 5):
    query_emb = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    ).data[0].embedding

    scores = [cosine_similarity(query_emb, d.embedding) for d in doc_embeddings]
    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [(docs[i], scores[i]) for i in top_indices]
```

### Clustering

```python
from sklearn.cluster import KMeans

# Get embeddings
embeddings = np.array([e.embedding for e in doc_embeddings])

# Cluster
kmeans = KMeans(n_clusters=5)
labels = kmeans.fit_predict(embeddings)

# Group documents by cluster
clusters = {}
for i, label in enumerate(labels):
    clusters.setdefault(label, []).append(docs[i])
```

### Anomaly Detection

```python
# Calculate centroid of "normal" embeddings
normal_embeddings = np.array([...])
centroid = normal_embeddings.mean(axis=0)

# Detect anomalies (low similarity to centroid)
def is_anomaly(embedding, threshold=0.7):
    similarity = cosine_similarity(embedding, centroid)
    return similarity < threshold
```

### RAG (Retrieval-Augmented Generation)

```python
def rag_query(question: str):
    # 1. Find relevant documents
    relevant_docs = search(question, top_k=3)

    # 2. Build context
    context = "\n\n".join([doc for doc, _ in relevant_docs])

    # 3. Generate answer with context
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Answer based on this context:\n{context}"},
            {"role": "user", "content": question}
        ]
    )
    return response.choices[0].message.content
```

## Best Practices

1. **Chunk long documents** - Split into ~500 token chunks with overlap
2. **Normalize embeddings** - For faster cosine similarity (dot product)
3. **Use batch requests** - More efficient than single requests
4. **Cache embeddings** - Store in vector database for production
5. **Match dimensions** - Query and document embeddings must use same dimensions
