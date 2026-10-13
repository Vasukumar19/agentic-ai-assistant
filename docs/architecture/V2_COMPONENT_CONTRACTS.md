# V2 Component Contracts & Interface Specifications

**Author:** Principal AI Systems Architect & Core Platform Team  
**Date:** October 2026  
**Status:** Approved Specification  
**Companion Documents:** `V2_TARGET_ARCHITECTURE.md`, `V2_DATA_MODEL.md`

---

## 1. Core Execution Context & Identifiers

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution context threaded across all layers."""
    user_id: str
    session_id: str
    execution_id: str
    plan_id: Optional[str] = None
    step_id: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: "cor_" + str(int(datetime.now(timezone.utc).timestamp()*1000)))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

---

## 2. Intent Classification Contract

```python
class IntentRoute(str, Enum):
    FAST_INFO = "FAST_INFO"          # Direct knowledge lookup / Q&A / schedule lookup
    FAST_CHAT = "FAST_CHAT"          # Casual conversational turn / greeting
    DELIBERATE_ACTION = "DELIBERATE"  # Multi-step goal, side-effect tool execution
    MEMORY_MUTATION = "MEMORY_MUTATION"  # Personal profile update / preference fact


class IntentClassification(BaseModel):
    """Output of the Intent Classification stage."""
    route: IntentRoute
    confidence: float = Field(ge=0.0, le=1.0)
    requires_retrieval: bool
    requires_approval: bool
    target_domains: List[str] = Field(default_factory=list)  # ["documents", "calendar", "notes", "reminders"]
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
```

---

## 3. Knowledge & Citation Contracts

```python
class CitationRecord(BaseModel):
    """Verifiable source passage citation record."""
    citation_id: str                    # Unique identifier in prompt (e.g. "cite_01")
    document_id: str                    # Unique document UUID
    document_name: str                  # Human-readable filename
    chunk_id: str                       # Deterministic chunk ID
    page_number: Optional[int] = None   # Source document page number
    relevance_score: float              # Cross-Encoder similarity score
    exact_quote: str                    # Extracted excerpt from source chunk


class KnowledgeRetrievalRequest(BaseModel):
    query: str
    user_id: str
    top_k: int = 5
    score_threshold: float = 0.5
    include_documents: bool = True
    include_notes: bool = True
    include_profile: bool = True


class KnowledgeRetrievalResponse(BaseModel):
    profile_facts: Dict[str, Any]
    retrieved_citations: List[CitationRecord]
    combined_context_text: str
    total_context_tokens: int
```

---

## 4. Calendar Gateway Contract

```python
class EventStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    TENTATIVE = "TENTATIVE"
    CANCELLED = "CANCELLED"


class CalendarEvent(BaseModel):
    """Canonical calendar event representation."""
    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.CONFIRMED
    attendees: List[str] = Field(default_factory=list)
    is_all_day: bool = False


class CalendarListFilter(BaseModel):
    time_min: datetime
    time_max: datetime
    max_results: int = 50
    include_cancelled: bool = False


class ICalendarGateway:
    """Protocol implemented by Local Mock and Google Calendar adapters."""
    async def list_events(self, ctx: ExecutionContext, filt: CalendarListFilter) -> List[CalendarEvent]: ...
    async def get_event(self, ctx: ExecutionContext, event_id: str) -> Optional[CalendarEvent]: ...
```

---

## 5. Tool Gateway & Manifest Contracts

```python
class SideEffectLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class ApprovalRequirement(str, Enum):
    NEVER = "NEVER"
    ALWAYS = "ALWAYS"
    CONDITIONAL = "CONDITIONAL"


class ToolManifest(BaseModel):
    """Explicit capability declaration for all tools."""
    name: str                          # Fully qualified: "notes.delete"
    version: str                       # e.g. "1.0.0"
    description: str
    input_schema: Dict[str, Any]       # JSON Schema definition
    side_effect: SideEffectLevel
    approval: ApprovalRequirement
    idempotent: bool
    timeout_seconds: float = 30.0


class ToolErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"


class ToolResultEnvelope(BaseModel):
    """Standardized response from all tool executions."""
    status: str                         # "success" | "error" | "awaiting_approval"
    tool_name: str
    data: Optional[Dict[str, Any]] = None
    error_code: Optional[ToolErrorCode] = None
    error_message: Optional[str] = None
    retryable: bool = False
    duration_ms: int = 0
```

---

## 6. Action Approval & Token Contracts

```python
class ActionApprovalRequest(BaseModel):
    """Payload representing a pending action requiring human confirmation."""
    action_id: str
    user_id: str
    tool_name: str
    arguments: Dict[str, Any]
    approval_token: str                # HMAC-SHA256 signature
    summary: str                       # Human-readable prompt: "Delete note 'Hardware Budget'"
    risk_level: SideEffectLevel
    expires_at: datetime


class ActionApprovalDecision(BaseModel):
    """User response to approval request."""
    action_id: str
    approval_token: str
    decision: str                      # "APPROVE" | "REJECT"
    decided_by_user_id: str
    reason: Optional[str] = None
```

---

## 7. Outcome Verifier Contract

```python
class VerificationStatus(str, Enum):
    SATISFIED = "SATISFIED"            # Goal completely fulfilled
    INSUFFICIENT = "INSUFFICIENT"      # Execution incomplete, need more steps
    BLOCKED = "BLOCKED"                # Unrecoverable error, abort execution


class OutcomeVerification(BaseModel):
    """Evaluates whether tool execution satisfies the original user goal."""
    status: VerificationStatus
    explanation: str
    missing_information: List[str] = Field(default_factory=list)
    suggested_next_tool: Optional[str] = None
```

---

## 8. Observability & Event Sink Contract

```python
class EventSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class SystemTraceEvent(BaseModel):
    """Immutable trace event emitted to decoupled sink."""
    event_id: str
    correlation_id: str
    user_id: str
    session_id: str
    execution_id: str
    timestamp: datetime
    component: str                     # "router" | "knowledge" | "gateway"
    event_type: str                    # "RETRIEVAL_COMPLETED" | "TOOL_EXECUTED"
    severity: EventSeverity
    duration_ms: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_details: Optional[Dict[str, Any]] = None


class IObservabilitySink:
    """Thread-safe event sink that decouples telemetry from state."""
    def emit(self, event: SystemTraceEvent) -> None: ...
    async def emit_async(self, event: SystemTraceEvent) -> None: ...
```
