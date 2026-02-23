---
title: "Transparent Tickets: Why Every AI Action Should Be Reviewable"
date: 2026-02-16
excerpt: "AI that works autonomously is only trustworthy if you can see exactly what it did and why. LFG's ticket system makes every agent action visible, reviewable, and correctable."
slug: transparent-tickets-ai-execution
---

# Transparent Tickets: Why Every AI Action Should Be Reviewable

There's a failure mode that's becoming common as AI tools get more capable: the black box problem.

You give an AI a task. It goes off and does things. Eventually it hands you an output. And you have no idea what it actually did, what decisions it made, or whether you'd make the same choices if you'd been the one doing the work.

For low-stakes tasks — writing a commit message, generating a test — this is fine. You can read the output and judge it directly.

For complex, multi-step work — building a feature, refactoring a system, implementing a product requirement — the black box is a serious problem. The output alone isn't enough information. You need to understand the path to trust the destination.

LFG's answer to this is the ticket system. Every piece of work the AI performs exists as a discrete, inspectable record.

---

## What a Ticket Contains

Every ticket in LFG represents one unit of work. Before execution starts, it has:

- **Title**: What this ticket is doing in plain English
- **Description**: The full context — what's being built, why, relevant background
- **Acceptance criteria**: Explicit conditions that define "done"
- **Type**: What kind of work this is (research, PRD creation, implementation, testing, bug fix, etc.)
- **Dependencies**: Which other tickets must complete before this one runs

During and after execution:

- **Status trail**: Every status transition, timestamped
- **Agent output**: The full streamed output from the AI as it worked
- **Sandbox link**: The isolated execution environment where code ran
- **Completion summary**: What was produced, what succeeded, what was skipped

---

## Why Acceptance Criteria Matter

One of the less obvious design choices in LFG is requiring explicit acceptance criteria for every ticket before execution starts.

The instinct is to skip this — it's extra friction, and the AI is going to do what it does regardless. But acceptance criteria serve two purposes that aren't about the AI at all.

First, they force the orchestrator (and the human reviewing the plan) to be explicit about what success looks like before any work happens. Vague goals produce vague work. "Implement user authentication" is a spec for an entire system. "Implement JWT token generation and validation with refresh token support, tested with expired/invalid token cases" is a ticket.

Second, they give you a standard for review. When a ticket comes back completed, you're not just asking "does this look right?" You're checking specific, enumerable conditions. This makes review faster and more consistent.

---

## Status as a Communication Protocol

The ticket status — `queued`, `ready`, `running`, `completed`, `failed`, `blocked` — isn't just bookkeeping. It's how the orchestrator and the human interface communicate.

`blocked` is particularly important. When a ticket is blocked, it means the AI hit something it can't resolve autonomously — a missing dependency, an ambiguous requirement, a decision that requires business context. The orchestrator surfaces this immediately rather than guessing or proceeding with bad assumptions.

This is the opposite of hallucination risk. The system is designed to stop and ask when it's uncertain, not to make something up and keep going.

---

## Parallel Visibility

Because all work is ticketed, you can see an entire sprint's worth of work in progress simultaneously. Three tickets running in parallel is just three rows in a list, each streaming their outputs in real time.

This is a qualitative change from watching a single conversation. You can compare outputs, catch inconsistencies between what different agents are producing, and spot when two tickets are making conflicting assumptions — before they're both "done" and you have to reconcile them.

---

## The Review Checkpoint

LFG doesn't assume every ticket output is automatically correct. The system has explicit review checkpoints built into pipelines — moments where work pauses and a human is expected to look at outputs before the next stage begins.

Typically this happens at high-leverage points: after a PRD is generated (before breaking it into implementation tickets), after a major feature is implemented (before tests are written against it), after a refactor (before it's merged into the main branch).

These checkpoints aren't gaps in the automation. They're intentional design. The best AI-human collaboration isn't AI handling everything; it's AI handling everything it's good at, and humans intervening at the moments where human judgment is most valuable.

---

## What This Means in Practice

If you've worked with AI coding assistants before, the ticket-based workflow takes a little adjustment. You're not editing a prompt and re-running until you get what you want. You're reviewing a plan, approving it, and then reviewing outputs at checkpoints.

The upside: you spend far less time on execution and far more time on direction. The quality of the output correlates more with the quality of the acceptance criteria you wrote than with how much you intervened during execution.

That's a skill shift worth making. The engineers who are most effective with LFG aren't the ones who micromanage every agent output — they're the ones who've learned to write crisp requirements and trust the system to execute against them.
