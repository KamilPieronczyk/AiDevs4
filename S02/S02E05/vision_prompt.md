---
model: gpt-5.4
---
Analyze the attached map of the Zarnowiec power plant area.

Your task:
1. Count the map grid columns and rows.
2. Find the dam sector. The task description says the water near the dam has intentionally stronger color intensity to make the dam easier to locate.
3. Return the dam sector coordinates using 1-based indexing where the top-left sector is `x=1, y=1`.

Return only JSON:
{
  "columns": 0,
  "rows": 0,
  "target_sector": {"x": 0, "y": 0},
  "confidence": "low|medium|high",
  "evidence": "max 30 words"
}

Rules:
- `x` is the column number.
- `y` is the row number.
- Be precise. The mission depends on hitting the dam, not just a water area.
- If uncertain, still provide the single best sector and lower confidence.
