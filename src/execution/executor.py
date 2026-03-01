from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
from datetime import datetime
from ..common.types import Order, OrderType, OrderSide


class ExecutionStatus(Enum):
    pending = "pending"
    filled = "filled"
    cancelled = "cancelled"
    rejected = "rejected"


@dataclass
class ExecutionRecord:
    order: Order
    status: ExecutionStatus
    created_at: datetime
    updated_at: datetime


class ExecutionEngine:
    def __init__(self):
        self.records: Dict[str, ExecutionRecord] = {}

    def submit_order(self, order: Order) -> str:
        now = datetime.utcnow()
        rec = ExecutionRecord(order=order, status=ExecutionStatus.pending, created_at=now, updated_at=now)
        self.records[order.order_id] = rec
        self._fill_immediately(order.order_id)
        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        rec = self.records.get(order_id)
        if not rec:
            return False
        if rec.status != ExecutionStatus.pending:
            return False
        rec.status = ExecutionStatus.cancelled
        rec.updated_at = datetime.utcnow()
        rec.order.status = "cancelled"
        return True

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        rec = self.records.get(order_id)
        if not rec:
            return None
        return {
            "order_id": rec.order.order_id,
            "status": rec.status.value,
            "filled_quantity": rec.order.filled_quantity,
            "avg_fill_price": rec.order.avg_fill_price,
            "updated_at": rec.updated_at.isoformat(),
        }

    def _fill_immediately(self, order_id: str) -> None:
        rec = self.records.get(order_id)
        if not rec:
            return
        o = rec.order
        o.filled_quantity = o.quantity
        o.avg_fill_price = o.limit_price if o.order_type == OrderType.LIMIT else o.avg_fill_price or 0.0
        o.status = "filled"
        rec.status = ExecutionStatus.filled
        rec.updated_at = datetime.utcnow()

