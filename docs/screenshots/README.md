# Screenshots

Primary portfolio diagram (checked in):

- [`../architecture.svg`](../architecture.svg) — system layers and agent loop

Optional live captures (add after you run the stack; do **not** include API keys or private hosts in the image):

| Suggested file | Content |
|----------------|---------|
| `webui-query.png` | LightRAG WebUI answering a GB 39901 question |
| `cli-ask.png` | Terminal: `python -m reg_harness.cli ask "..."` with JSON answer |
| `neo4j-browser.png` | Optional graph browser view (no credentials in frame) |

How to capture:

```bash
make v4-up
# WebUI http://127.0.0.1:9621
cd harness && python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？"
```

Then drop PNGs into this folder and link them from the root README if desired.
