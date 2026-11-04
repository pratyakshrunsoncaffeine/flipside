# Tableline

Reservation requests do not arrive where the booking lives. A guest writes on Instagram, the booking platform emails a notice, a partner site has its own reservation, and a wedding inquiry lands the same afternoon. Someone on the floor still has to work out what is free and what to answer.

Tableline is a Switch room for that work. Each source it has been given is turned into the same kind of reservation event. The room shows the conflict or the missing fact. The request is kept in the room's own ledger so its history can be read, and no booking is written and no guest is answered until a person on the team decides. The reservation system the restaurant already uses stays the record of the booking.

```text
request or notice → source adapter → shared event → Switch room → staff decision → daily PDF / calendar file
```

## What Switch does here

Switch connects an agent runtime that is already signed in on the server, Claude Code, Codex, or OpenCode, to the chat app that server already uses: Slack, Discord, Teams, or Mattermost. `templates/tableline.template.yaml` opens one private channel, `{team}-reservations`, with three agents and the person who created it.

- The coordinator runs the Tableline commands and posts the result. It takes instructions from the person who created the room, and from that person's agents, and from nobody else. Switch enforces this with the agent's addressing setting, so the approval that goes through the coordinator is the owner's, whoever else is invited to read along.
- The booking agent and the guest agent comment on what the coordinator posted. They answer the same owner, and they do not run the commands. Their folders are not the ledger.
- Auto mode and bypass permissions are off on all three, so the runtime asks before it acts.

The room is where the decision happens in front of the team: the conflict, the slot that was withheld, who said yes, and the reference someone typed afterward. Without Switch this is a script on one laptop that nobody else can see.

Cursor was the editor for this repository. It is not the agent in the room.

Everything below runs on synthetic files. Nothing calls a booking API, polls a mailbox, or sends a message.

## Try it

Python 3.9 or newer. Nothing to install.

```bash
git clone https://github.com/Crisvond-hnt/tableline-demo.git
cd tableline-demo
python3 -m integrations configure
python3 -m unittest discover -s tests -t . -v
python3 -m integrations demo
```

`demo` runs the fixture night in a temporary ledger and prints:

- the snapshot time, and the conflict with NL-0881 for a party of four at 20:00
- an empty `offered` list, with 21:30 in `withheld_slots` because NL-1042 and TF-2201 have a start time and no verified duration
- a refused approval of 21:30 that names those two reservations
- the calendar rows with a known start and end, and the rows left out by name

`configure` lists the house rules that are still `unknown`. `python3 -m integrations review` lists the files and events that were held for staff instead of accepted. `demo` does not write `var/store.json`; the other commands do.

To run the same checks in a chat channel, open Switch Console, start a local server, import `templates/tableline.template.yaml`, and use it with the repository URL above. `docs/SERVER_SETUP.md` walks through it from a fresh install, including Slack and Telegram.

## The fixture night

Northline is a fictional restaurant in Lisbon. Every guest is invented. The night is 14 November 2026.

The snapshot, `fixtures/snapshot.json`, is marked `live: false` and generated at 16:00 UTC. NL-0881 is booked from 19:30 to 21:00 and NL-0902 from 18:00 to 19:15, so both can be used as windows. NL-0770 is on the snapshot from 21:30 to 22:30.

Mara Quinn's message asks for four people at 20:00. The check names the conflict with NL-0881 and does not name the other guest. It does not offer 21:30 either: a UMAI-shaped notice for NL-1042 and a TheFork-shaped notice for TF-2201 have a start time that evening and no verified duration, so any slot at or after those starts is withheld for a person to look at. Approving 21:30 on that feed is refused, and the refusal says why.

A cancellation is different. A newer notice cancels NL-0770, which already had a start and an end on the snapshot. On a feed whose only change is that cancellation, 21:30 is clear and can be approved. The tests take that path. A slot is offered only if the house lists it in `candidate_slots`, the party fits that slot's maximum, and nothing on the reconciled feed covers it; a request for seven at 21:30 is held, because that slot takes six. The approval must match an offered date, time, and party size exactly, and the command reads the snapshot and the notice feed again at that moment, so a notice that arrived after the offer was posted is enough to refuse it. The reference, NL-2044 in the demo, is a note typed after someone enters the booking in the real system; the command checks its shape and this folder's own records, and never reads the booking platform. The guest confirmation that follows is stored as `simulated` and not delivered.

Lee Okonkwo's email is a wedding, so it stays an event inquiry. Staff name the questions, the follow-up date is one the owner types, and the reply is simulated.

The PDF is the list for that service date. The `.ics` file includes only rows with a known start and end, so NL-0881 and NL-0902 are in it, and notices and typed references without a duration are named in comments and left out. If two notices for one reservation cannot be put in order, both files are refused rather than printed. Neither file is a live sync, and the calendar file is not connected to Google Calendar.

## How a source becomes an event

Each source has a small adapter. UMAI-shaped email is `integrations/mailbox.py`. TheFork-shaped JSON is `integrations/thefork.py`. Both emit `tableline.reservation_event.v1`, described in `docs/schema.md`, and the ledger keeps the events that pass. A third source would be another adapter writing the same object.

Deduplication uses the provider, the source label, the event kind, and the event id together, so the same id from two providers is two events, and a TheFork id never overwrites a UMAI row. A notice that fails validation, or a file that cannot be read, is held for review without being marked seen, and the rest of the batch continues. A corrected copy of that file can be ingested later.

Each notice carries `source_message_time`, the email Date header or the time written on the fixture, and `ingested_at`, when the local process recorded it. The first is not proof that a mailbox received anything. Dates, clock times, and timestamps are checked before they affect a conflict or an export; 2026-02-31 is rejected.

The snapshot and the notices are reconciled by those timestamps. A notice older than the snapshot does not replace a snapshot row. Two notices for the same reservation with the same source time are not ordered by guesswork; the check stops and says so.

A notice without a verified duration does not clear the rest of the evening. A duration is used only when `rules.turn_time_verified` is true and `rules.turn_time_minutes` is a positive number of minutes. The sample config sets neither.

## What is connected

| Input | In this repository |
|---|---|
| Dated snapshot | Synthetic file, `fixtures/snapshot.json`, `live: false`. The conflict check uses it. |
| UMAI-shaped email | Parser for the fixture contract in `fixtures/emails/`. No mailbox is polled. |
| TheFork-shaped JSON | Parser for `fixtures/thefork/`. [TheFork's partner API](https://docs.thefork.io/B2B-API/introduction) is not called. |
| OpenTable | Not connected. Their APIs need partner approval: [docs.opentable.com](https://docs.opentable.com/). No fixture and no client. |
| Guest messages | Fixture files. Replies are simulated and not delivered. |
| UMAI API | No public API found on [umai.io](https://www.umai.io/). No client in this code. |
| Daily PDF and `.ics` | Written from the snapshot and the local ledger. Unknown durations are left out of the calendar file. |

The longer table, with the provider documentation that was checked, is `docs/integration-matrix.md`.

## Another restaurant

Copy `fixtures/restaurant.json` or point `TABLELINE_CONFIG` at another file. `python3 -m integrations configure` accepts `unknown`, and rejects a blank rule, a source marked `connected`, and an email address outside `example.test`, `example.com`, and `example.invalid`.

The sample leaves hours, service windows, party size, turn time, buffers, closed dates, areas, capacities, approval roles, sources, and daily output unknown on purpose. The field notes are in `docs/restaurant-config.md`, and what a restaurant hands over to go live, including redacted notices, is `docs/pilot-inputs.md`. The code is under the MIT license.

Server clicks are in `docs/SERVER_SETUP.md`, the recording order in `demo/SCRIPT.md`, the event and request shapes in `docs/schema.md` and `docs/lifecycle.md`, and the module notes in `integrations/README.md`.
