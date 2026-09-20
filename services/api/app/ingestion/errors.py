"""
Errors raised by the ingestion pipeline.

Every error carries a stable machine-readable `code` (shown to API clients and stored on
the job) and a message that is safe and useful to put in front of an administrator.
Nothing in this pipeline fails silently: a stage that cannot complete raises one of these
and the job records exactly which stage and why.
"""


class IngestionError(Exception):
    code = "ingestion_error"
    http_status = 400
    retryable = False

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


# ---- rejected at the door (nothing is stored) ------------------------------------------------
class InvalidUpload(IngestionError):
    code = "invalid_upload"
    http_status = 422


class UnsupportedFormat(IngestionError):
    code = "unsupported_format"
    http_status = 415


class FileTooLarge(IngestionError):
    code = "file_too_large"
    http_status = 413


class InvalidUrl(IngestionError):
    code = "invalid_url"
    http_status = 422


# ---- failures while processing (recorded on the job) -----------------------------------------
class SourceUnavailable(IngestionError):
    """The remote source could not be reached right now; trying again may work."""
    code = "source_unavailable"
    http_status = 502
    retryable = True


class VideoUnavailable(IngestionError):
    """The video does not exist, is private, or is not embeddable."""
    code = "video_unavailable"
    http_status = 422


class EmptyContent(IngestionError):
    code = "empty_content"
    http_status = 422


class NoTranscript(IngestionError):
    """The content is fine but has no text to analyse. The administrator can supply a transcript."""
    code = "no_transcript"


class TranscriptionUnavailable(IngestionError):
    """No speech-to-text engine is configured. The administrator can supply a transcript."""
    code = "transcription_unavailable"


class AIUnavailable(IngestionError):
    """No AI provider is configured, or it could not be reached."""
    code = "ai_unavailable"
    http_status = 503
    retryable = True


class AIOutputInvalid(IngestionError):
    """The model answered, but not with usable, well-formed output."""
    code = "ai_output_invalid"
    retryable = True
