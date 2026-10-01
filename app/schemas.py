from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Status(str, Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


# Allowed status transitions. Finished orders are final.
TRANSITIONS: dict[Status, set[Status]] = {
    Status.new: {Status.in_progress, Status.cancelled},
    Status.in_progress: {Status.done, Status.cancelled},
    Status.done: set(),
    Status.cancelled: set(),
}


class OrderCreate(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    item: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=10_000)
    unit_price: float = Field(ge=0, le=1_000_000)

    @field_validator("customer", "item")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class StatusUpdate(BaseModel):
    status: Status


class Order(BaseModel):
    id: int
    customer: str
    item: str
    quantity: int
    unit_price: float
    total: float
    status: Status
    created_at: str
    updated_at: str


class OrderPage(BaseModel):
    items: list[Order]
    total: int
    limit: int
    offset: int
