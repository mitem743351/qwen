"""Qwen Research System — local AI research infrastructure.

Phase 1 establishes the **core domain and runtime contracts**: stable,
provider- and transport-independent domain objects, runtime interfaces, the
task state machine, an error model, configuration model, and testable
in-memory contracts.

The boundary this package enforces:

    MCP Server        = protocol/capability adapter          (future)
    Research Runtime  = provider-independent research app    (contracts here)
    Inference Runtime = model/provider execution boundary    (contracts here)
    Domain            = stable contracts shared by all of them  (here)

No MCP, Qwen API, retrieval, database, or dashboard implementation lives here
in Phase 1.
"""

__version__ = "0.1.0"
