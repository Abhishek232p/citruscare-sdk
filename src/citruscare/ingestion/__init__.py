"""Authorized-source knowledge ingestion abstractions."""

from citruscare.ingestion.pipeline import (
    IngestionPipeline,
    IngestionResult,
    RawRecord,
    SourceConnector,
)

__all__ = ["IngestionPipeline", "IngestionResult", "RawRecord", "SourceConnector"]
