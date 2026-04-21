# Ingestion Service Template

## Responsibility
Compose ingestion stages for validation, metadata extraction, persistence, and post-processing.

## Contracts
- Stage ordering must be deterministic.
- Stage failures should include source path and stage name.
- Retry policy should be orchestrated by queue service, not stage implementation.
