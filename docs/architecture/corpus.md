# Corpus

The corpus layer holds files and source material, with an explicit **security
boundary**: filesystem access is allowlisted to configured roots, and a
retrieval request can never escape them.

---

## Corpus roots

```text
CorpusRoot
    root_id
    path
    name
    enabled
    read_only          (default true)
    recursive          (default true)
    include_patterns
    exclude_patterns
```

Multiple roots are supported (`Research/`, `Papers/`, `Books/`, …). The
architecture never assumes a specific absolute path; roots come from
`CorpusConfig`.

---

## Security boundary

The resolution flow is `request → retrieval → CorpusRoot validation →
normalized path → filesystem`. The system rejects:

- `../` traversal
- absolute paths outside roots
- symlink escapes (symlinks are resolved before the containment check, and are
  refused entirely when `follow_symlinks = false`)
- excluded directories / patterns

`PathSecurityError` carries **no** offending absolute path. A retrieval request
cannot escape the configured roots, and no unrestricted filesystem tools
(`read_any_file`, `list_any_directory`) are exposed.

---

## Configuration

```text
CorpusConfig
    roots[]
    supported_extensions[]
    excluded_patterns[]
    maximum_file_size   (default 50 MiB)
    follow_symlinks     (default false)
    indexing_workers
    chunk_size
    chunk_overlap
```

Safe defaults favor `follow_symlinks = false` and `read_only = true`.

---

## Discovery (scanner)

The scanner walks configured roots, respects include/exclude rules, enforces
containment, detects supported files, computes metadata and a SHA-256 content
hash, and reports candidate `FileRecord`s with a status (`NEW`, `UNCHANGED`,
`MODIFIED`, `MISSING`, `UNSUPPORTED`, `TOO_LARGE`, `ERROR`). Discovery is kept
separate from ingestion: the scanner never parses content.

---

## Identifiers & provenance

Document identity is a stable hash of `(root_id, relative_path)` — stable across
content changes, never a raw filesystem path. Every chunk retains enough
provenance to answer: *which file, which document, which page/section, which
chunk*.

See [`document-pipeline.md`](document-pipeline.md) and
[`retrieval.md`](retrieval.md).
