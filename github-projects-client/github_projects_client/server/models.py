"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Response models ---


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ItemsResponse(BaseModel):
    items: list[dict[str, Any]]
    total_in_page: int
    has_more: bool = False
    next_cursor: Optional[str] = None


class CompactItemsResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total_in_page: int
    has_more: bool = False
    next_cursor: Optional[str] = None


class MutationResponse(BaseModel):
    success: bool
    item_ref: str
    field_name: str
    old_value: str = ""
    new_value: str = ""
    error: Optional[str] = None


class BulkMutationResult(BaseModel):
    item_ref: str
    success: bool
    old_value: str = ""
    new_value: str = ""
    error: Optional[str] = None


class BulkMutationResponse(BaseModel):
    success_count: int
    failure_count: int
    results: list[BulkMutationResult]


# --- Request models ---


class SetFieldRequest(BaseModel):
    value: str


class BulkSetFieldRequest(BaseModel):
    item_refs: list[str]
    value: str


# --- Field models ---


class FieldInfo(BaseModel):
    name: str
    id: str
    type: str


class FieldsResponse(BaseModel):
    fields: list[FieldInfo]


class FieldOptionItem(BaseModel):
    name: str


class SingleSelectOptionsResponse(BaseModel):
    field_name: str
    type: str = "single_select"
    options: list[FieldOptionItem]


class IterationItem(BaseModel):
    title: str
    start_date: Optional[str] = None


class IterationOptionsResponse(BaseModel):
    field_name: str
    type: str = "iteration"
    active: list[IterationItem]
    completed: list[IterationItem]


# --- Audit log models ---


class AuditLogEntry(BaseModel):
    timestamp: str
    caller: str = ""
    endpoint: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    error: Optional[str] = None


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
