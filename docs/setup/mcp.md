# Running the MCP server

The MCP server exposes a minimal set of Research Runtime operations to an MCP
client (e.g. Qwen Studio). It runs **local-only** over stdio — no network
socket is opened.

---

## Install

```text
pip install -e ".[dev]"
```

This installs the `qwen-research` package and the `mcp` SDK dependency.

---

## Run

```text
python -m qwen_research.mcp
```

or, after installing the console script:

```text
qwen-research-mcp
```

The server blocks, serving MCP over stdin/stdout. It exits cleanly when the
client closes the connection (Ctrl-C also terminates it).

---

## Connect from Qwen Studio / Desktop

Configure the MCP client to launch the server as a stdio command. For example,
a typical client configuration:

```json
{
  "mcpServers": {
    "qwen-research": {
      "command": "python",
      "args": ["-m", "qwen_research.mcp"],
      "cwd": "/path/to/qwen-research-system"
    }
  }
}
```

Use the absolute path to the Python interpreter (e.g. the project venv) if
needed. The client will discover the server, list the six tools, and invoke
them.

---

## Available tools

| Tool | Purpose |
|------|---------|
| `get_session` | read a session by id |
| `create_session` | create a session (project id + operating mode) |
| `execute_task` | create/classify/plan a task |
| `continue_task` | advance a task one step |
| `get_task_state` | read a task's state |
| `get_research_state` | read a task's structured research state |

---

## Security defaults

- **Local-only:** stdio transport; no public binding.
- **Minimal permissions:** only `read` and `analyze` are enabled by default;
  `write`/`execute`/`destructive` are disabled.
- **No secrets in responses:** errors are normalized to safe messages; no
  provider credentials, filesystem internals, or chain-of-thought are exposed.

See [`../architecture/security.md`](../architecture/security.md) and
[`../architecture/mcp-implementation.md`](../architecture/mcp-implementation.md).
