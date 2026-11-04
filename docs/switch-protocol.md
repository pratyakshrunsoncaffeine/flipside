# Switch protocol notes

Read from the Switch v0.9 source on 2026-11-04, with file references into `sandbox-quantum/switch`.
Not yet checked against a running server.

## Registering a custom agent

- `POST /agents` with `Authorization: Bearer <token>`.
  The token is a personal API key (the agent is then owned by that person) or `AGENT_REGISTRATION_TOKEN` from `.env` (owned by a synthetic bootstrap account).
- Body: `name`, `description`, `connector_type: "custom"`, `overwrite`, and `integration_profile` with `connection_model: "always_on"`, `message_exchange: true` and empty mediation and reporting lists (`core/tests/e2e/follow_the_conversation/harness.py:145-161`).
- Response: `{id, api_key}`. A duplicate name is 409 unless `overwrite` is true.
- `register-known` only accepts claude-code, codex, opencode, antigravity and cursor.

## Receiving messages

- SSE: `GET /agents/{id}/events?connection_id=<uuid>&scope=all&filter=all&start_from=head` with `Accept: text/event-stream`.
  The WebSocket at `/agents/{id}/connection/ws` is the primary transport; SSE is kept for compatibility.
- Heartbeat: `POST /agents/{id}/connection/beat {connection_id}`.
  The server's interval is 10 s with a 30 s TTL; the docs say 2 s / 6 s; beating every 2 s is safe.
  A 404 or 409 on a beat means reopen the stream.
- Message event: `{type: "message", room_id, payload: {message_id, sender, sender_name, sender_role, body, thread_id, addressed, ...}}`.
  `sender` is an opaque participant id; `sender_name` is the platform username.

## Acting

- `POST /agents/{id}/ops/{name}` with header `X-Switch-Connection-Id` and the bare arguments as the body; the response is `{"result": ...}`.
- `connect_to_room(room_id, include_general_instructions)` before `post_message(body, thread_id)`.
- `create_room_from_yaml(yaml, inputs)` returns `{room_id, room_name, ...}`; rooms are created as the calling agent's owner, so `{$creator}` is the PR author.
- `invite_agent_to_room(room_id, agent_name)`.

## Who may answer

- An agent's addressing policy (`owner`, `owner-agents`, `anyone`) is enforced server-side.
  An agent cannot change its own policy; the owner sets it in the dashboard.
- The gate also accepts answers only from the author's configured chat username.

## Approval cards

- Any agent can open one with `POST /agent-sessions/{session_id}/approvals` (`kind` approval or questions, `options` with accept/decline decisions, optional `room_id` and `thread_id`).
  Only people the addressing policy admits can answer.
  Not used yet; a candidate for previewing contradictions privately before they post.
