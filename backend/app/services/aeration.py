"""曝气控制业务规则：状态流转、锁定校验、归属校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "aeration"
REQUIRED_FIELDS = ["记录编号", "曝气池编号", "溶解氧值"]
STATUS_ORDER = ["待调节", "已调节", "待复核", "已锁定"]
LOCKED_STATUS = STATUS_ORDER[-1]
# 每个动作只允许在指定的当前状态下发起；已锁定不在任何动作的前置状态里，
# 因此锁定后对记录的一切写操作（含再次提交调节改参数）都会被拦下。
ACTION_RULES: dict[str, dict[str, Any]] = {
    "提交调节": {"from": "待调节", "to": "已调节"},
    "复核确认": {"from": "已调节", "to": "待复核"},
    "锁定参数": {"from": "待复核", "to": "已锁定"},
}
# 提交调节时允许随动作一起写入的工艺参数；其它字段不接受动作通道修改。
ADJUSTABLE_FIELDS = ["溶解氧值", "风量设定"]
# 未显式指定操作人员时的默认归属，保证跨值班人共享记录也能按归属区分。
DEFAULT_OPERATOR = "值班管理员"


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
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["风量设定"] = values.get("风量设定")
        entry["操作人员"] = str(values.get("操作人员") or "").strip() or DEFAULT_OPERATOR
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._present(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"曝气记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于曝气控制可执行范围"

        rule = ACTION_RULES[action]
        current = entry.get("status")
        # 同一个根因的第一道闸：状态机前置校验。
        # 已锁定的记录没有任何合法后继动作，锁定后一律只读，不能再改参数或退回。
        if current == LOCKED_STATUS:
            return None, f"曝气记录 {entry_id} 参数已锁定，锁定期间只读，不能再执行「{action}」或修改溶解氧、风量设定"
        if current != rule["from"]:
            if current == rule["to"]:
                return None, f"曝气记录 {entry_id} 当前已是「{current}」状态，请勿重复{action}"
            expected = rule["from"]
            return None, f"曝气记录 {entry_id} 当前为「{current}」，需先到「{expected}」才能{action}"

        # 第二道闸：归属校验。跨值班人共享同一条记录时，只允许归属操作人员操作。
        operator = str(values.get("操作人员") or "").strip() or DEFAULT_OPERATOR
        owner = str(entry.get("操作人员") or "").strip()
        if owner and operator != owner:
            return None, f"曝气记录 {entry_id} 归属「{owner}」，当前值班人「{operator}」无权操作，请联系归属值班人"

        # 第三道闸：提交调节才允许改工艺参数；空数据与重复调节在这里给出说明。
        if action == "提交调节":
            blanks = [
                field for field in ADJUSTABLE_FIELDS
                if not str(values.get(field) if values.get(field) is not None else entry.get(field) or "").strip()
            ]
            if blanks:
                return None, f"提交调节失败：{'、'.join(blanks)}不能为空，请补全后再提交"
            for field in ADJUSTABLE_FIELDS:
                if values.get(field) is not None:
                    entry[field] = values.get(field)

        target = rule["to"]
        entry["status"] = target
        entry["pending"] = target != LOCKED_STATUS
        entry["abnormal"] = False
        return self._present(entry), f"曝气记录已{action}"

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """对外口径：列表、详情、导出都用真实状态回填「控制状态」，保持一致。"""
        data = dict(entry)
        data["控制状态"] = entry.get("status")
        return data
