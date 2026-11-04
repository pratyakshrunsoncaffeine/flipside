# Code Review Duel

Two AI reviewers on **different models** review the same code in one Switch room, check each other's work, and ask a human to pick the better review.

Built for the Flip the Switch Hackathon. Runs entirely on free models, with no API keys and no subscriptions.

## Why this exists

One AI reviewer can be confidently wrong. In my test, both reviewers got `int x = 5 / 0;` (Java):

- **reviewer-a** (DeepSeek) said it is a compile error. Wrong.
- **reviewer-b** (GLM) said it compiles and throws `ArithmeticException` at runtime. Right.

A single-model setup would have given me the wrong answer with no warning. With two models in one room, the disagreement is visible and a human makes the call.

## How it works

1. You post a code snippet in `code-review-room`.
2. reviewer-a posts its review (starts with `A:`).
3. reviewer-b posts its review (starts with `B:`) and asks reviewer-a if it agrees.
4. reviewer-a answers "I agree because..." or "I disagree because...".
5. reviewer-b does the same, then asks the human: "Admin, reply A or B to pick."
6. You reply `A` or `B`, and both reviewers acknowledge and stop.

## Why Switch is central

This project does not work without Switch:

- **One room, two agents.** Both reviewers read the same room history, so each can answer the other's review.
- **Agents address each other by name.** The chain (review, agree/disagree, ask the human) runs through mentions in the room.
- **The human is in the same room.** Your pick is just another message in the thread.
- **Different models, one place.** Switch connects both agents to the same chat without any glue code.

## Setup

You need Docker Desktop, Node.js, and Switch Console.

1. Install OpenCode: `npm install -g opencode-ai`
2. Check the free models: `opencode models` (look for names ending in `-free`)
3. Install Switch Console: https://github.com/sandbox-quantum/switch/releases/latest
4. Start Docker Desktop, open Switch Console, and click Start on the local server.
5. Import `code-review-duel.template.yaml`. First change both `machine:` lines to your computer's name.
6. Open `code-review-room` and post a snippet, tagging both reviewers:

```
@reviewer-a @reviewer-b Review this Java code:
int x = 5 / 0;
System.out.println(x);
```

## Models used

| Agent | Model |
|---|---|
| reviewer-a | `opencode/deepseek-v4.1-flash-free` |
| reviewer-b | `opencode/glm-5.3-flash-free` |

Free models can be slow or busy. If a reviewer goes quiet, swap its model for another `-free` one in `opencode models`.

## Demo

TODO: add demo video link.

## What I learned

TODO: fill in after the build (agents only act when mentioned by name; free models sometimes time out on long code; instructions must name who speaks next).
