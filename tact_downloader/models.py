"""型付きの外部データモデル。"""

from typing import TypedDict


class SiteRecord(TypedDict, total=False):
    entityId: str
    id: str
    entityTitle: str
    title: str


class ResourceRecord(TypedDict):
    url: str
    name: str
    relative_path: str
    type: str
    size: int | str | None


class AttachmentRecord(TypedDict):
    name: str
    url: str
    size: int | str | None
    type: str


class SubmissionRecord(TypedDict, total=False):
    id: str
    submittedText: str
    submitted: bool
    userSubmission: bool
    graded: bool
    returned: bool
    draft: bool
    late: bool
    dateSubmitted: str
    dateSubmittedEpochSeconds: int | float
    status: str
    grade: str
    feedbackText: str
    feedbackComment: str
    submittedAttachments: list[AttachmentRecord]
    feedbackAttachments: list[AttachmentRecord]


class AssignmentRecord(TypedDict):
    id: str
    title: str
    instructions: str
    status: str
    draft: bool
    openTimeString: str
    dueTimeString: str
    dropDeadTimeString: str
    closeTimeString: str
    submissionType: str
    gradeScale: str
    maxGradePoint: str | int | float | None
    attachments: list[AttachmentRecord]
    submissions: list[SubmissionRecord]
