"""
Validation script for all ControlPlane datasets.
"""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DOCS = BASE / 'docs' / 'DATA'
DATA = BASE / 'data'

errors = []

# 1. Check Query Profiles Large
qps_file = DATA / 'raw' / 'generated' / 'query_profiles_large.json'
with open(qps_file, 'r', encoding='utf-8') as f:
    qps = json.load(f)

req_fields = {
    'query_id', 'query', 'intent', 'domain', 'knowledge_type',
    'required_data_sources', 'required_capabilities', 'complexity',
    'risk', 'actionability', 'sensitivity', 'ambiguity',
    'expected_route', 'taxonomy_labels', 'provenance'
}
valid_tax = {
    'PUBLIC_FACTUAL', 'PRIVATE_FACTUAL', 'RAG', 'INSUFFICIENT_RAG',
    'SQL', 'ANALYTICAL', 'REASONING', 'CODING', 'RECOMMENDATION',
    'DECISION_SUPPORT', 'MEMORY', 'CHAT_HISTORY', 'AGENTIC',
    'HIGH_RISK_AGENTIC', 'SENSITIVE', 'AMBIGUOUS', 'MULTI_SOURCE', 'MULTI_STEP'
}
valid_risk = {'NO_ACTION', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK', 'CRITICAL'}
valid_sens = {'NONE', 'POTENTIAL_PII', 'PII_EXPOSURE', 'SENSITIVE_DATA_EXPOSURE'}

ids = set()
for q in qps:
    qid = q.get('query_id')
    if qid in ids:
        errors.append(f"Duplicate query_id: {qid}")
    ids.add(qid)
    
    missing = req_fields - set(q.keys())
    if missing:
        errors.append(f"{qid} missing fields: {missing}")
    
    if q.get('risk') not in valid_risk:
        errors.append(f"{qid} invalid risk: {q.get('risk')}")
        
    if q.get('sensitivity') not in valid_sens:
        errors.append(f"{qid} invalid sensitivity: {q.get('sensitivity')}")
        
    for t in q.get('taxonomy_labels', []):
        if t not in valid_tax:
            errors.append(f"{qid} invalid taxonomy: {t}")

print(f"1. Query Profiles Checked: {len(qps)} records. Errors: {len(errors)}")

# 2. Check RAG Cases
rag_file = DATA / 'raw' / 'generated' / 'rag_cases.json'
with open(rag_file, 'r', encoding='utf-8') as f:
    rag = json.load(f)
rag_req = {
    'case_id', 'query', 'documents', 'retrieved_documents',
    'document_relevance', 'evidence_sufficiency', 'ground_truth',
    'expected_answer', 'rag_category'
}
for r in rag:
    missing = rag_req - set(r.keys())
    if missing:
        errors.append(f"RAG {r.get('case_id')} missing: {missing}")
print(f"2. RAG Cases Checked: {len(rag)} records.")

# 3. Check Interventions
interv_file = DATA / 'raw' / 'generated' / 'intervention_cases.json'
with open(interv_file, 'r', encoding='utf-8') as f:
    intervs = json.load(f)
valid_interv = {
    'KEEP', 'VERIFY', 'RETRIEVE_MORE', 'RERANK', 'CHANGE_MODEL',
    'INCREASE_COMPUTE', 'DECREASE_COMPUTE', 'CHANGE_DATA_SOURCE',
    'REGENERATE', 'REPAIR', 'REDACT', 'ASK_CLARIFICATION',
    'HUMAN_REVIEW', 'ABSTAIN', 'BLOCK', 'OTHER'
}
interv_req = {
    'case_id', 'initial_route', 'failure', 'severity', 'evidence',
    'possible_interventions', 'preferred_intervention', 'reason',
    'expected_effect', 'cost_effect', 'latency_effect', 'risk_effect'
}
for i in intervs:
    missing = interv_req - set(i.keys())
    if missing:
        errors.append(f"Intervention {i.get('case_id')} missing: {missing}")
    if i.get('preferred_intervention') not in valid_interv:
        errors.append(f"Intervention {i.get('case_id')} invalid pref interv: {i.get('preferred_intervention')}")
print(f"3. Intervention Cases Checked: {len(intervs)} records.")

# 4. Check Counterfactuals
cf_file = DATA / 'raw' / 'generated' / 'counterfactual_cases.json'
with open(cf_file, 'r', encoding='utf-8') as f:
    cfs = json.load(f)
cf_req = {
    'case_id', 'query', 'route_A', 'result_A', 'route_B',
    'result_B', 'which_is_better', 'why', 'cost_A', 'cost_B',
    'latency_A', 'latency_B'
}
for c in cfs:
    missing = cf_req - set(c.keys())
    if missing:
        errors.append(f"Counterfactual {c.get('case_id')} missing: {missing}")
print(f"4. Counterfactual Cases Checked: {len(cfs)} records.")

# 5. Check Agent Trajectories
traj_file = DATA / 'raw' / 'generated' / 'agent_trajectories.json'
with open(traj_file, 'r', encoding='utf-8') as f:
    trajs = json.load(f)
traj_req = {
    'trajectory_id', 'trajectory_type', 'user_request', 'plan',
    'steps', 'final_action', 'final_answer', 'risk',
    'intervention_point', 'expected_control_action'
}
for t in trajs:
    missing = traj_req - set(t.keys())
    if missing:
        errors.append(f"Trajectory {t.get('trajectory_id')} missing: {missing}")
print(f"5. Agent Trajectories Checked: {len(trajs)} records.")

# 6. Check Evaluation Splits
splits_dir = DATA / 'evaluation'
total_split_count = 0
for s in ['train', 'validation', 'test', 'challenge']:
    sfile = splits_dir / s / f"query_profiles_{s}.json"
    with open(sfile, 'r', encoding='utf-8') as f:
        sdata = json.load(f)
        total_split_count += len(sdata)
        print(f"   Split {s}: {len(sdata)} records")

if total_split_count != len(qps):
    errors.append(f"Splits total ({total_split_count}) != query profiles total ({len(qps)})")

# 7. Check Synthetic DB & Docs
db_dir = DATA / 'synthetic_enterprise' / 'database'
csv_files = list(db_dir.glob('*.csv'))
print(f"6. Synthetic DB Tables: {len(csv_files)} CSV files.")

docs_dir = DATA / 'synthetic_enterprise' / 'documents'
doc_files = list(docs_dir.glob('*.txt'))
print(f"7. Synthetic Documents: {len(doc_files)} policy/product text documents.")

chat_file = DATA / 'synthetic_enterprise' / 'chat' / 'chat_history.json'
with open(chat_file, 'r', encoding='utf-8') as f:
    chats = json.load(f)
print(f"8. Synthetic Chat Records: {len(chats)} sessions.")

print("\n-------------------------------------------------------")
if errors:
    print(f"VALIDATION FAILED with {len(errors)} errors:")
    for err in errors[:10]:
        print(" -", err)
else:
    print("ALL VALIDATION CHECKS PASSED PERFECTLY WITH ZERO ERRORS!")
print("-------------------------------------------------------")
