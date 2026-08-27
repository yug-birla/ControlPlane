from sqlalchemy import select

from controlplane.db.engine import session_scope
from controlplane.db.models import ModelRegistryRecord
from controlplane.models.registry_seed import seed


def test_seed_creates_both_local_and_remote_entries():
    seed()
    with session_scope() as session:
        rows = session.execute(select(ModelRegistryRecord)).scalars().all()
        keys = {r.model_key for r in rows}
    assert "local_hf_all_minilm_l6_v2" in keys
    assert "groq_configured_model" in keys


def test_seed_is_idempotent_and_upserts():
    first_ids = sorted(seed())
    second_ids = sorted(seed())
    assert first_ids == second_ids


def test_local_entry_has_pinned_revision_and_no_unknown_parameter_count():
    seed()
    with session_scope() as session:
        record = session.execute(
            select(ModelRegistryRecord).where(ModelRegistryRecord.model_key == "local_hf_all_minilm_l6_v2")
        ).scalar_one()
    assert record.local_or_remote == "LOCAL"
    assert record.revision is not None
    assert record.parameter_count is not None
    assert record.license == "apache-2.0"


def test_remote_entry_does_not_hardcode_a_specific_model_name():
    seed()
    with session_scope() as session:
        record = session.execute(
            select(ModelRegistryRecord).where(ModelRegistryRecord.model_key == "groq_configured_model")
        ).scalar_one()
    assert record.local_or_remote == "REMOTE"
    assert record.model_family is None  # varies by GROQ_MODEL, never fixed here
