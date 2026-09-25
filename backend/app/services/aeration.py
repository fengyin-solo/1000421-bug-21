"""曝气控制业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "aeration"
REQUIRED_FIELDS = ["记录编号", "曝气池编号", "溶解氧值"]
STATUS_ORDER = ["待调节", "已调节", "待复核", "已锁定"]
ACTION_RULES = {"提交调节": "已调节", "复核确认": "待复核", "锁定参数": "已锁定"}
# 每个动作允许的起点状态：已锁定是终态，不出现在任何起点里，锁定后记录只读。
ACTION_SOURCES = {"提交调节": ["待调节"], "复核确认": ["已调节"], "锁定参数": ["待复核"]}
# 只允许随「提交调节」更新的参数；其余字段（含记录编号、曝气池编号）全程不可改。
EDITABLE_FIELDS = ["溶解氧值", "风量设定", "风机频率"]
LOCKED_STATUS = "已锁定"
NEGATIVE_ACTIONS = []


class AerationService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in EDITABLE_FIELDS + ["调节时间", "操作人员"]:
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"曝气记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于曝气控制可执行范围"
        label = entry.get("记录编号") or entry_id
        current = str(entry.get("status") or "")
        if current == LOCKED_STATUS:
            locker = entry.get("锁定人") or entry.get("操作人员") or "当班人员"
            return None, (
                f"曝气记录 {label} 已由{locker}锁定，溶解氧值、风量设定等参数只读，"
                f"不能再执行「{action}」"
            )
        allowed = ACTION_SOURCES[action]
        if current not in allowed:
            if action == "提交调节" and current == "已调节":
                return None, f"曝气记录 {label} 已处于已调节状态，请勿重复提交调节"
            return None, (
                f"曝气记录 {label} 当前为「{current}」，"
                f"只有「{'、'.join(allowed)}」状态才能执行「{action}」"
            )
        values = values or {}
        operator = str(values.get("操作人员") or "").strip()
        if action == "提交调节":
            changed = [
                field for field in EDITABLE_FIELDS
                if str(values.get(field) or "").strip()
            ]
            if not changed:
                return None, (
                    f"曝气记录 {label} 未填写任何调节参数，"
                    f"请至少填写{'、'.join(EDITABLE_FIELDS)}中的一项再提交"
                )
            for field in changed:
                entry[field] = values.get(field)
        if operator:
            entry["操作人员"] = operator
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if target == LOCKED_STATUS:
            entry["锁定人"] = operator or entry.get("操作人员") or "当班人员"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"曝气记录 {label} 已{action}"
