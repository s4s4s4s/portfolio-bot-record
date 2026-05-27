# Architecture v1 (frozen)

Intent-routing + FSM booking + LLM copy (`human_reply.say`).

- **Routing:** heuristics + `classify_intent` → `_handle_user_text` pipeline
- **Booking:** aiogram FSM (service → master → date → slot → name → phone → confirm)
- **Copy:** Groq LLM per scene, facts injected from code
- **Safety:** atomic slot reserve, phone normalize, cancel confirm, usage limits

Tag `v1.0.0` — baseline before **v2** (receptionist: single LLM turn + tools, FSM as executor only).

Branch `v2` — active development for LLM-full dialogue.
