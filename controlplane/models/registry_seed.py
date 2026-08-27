"""Seeds ``model_registry`` with the two models this milestone actually
uses. Run once (idempotent -- upserts by ``model_key``):

    .venv/Scripts/python -m controlplane.models.registry_seed
"""

from __future__ import annotations

from sqlalchemy import select

from controlplane.db.engine import session_scope
from controlplane.db.models import ModelRegistryRecord, new_id
from controlplane.models.local_hf_provider import EMBEDDING_DIMENSION, MODEL_REPO, MODEL_REVISION

_ENTRIES = [
    dict(
        model_key="local_hf_all_minilm_l6_v2",
        provider="local_hf",
        source="huggingface",
        display_name="all-MiniLM-L6-v2 (local)",
        model_family="MiniLM",
        capabilities={"tasks": ["EMBEDDING"]},
        parameter_count=22_700_000,  # verified via file-size/fp32 math, see docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md
        context_window=256,
        latency_class="fast",
        cost_class="free",
        local_or_remote="LOCAL",
        hardware_requirements={"ram_mb": 200, "disk_mb": 100, "gpu_required": False},
        license="apache-2.0",
        revision=MODEL_REVISION,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["fast CPU inference", "no API cost", "no network dependency at inference time"]},
        known_weaknesses={"notes": ["384-dim embeddings only", "256-token max sequence length", "no generation capability"]},
    ),
    dict(
        model_key="groq_configured_model",
        provider="groq",
        source="groq_api",
        display_name="Groq (model selected via GROQ_MODEL env var)",
        model_family=None,
        capabilities={"tasks": ["GENERATION"]},
        parameter_count=None,
        context_window=None,
        latency_class="fast",
        cost_class="metered",
        local_or_remote="REMOTE",
        hardware_requirements={},
        license=None,
        revision=None,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["low-latency hosted inference", "no local compute/RAM cost"]},
        known_weaknesses={
            "notes": [
                "requires network + GROQ_API_KEY",
                "per-token cost",
                "actual model/parameter_count/context_window vary by GROQ_MODEL and are not known until configured -- never hard-coded, see docs/PROJECT_STATE/DECISIONS.md",
            ]
        },
    ),
]


def seed() -> list[str]:
    seeded = []
    with session_scope() as session:
        for entry in _ENTRIES:
            existing = session.execute(
                select(ModelRegistryRecord).where(ModelRegistryRecord.model_key == entry["model_key"])
            ).scalar_one_or_none()
            if existing:
                for key, value in entry.items():
                    setattr(existing, key, value)
                seeded.append(existing.id)
            else:
                record = ModelRegistryRecord(id=new_id("model"), **entry)
                session.add(record)
                seeded.append(record.id)
    return seeded


if __name__ == "__main__":
    ids = seed()
    print(f"Seeded/updated {len(ids)} model_registry rows: {ids}")
