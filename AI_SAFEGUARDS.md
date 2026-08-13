# AI Safeguards regression framework

Run `tests/test_ai_safeguards.py` whenever models, prompts, retrieval settings,
coding, evidence confidence, or decision-support logic changes. The framework
fails closed on missing review gates, accepted AI status, fabricated quotations,
unsupported causal/statistical claims, absent scope, cross-scope results, and
invalid qualitative confidence treatment.

## Training and data use

Participant material is for inference, retrieval, transcription and analysis
only. It must not train or fine-tune public foundation models, and must not
train a shared Citizen Centric model across organisations. A future fine-tuning
feature requires separate organisation enablement, lawful basis, governance,
and isolation; it is not implemented here.

## Zero-tolerance controls

- fabricated quotation: 0 accepted
- cross-organisation/study result: 0 accepted
- missing review gate: 0 accepted
- anonymous or participant approval: 0 accepted
