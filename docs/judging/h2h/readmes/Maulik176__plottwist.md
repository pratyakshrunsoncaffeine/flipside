# PlotTwist

Friends write the mystery, a director twists it live, and a checker proves the players can still finish.

Built for the Flip the Switch hackathon (Track 02, Best Personal or Creative Workflow), on
[Switch](https://github.com/sandbox-quantum/switch). Work in progress: this README grows with the project.

## How it works

Two Switch rooms on Discord:

- **Backstage** (private): the director and writers. The answer key lives here.
- **Player room**: the players and the game.

The game engine is plain code that joins both rooms as a Switch agent. Players type commands (`look`, `take tape`,
`answer panel 472`). In Backstage the director proposes a twist (`twist remove tape | A pipe bursts…`). Before
anything changes, a deterministic checker searches every state the players can reach from where they are now:

- **APPROVABLE**: they can still reach the intended ending and can't get stuck. `confirm P-n` applies it.
- **BLOCKED**: it would strand them, lose the intended ending, set a trap, or let them skip a protected discovery.
  The verdict explains why, and ordinary confirm is withheld.

The same twist can be refused before players discover a clue and accepted after, while the evidence they already
learned survives. No LLM decides any of this. See [docs/design.md](docs/design.md).

## Run the tests

```bash
uv sync
uv run pytest -q
```

## Run the engine against Switch

Needs Switch Console 0.40.1 with its local server running and a Discord server connected.

```bash
uv run plottwist-engine register --name plottwist-engine
uv run plottwist-engine run --world tests/fixtures/clue.json \
  --backstage "<backstage room name>" --players "<player room name>" --director "<your Switch participant id>"
```

`register` reads a registration key from `~/.config/plottwist/registration_key` and stores the engine's own key in
`~/.config/plottwist/agent.json` (mode 600). On a Console-managed local server that runs without Docker there is no
Gateway page for creating a registration key, so for now the server's bootstrap key is used. Setup steps will be
documented in full here.
