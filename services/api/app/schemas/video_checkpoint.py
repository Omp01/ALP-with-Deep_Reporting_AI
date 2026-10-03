"""
Pydantic schemas for video checkpoints, attempt-based scoring, and remediation.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CheckpointOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Option identifier e.g. 'A', 'B', 'C', 'D'")
    text: str = Field(..., description="Option label text")


class CheckpointRemediation(BaseModel):
    """
    Direct link back to relevant video section and transcript for incorrect answers.
    """
    topic: str
    video_title: str
    content_item_id: UUID
    timestamp_start_seconds: float
    timestamp_end_seconds: float
    section_label: str  # e.g. "05:20 - 08:45"
    explanation: Optional[str] = None
    action_url: Optional[str] = None


class VideoCheckpointItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_item_id: UUID
    timestamp_seconds: float
    timestamp_start_seconds: Optional[float] = None
    timestamp_end_seconds: Optional[float] = None
    topic: Optional[str] = None
    transcript_segment: Optional[str] = None
    question: str
    options: List[CheckpointOption]
    order_index: int = 0
    max_score: float = 10.0
    status: str = Field(default="pending", description="pending, displayed, answered, correct, incorrect")
    selected_option_id: Optional[str] = None
    attempt_count: int = 0
    score: float = 0.0
    formula_id: Optional[str] = None
    calculation_details: Optional[Dict[str, Any]] = None
    # Answers and explanations are exposed only after the user attempts the question
    correct_option_id: Optional[str] = None
    explanation: Optional[str] = None


class VideoCheckpointsResponse(BaseModel):
    content_item_id: UUID
    total_checkpoints: int
    completed_checkpoints: int
    checkpoints: List[VideoCheckpointItem]


class VideoCheckpointAnswerRequest(BaseModel):
    selected_option_id: str = Field(..., description="The selected option ID, e.g. 'A'")


class VideoCheckpointAnswerResponse(BaseModel):
    checkpoint_id: UUID
    is_correct: bool
    status: str  # correct, incorrect
    selected_option_id: str
    correct_option_id: str
    score: float = 0.0
    max_score: float = 10.0
    attempt_number: int = 1
    formula_id: str = "attempt_decay_v1"
    formula_version: str = "1.0.0"
    calculation_details: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    remediation: Optional[CheckpointRemediation] = None
    explanation: Optional[str] = None
    all_checkpoints_completed: bool = False


class VideoCheckpointStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="displayed, etc.")


class VideoSeekValidationRequest(BaseModel):
    current_time: float = Field(..., description="Playback time before seeking (seconds)")
    target_time: float = Field(..., description="Target seek time (seconds)")


class VideoSeekValidationResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    first_missed_checkpoint: Optional[VideoCheckpointItem] = None
    missed_checkpoints: List[VideoCheckpointItem] = []

