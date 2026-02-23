---
title: "Projects, Tickets, and AI: A New Model for Engineering Work"
date: 2026-02-21
excerpt: "LFG replaces the traditional ticket tracker with an AI-native project model — where tickets aren't just tracked, they're executed by specialist agents against explicit acceptance criteria."
slug: project-management-ai-agents
---

# Projects, Tickets, and AI: A New Model for Engineering Work

Traditional project management tools are great at tracking what needs to happen. They're silent on the question of who does it.

That wasn't a problem when the answer was always "a human developer." But once agents are doing real work — writing code, running tests, generating documents — the gap between "this is in the backlog" and "this is being worked on" collapses. Tickets don't just get planned. They get executed.

LFG's project model is built around this. It's not a task tracker with AI attached. It's an AI execution system with project structure around it.

---

## Projects as Execution Contexts

Every project in LFG has a few key things:

- **Conversations**: Real-time chat with AI agents, saved and searchable
- **Tickets**: Discrete units of work, each with a defined scope and status
- **Sandboxes**: Isolated execution environments tied to specific tickets
- **Tech stack config**: Framework-specific defaults (Next.js, Django, Rails, etc.) that agents use when generating code
- **Git worktrees**: Separate branches for parallel work that doesn't interfere with the main branch

The project is a shared context. Agents working on different tickets within the same project have access to the same codebase, the same conventions, the same history of decisions. This prevents the fragmentation you get when multiple AI sessions don't know about each other.

---

## Ticket Lifecycle

A ticket in LFG has a lifecycle that maps to how work actually moves:

```
queued → ready → running → completed
                        ↘ failed
                        ↘ blocked
```

**Queued**: The ticket exists in the plan but its dependencies haven't completed yet.

**Ready**: Dependencies are done; the ticket can be picked up by an agent.

**Running**: An agent is actively working on this ticket in a sandbox.

**Completed**: Work is done, output is available for review.

**Failed**: The agent encountered an error it couldn't recover from — surfaced for human review.

**Blocked**: The agent needs input or a decision that can't be automated — human attention required.

The `blocked` status is particularly important. It's the system's way of saying "I need you" without interrupting everything else. Other tickets keep running. The blocked ticket waits. You address it when you have a moment, and the pipeline continues.

---

## Ticket Types Map to Agent Specializations

Not all tickets are the same kind of work, and LFG doesn't pretend they are. Ticket types determine which agent handles the work and what tools are available:

- **Research**: Gather information, summarize findings, provide recommendations — no code execution
- **PRD Creation**: Structured product requirements with user stories and acceptance criteria
- **Implementation**: Code writing, running, and testing in a sandbox
- **Bug Fix**: Reproduce, diagnose, fix, verify a specific issue
- **Testing**: Write and run a test suite against existing code
- **Code Review**: Analyze a diff, surface issues, suggest improvements
- **Documentation**: Generate docs, update READMEs, write changelogs

Each type has a default set of acceptance criteria patterns, a default agent assignment, and a default tool set. You can customize all of this — but the defaults mean most tickets are correctly configured without manual setup.

---

## Git Worktrees for Parallel Development

When multiple tickets are running simultaneously, they need isolation at the code level, not just at the VM level.

LFG uses Git worktrees to give each parallel workstream its own branch. Ticket A working on the authentication system doesn't see Ticket B's in-progress changes to the routing layer. When both complete, the merge is a normal code review, not an archaeology expedition to untangle concurrent changes.

The worktree approach means you can run 5 tickets simultaneously and end up with 5 clean, reviewable branches — each representing exactly the changes for that ticket, nothing else.

---

## Project-Level Tech Stack Awareness

One of the less obvious features of LFG's project model is tech stack configuration. When you set up a project, you specify the framework and runtime (Next.js, Astro, Django, FastAPI, Go, Rust, Rails).

This configuration does more than label the project. It populates default values that agents use throughout execution:

- What install command to run (`npm install`, `pip install`, `bundle install`)
- How to start the dev server, and on what port
- What file patterns to expect and conventions to follow
- What test runner to use

An agent working on a Django project and an agent working on a Next.js project behave differently out of the box — because they're drawing on different default contexts. You don't have to explain the framework in every ticket.

---

## Linear Integration

For teams that use Linear as their source of truth, LFG syncs ticket completions back to Linear issues automatically. When a ticket moves to `completed`, the corresponding Linear issue updates.

This means the AI-execution layer doesn't require a separate workflow. You manage priorities in Linear, LFG executes the work, and the status flows back. The humans reviewing work see the same tools they've always used; the AI execution is largely invisible to the broader organizational process.

---

## The Relationship Between Chat and Tickets

LFG's chat and ticket systems are designed to be complementary, not competing.

Chat is for direction: "let's add a notification system to this project" — the kind of open-ended, conversational planning that benefits from back-and-forth.

Tickets are for execution: once the direction is clear, the orchestrator generates a plan, the plan becomes tickets, and the tickets get executed.

You can move fluidly between modes. A conversation can generate tickets. A completed ticket can be the starting point for a new conversation. The project history ties it all together — so the context from the planning conversation is available to the agent executing the implementation ticket, and the output of the implementation is available when you return to the conversation to review it.

---

## What This Replaces

The LFG project model effectively replaces:

- A Jira board (for ticket tracking)
- A GitHub Codespace or local dev environment (for code execution)
- A single-agent AI chat (for direct AI interaction)
- A PR review queue (with the built-in sandbox verification and review checkpoints)

Not because any of those tools are bad — but because combining them into a single AI-native execution environment eliminates the coordination overhead between them. The ticket that's in the backlog, being worked on, and being reviewed is the same ticket throughout its lifecycle. No handoffs. No copy-paste between tools. No "update the ticket status after you merge."

The project manages itself. You direct it.
