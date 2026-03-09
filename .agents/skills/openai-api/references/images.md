# Image Generation (DALL-E) Reference

## Table of Contents
- [Image Generation](#image-generation)
- [Image Editing](#image-editing)
- [Image Variations](#image-variations)
- [Model Comparison](#model-comparison)

## Image Generation

**Python:**
```python
response = client.images.generate(
    model="dall-e-3",
    prompt="A futuristic cityscape at sunset",
    size="1024x1024",
    quality="standard",
    n=1
)
image_url = response.data[0].url

# Get as base64 instead of URL
response = client.images.generate(
    model="dall-e-3",
    prompt="A futuristic cityscape at sunset",
    size="1024x1024",
    response_format="b64_json"
)
import base64
image_bytes = base64.b64decode(response.data[0].b64_json)
```

**TypeScript:**
```typescript
const response = await client.images.generate({
    model: 'dall-e-3',
    prompt: 'A futuristic cityscape at sunset',
    size: '1024x1024',
    quality: 'standard',
    n: 1
});
const imageUrl = response.data[0].url;

// Get as base64
const b64Response = await client.images.generate({
    model: 'dall-e-3',
    prompt: 'A futuristic cityscape at sunset',
    size: '1024x1024',
    response_format: 'b64_json'
});
const imageBase64 = b64Response.data[0].b64_json;
```

### DALL-E 3 Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `size` | `1024x1024`, `1792x1024`, `1024x1792` | Square or landscape/portrait |
| `quality` | `standard`, `hd` | HD has more detail |
| `style` | `vivid`, `natural` | Vivid is more hyper-real |
| `n` | `1` only | DALL-E 3 generates one image per request |

### DALL-E 2 Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `size` | `256x256`, `512x512`, `1024x1024` | Smaller sizes available |
| `n` | `1-10` | Can generate multiple images |

## Image Editing

Edit images with a mask (DALL-E 2 only):

**Python:**
```python
response = client.images.edit(
    model="dall-e-2",
    image=open("original.png", "rb"),
    mask=open("mask.png", "rb"),  # Transparent areas will be edited
    prompt="A red sports car",
    size="1024x1024",
    n=1
)
```

**TypeScript:**
```typescript
import fs from 'fs';

const response = await client.images.edit({
    model: 'dall-e-2',
    image: fs.createReadStream('original.png'),
    mask: fs.createReadStream('mask.png'),
    prompt: 'A red sports car',
    size: '1024x1024',
    n: 1
});
```

**Mask requirements:**
- Same dimensions as original image
- PNG format with alpha channel
- Transparent areas indicate where to edit
- Fully transparent = edit here
- Fully opaque = preserve original

## Image Variations

Create variations of an existing image (DALL-E 2 only):

**Python:**
```python
response = client.images.create_variation(
    model="dall-e-2",
    image=open("original.png", "rb"),
    size="1024x1024",
    n=3
)
for i, img in enumerate(response.data):
    print(f"Variation {i+1}: {img.url}")
```

**TypeScript:**
```typescript
const response = await client.images.createVariation({
    model: 'dall-e-2',
    image: fs.createReadStream('original.png'),
    size: '1024x1024',
    n: 3
});
```

## Model Comparison

| Feature | DALL-E 3 | DALL-E 2 |
|---------|----------|----------|
| Image quality | Higher | Standard |
| Prompt adherence | Better | Good |
| Max images per request | 1 | 10 |
| Image editing | No | Yes |
| Image variations | No | Yes |
| Sizes | 1024x1024, 1792x1024, 1024x1792 | 256x256, 512x512, 1024x1024 |
| Quality modes | standard, hd | N/A |
| Style modes | vivid, natural | N/A |

### Prompt Tips for DALL-E 3

- Be specific and detailed
- DALL-E 3 may revise your prompt - check `response.data[0].revised_prompt`
- For precise control, start prompt with "I NEED to test how the tool works..."
- Avoid prohibited content (violence, adult content, real people)

```python
response = client.images.generate(
    model="dall-e-3",
    prompt="A photorealistic image of a golden retriever playing in autumn leaves"
)
print(f"Revised prompt: {response.data[0].revised_prompt}")
```
