# Configuring a local corpus

The MCP server exposes `search_corpus` and `get_source` over an indexed local
corpus. The corpus is configured via two environment variables:

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_CORPUS_DB` | Path to the SQLite index database |
| `QWEN_RESEARCH_CORPUS_ROOT` | An allowlisted corpus directory (read-only, recursive) |

When both are set, the server incrementally indexes the root on startup and
serves ranked evidence through MCP. Without them, the server runs with no
corpus (`search_corpus` returns a "no corpus retriever configured" error).

---

## Example (Qwen Studio / Desktop MCP config)

```json
{
  "mcpServers": {
    "qwen-research": {
      "command": "python",
      "args": ["-m", "qwen_research.mcp"],
      "cwd": "/path/to/qwen-research-system",
      "env": {
        "QWEN_RESEARCH_CORPUS_DB": "/path/to/data/corpus.db",
        "QWEN_RESEARCH_CORPUS_ROOT": "/path/to/research/papers"
      }
    }
  }
}
```

---

## Configuration reference (typed model)

The full typed configuration model is `CorpusConfig` (see
[`../architecture/corpus.md`](../architecture/corpus.md)). A YAML shape for a
future config-file loader:

```yaml
corpus:
  roots:
    - id: research
      path: /path/to/research     # placeholder — never hard-coded
      read_only: true
      recursive: true
    - id: papers
      path: /path/to/papers
      read_only: true
      recursive: true
  supported_extensions: [.txt, .md, .pdf, .py, .json, .yaml, .csv]
```

---

## Security

- Roots are **allowlisted**; a retrieval request cannot escape them (no `../`,
  absolute-path, or symlink escape).
- Retrieved documents are **untrusted data** — their contents never change tool
  permissions or system behavior.
- The server stays local-only (stdio); no public binding.

See [`../architecture/security.md`](../architecture/security.md).
