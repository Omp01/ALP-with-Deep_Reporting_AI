"""
Pydantic schemas for video checkpoints and anti-skipping validation.
"""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CheckpointOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Option identifier e.g. 'A', 'B', 'C', 'D'")
    text: str = Field(..., description="Option label text")


class VideoCheckpointItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_item_id: UUID
    timestamp_seconds: float
    transcript_segment: Optional[str] = None
    question: str
    options: List[CheckpointOption]
    order_index: int = 0
    status: str = Field(default="pending", description="pending, displayed, answered, correct, incorrect")
    selected_option_id: Optional[str] = None
    attempt_count: int = 0
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
