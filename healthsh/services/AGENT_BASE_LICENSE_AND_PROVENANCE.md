# Agent base — provenance and licence

The agent loop in `ai_service.py` (model-call + tool-dispatch + retry) is a
**clean-room implementation** of the pattern Healthsh's roadmap calls
"Blocksh's agent base". I did not have access to the Blocksh source at the
time this code was written, so nothing here is a verbatim port. The contract
is the same shape — register tools, run a model loop, dispatch tool calls,
emit streamed text + tool-call events — but the actual implementation is new.

If the project later wants to vendor the real Blocksh agent base, this file
should be updated with:

- the Blocksh repository URL,
- the commit hash that was ported,
- the licence under which it was ported (and any compatible attribution),
- a diff or note describing modifications from the upstream.

Until then: the code is original MIT-licensed source under the same project
licence.
