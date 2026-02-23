---
title: "Why Every AI Code Action Runs in an Isolated Sandbox"
date: 2026-02-18
excerpt: "LFG runs every ticket in its own Firecracker microVM. The AI can be aggressive and experimental — if something breaks, it breaks in the sandbox. Your codebase stays clean."
slug: sandboxed-code-execution
---

# Why Every AI Code Action Runs in an Isolated Sandbox

The most common objection to letting AI write and run code autonomously is also the most reasonable one: what if it breaks something?

It's a fair concern. AI systems make mistakes. They write code that has bugs. They sometimes misread requirements and implement the wrong thing entirely. And running arbitrary code — even well-intentioned code — against a real environment can cause real damage.

Most AI coding tools handle this by not running code at all. They generate code and hand it to you to run. You're the execution environment, and you're responsible for what happens when you run it.

LFG takes a different approach. Every ticket that involves code execution runs in a dedicated, isolated sandbox. The AI writes code, runs it, iterates on it, and tests it — entirely inside an environment that has no access to your production systems, your database, or your codebase's main branch.

---

## The Sandbox Stack

Each LFG execution environment is a Firecracker microVM — the same hypervisor technology that powers AWS Lambda. VMs boot in under 300ms from a pre-warmed pool, so there's essentially no wait time between ticket creation and execution start.

Workspaces inside VMs persist via JuiceFS + OverlayFS:

- **JuiceFS** backs workspace data to S3, giving you durability across sessions
- **OverlayFS** layers a local disk write layer on top for speed — writes hit local disk first, then sync to S3 on completion
- Each workspace is named and scoped to its ticket: `{ticket_id}-{uuid}`

When a ticket's agent needs to install a dependency, run a build, start a dev server, or execute a test suite — all of that happens inside this isolated environment. Nothing touches the host.

---

## What Isolation Actually Buys You

**Fearless experimentation.** When the AI is trying five different approaches to a tricky problem, it can actually run all five — not just generate them. It can install a library, see if it works, uninstall it, and try another. The cost of a failed experiment is zero because there's nothing to undo.

**No dependency pollution.** npm packages installed in a sandbox don't appear in your repo's package.json unless the ticket explicitly updates it. `node_modules` directories don't accumulate in your working tree. Every ticket starts from a known state.

**Safe refactoring.** If a ticket is implementing a major refactor, the entire thing runs and tests in the sandbox before it's ever proposed for merge. You see working (or explicitly failing) code, not a diff you have to mentally simulate.

**Parallel execution.** Multiple tickets can run simultaneously because each has its own isolated environment. There's no conflict between ticket A installing one version of a library while ticket B needs a different version.

---

## Workspace Persistence Across Runs

One of the harder problems in sandbox design is persistence: how do you let subsequent runs build on previous work without letting the sandbox sprawl into a long-lived, messy state?

LFG workspaces persist file system state across runs for the same ticket or project context. If ticket A installed dependencies, ticket B (in the same project) doesn't reinstall them from scratch. If a previous run wrote intermediate build artifacts, they're available.

But this persistence is scoped and versioned. It's not "here's a VM that's been running for a week and has accumulated unknown state." It's a clean workspace that specifically contains the files produced by previous runs, nothing else.

The warm VM cache goes a step further: for iterative development workflows — running `mags run -w myproject 'npm test'` in quick succession — the workspace stays mounted between runs. First run takes ~4 seconds. Subsequent runs within 5 minutes take ~100ms. You get the speed of a persistent local environment with the isolation guarantees of a fresh VM.

---

## How Review Intersects with the Sandbox

When a ticket completes, what you're reviewing isn't just a diff. You're reviewing:

- The code changes the agent produced
- The test results from the sandbox run
- Any logs or output from the execution
- Whether the acceptance criteria were met

The sandbox run isn't just for the AI's benefit. It's evidence. You're not being asked to mentally simulate whether the code would work — you're looking at whether it actually did.

This changes the quality bar for what counts as "done." A ticket isn't complete when the code looks right. It's complete when the code ran correctly against the acceptance criteria in an isolated environment.

---

## Production Environments

For production workloads, LFG uses Kubernetes pod orchestration with namespace isolation instead of Firecracker VMs. The principles are the same — isolated execution, resource limits, automatic cleanup — but on infrastructure that scales horizontally.

The agent that runs your ticket doesn't know or care whether it's running on a local Firecracker VM or a production Kubernetes pod. The abstraction is clean. The execution model is identical.

---

## The Practical Upshot

If you've worked in an environment where AI code generation was gated behind "never run anything automatically," the sandbox model feels different. You're not signing off on every command before it executes. The AI can move quickly, try things, fail, recover, and arrive at a working solution — without you watching each step.

Your job is to review the outcome, not monitor the process. That's a better use of your time.
