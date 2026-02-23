---
title: "How LFG's Orchestrator Turns a Single Request into a Multi-Agent Pipeline"
date: 2026-02-14
excerpt: "Most AI tools give you one agent. LFG gives you a coordinator that reads your request, builds an execution plan, and dispatches specialized agents to work in parallel — while you watch."
slug: orchestrator-multi-agent-pipelines
---

# How LFG's Orchestrator Turns a Single Request into a Multi-Agent Pipeline

Most AI coding tools are single-agent: you type a prompt, the AI responds. It's a one-to-one interaction. This works well for small, self-contained tasks — but it breaks down the moment work gets complex.

Real product development isn't one task. It's a cascade: you need research before you can write a PRD, a PRD before you can plan implementation, implementation before you can write tests. Each step depends on the last. And most steps can be broken into sub-tasks that could run in parallel if something were coordinating them.

That coordination problem is exactly what LFG's orchestrator solves.

---

## What the Orchestrator Does

When you send a message to LFG — "build a user onboarding flow with email verification" — it doesn't immediately start writing code. It first figures out what kind of work this actually is.

The orchestrator categorizes every request into one of four types:

- **Direct response** — A question or decision that can be answered conversationally
- **Research** — Gathering information before acting
- **Single task** — One concrete deliverable (a PRD, a bug fix, a specific feature)
- **Pipeline** — A sequence of dependent tasks that must execute in order

For the onboarding flow request, it's a pipeline. The orchestrator doesn't just recognize this — it constructs the plan:

```
1. Research existing auth setup and codebase patterns
2. Write a PRD for the onboarding flow
3. Break PRD into implementation tickets
4. Implement email sending service
5. Implement verification token logic
6. Build the onboarding UI components
7. Write integration tests
```

Each item becomes a ticket. Dependencies are tracked. Tickets that can run in parallel do.

---

## The Specialist Agent Roster

Once the plan exists, the orchestrator dispatches work to the right agent for each ticket type. LFG runs several specialist agents, each with a different system prompt and tool set:

- **Product Agent**: PRDs, feature requirements, user stories, acceptance criteria
- **Code Agent**: Implementation, refactoring, bug fixes, code reviews
- **Design Agent**: UI/UX specifications, component design, interaction flows
- **Builder Agent**: Infrastructure, architecture, system design
- **Turbo Agent**: High-speed execution for well-defined, bounded tasks

The onboarding flow example would hit the Product Agent first (PRD), then hand off to the Code Agent for implementation, with the Design Agent potentially running in parallel on the UI components.

---

## How Tickets Flow Through the System

Each ticket in LFG's system has a clear lifecycle:

```
queued → ready → running → completed (or failed, or blocked)
```

A ticket moves to `ready` when all its dependencies are complete. The orchestrator monitors this continuously — when a ticket completes, it checks the dependency graph and unblocks whatever was waiting.

If a ticket fails, the orchestrator doesn't just surface an error. It analyzes what went wrong, decides whether to retry, break the ticket into smaller steps, or escalate to a human reviewer.

This autonomous error handling is one of the biggest practical differences from single-agent tools. You don't have to babysit the pipeline.

---

## What You See While It Runs

The principle we've built around is: the more autonomous the system, the more visible it needs to be.

When the orchestrator is running a pipeline, you can see:

- The execution plan it built (every ticket, every dependency)
- Which tickets are running right now
- The agent output streaming in real time as each ticket executes
- Status updates when tickets complete or hit issues
- The final synthesized result when the pipeline finishes

Nothing happens in a black box. You can pause, redirect, or take over at any point.

---

## When Pipelines Are Worth It

Not every request needs a full pipeline. The orchestrator is smart about this — most conversational questions get direct answers, most small tasks get single-agent execution.

Pipelines kick in when:
- The work requires multiple distinct types of expertise
- Steps have clear dependencies between them
- The total scope is too large for one context window
- Parallel execution would meaningfully reduce clock time

For large features, product sprints, or any work that would take a developer multiple days — the pipeline approach pays for itself almost immediately.

---

## The Organizational Implication

Here's the shift that matters most: when work happens in a coordinated pipeline rather than through ad-hoc prompting, the human's role changes.

You're not directing each individual step. You're setting the objective, reviewing the plan, and reviewing outputs at key checkpoints. The in-between work happens without your intervention.

That's not a subtle difference. It's the difference between using AI as a tool and using AI as a workforce.

LFG is built around the latter.
