from __future__ import annotations

from datetime import datetime, timedelta

from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db
from care_lifeline.memory import patient_memory

# 种子纵向指标（契约 §8）：让慢病趋势图直接有数据可看。
_SEED_METRICS: dict[str, tuple[float, str, float]] = {
    # metric_name: (起始值, 单位, 单步增量)
    "收缩压": (138.0, "mmHg", 3.0),
    "空腹血糖": (6.4, "mmol/L", 0.3),
}


def _seed_patients_and_metrics() -> None:
    patient_memory.ensure_patient(1, "张先生")
    patient_memory.ensure_patient(2, "李女士")
    now = datetime.now()
    for day in range(28, -1, -7):
        for name, (base, unit, step) in _SEED_METRICS.items():
            for patient_id in (1, 2):
                offset = (patient_id - 1) % 2  # 两位患者相位错开
                value = round(base + step * ((28 - day) // 7 + offset), 1)
                patient_memory.append_metric(
                    patient_id, name, value, unit, measured_at=now - timedelta(days=day)
                )


def seed() -> None:
    init_db()
    session_store.seed_demo_user()
    _seed_patients_and_metrics()
    print("seeded: admin/admin123(admin), doctor/doctor123(clinician), demo/demo123(patient)")
    print("seeded: patients 1-2 with longitudinal metrics (28 days)")


if __name__ == "__main__":
    seed()
