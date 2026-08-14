# Notes on Retrieval-Augmented Generation

Retrieval-augmented generation combines a retriever with a language model so
that the model grounds its answers in a corpus of private documents.

## Evidence Packaging

Evidence must carry provenance so a reader can trace every claim back to a
source document, a page, and a section. Anonymous retrieved text is not
acceptable for research use.

## Prompt Injection

Retrieved documents are untrusted data. A document containing instructions
must remain document content and never change tool behavior.
