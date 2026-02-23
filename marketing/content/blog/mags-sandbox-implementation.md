---
title: Implementing Mags Sandbox environment on Baremetal machines
date: 2026-02-22
excerpt: "We've been building Mags, a sandbox platform for AI agents. Each sandbox is a Firecracker microVM that boots in ~300ms from a pre-warmed pool. Workspaces persist via JuiceFS + OverlayFS — writes go to local disk for speed, then sync to S3 on completion. Our newest trick: instead of tearing down the VM after a job, we park it with the workspace still mounted. If the same workspace runs again within 5 minutes, we skip the entire mount sequence and go from ~4s to ~100ms. Two 64GB bare-metal agents give us ~100 concurrent VMs."
---

# How We Built Mags: Sub-Second Cloud Sandboxes with Firecracker, JuiceFS, and a Warm VM Cache

Mags is a sandbox platform that gives AI agents and developers isolated cloud VMs that boot in ~300ms, persist files automatically, and sleep when idle. Under the hood it's a distributed system with an orchestrator, two agent servers, a reverse proxy, and a workspace layer built on JuiceFS + OverlayFS.

This post walks through the architecture — how we route jobs, boot VMs, persist workspaces, and our newest optimization: a warm VM cache that makes repeated workspace runs nearly instant.

---

## The 10,000-Foot View

```
                           ┌──────────────────────────────────────┐
                           │           User / AI Agent            │
                           │   (CLI, Python SDK, Node.js SDK)     │
                           └───────────────┬──────────────────────┘
                                           │
                              HTTPS REST API (port 9000)
                              SSH proxy   (port 20000+)
                                           │
                           ┌───────────────▼──────────────────────┐
                           │         ORCHESTRATOR SERVER          │
                           │                                      │
                           │  ┌──────────┐  ┌──────────────────┐  │
                           │  │ REST API │  │  SSH Proxy Mgr   │  │
                           │  │ Gateway  │  │  (sleep/wake)    │  │
                           │  └────┬─────┘  └───────┬──────────┘  │
                           │       │                │             │
                           │  ┌────▼────────────────▼──────────┐  │
                           │  │      Job Scheduler             │  │
                           │  │  (affinity + least-loaded)     │  │
                           │  └────┬───────────────────┬───────┘  │
                           │       │                   │          │
                           │  ┌────▼─────┐       ┌────▼─────┐    │
                           │  │PostgreSQL│       │  gRPC    │    │
                           │  │  (jobs,  │       │  Server  │    │
                           │  │  agents) │       │          │    │
                           │  └──────────┘       └──┬───┬───┘    │
                           └────────────────────────┼───┼────────┘
                                          gRPC      │   │     gRPC
                                   ┌────────────────┘   └──────────────┐
                                   │                                   │
                    ┌──────────────▼───────────────┐    ┌──────────────▼───────────────┐
                    │        AGENT SERVER 1        │    │        AGENT SERVER 2        │
                    │                              │    │                              │
                    │  ┌────────────────────────┐  │    │  ┌────────────────────────┐  │
                    │  │     HTTP Proxy         │  │    │  │     HTTP Proxy         │  │
                    │  │  *.apps.magpiecloud.com│  │    │  │  *.apps.magpiecloud.com│  │
                    │  └────────────────────────┘  │    │  └────────────────────────┘  │
                    │                              │    │                              │
                    │  ┌────────────────────────┐  │    │  ┌────────────────────────┐  │
                    │  │     Mags Executor      │  │    │  │     Mags Executor      │  │
                    │  │  (SSH, mount, execute) │  │    │  │  (SSH, mount, execute) │  │
                    │  └────────────────────────┘  │    │  └────────────────────────┘  │
                    │                              │    │                              │
                    │  ┌────────────────────────┐  │    │  ┌────────────────────────┐  │
                    │  │       VM Pool          │  │    │  │       VM Pool          │  │
                    │  │                        │  │    │  │                        │  │
                    │  │  idle: [VM][VM][VM]    │  │    │  │  idle: [VM][VM][VM]    │  │
                    │  │  busy: [VM]            │  │    │  │  busy: [VM][VM]        │  │
                    │  │  warm: [VM:ws-abc]     │  │    │  │  warm: []              │  │
                    │  └───────────┬────────────┘  │    │  └───────────┬────────────┘  │
                    │              │                │    │              │                │
                    │    ┌─────────▼─────────┐     │    │    ┌─────────▼─────────┐     │
                    │    │  Linux bridge     │     │    │    │  Linux bridge     │     │
                    │    │  (private subnet) │     │    │    │  (private subnet) │     │
                    │    └──┬──┬──┬──┬───────┘     │    │    └──┬──┬──┬──┬───────┘     │
                    │    tap│tap│tap│tap            │    │    tap│tap│tap│tap            │
                    │    ┌──▼──▼──▼──▼───────┐     │    │    ┌──▼──▼──▼──▼───────┐     │
                    │    │   Firecracker VMs  │     │    │    │   Firecracker VMs  │     │
                    │    │  (Alpine Linux)    │     │    │    │  (Alpine Linux)    │     │
                    │    └───────────────────┘     │    │    └───────────────────┘     │
                    └──────────────────────────────┘    └──────────────────────────────┘
                                   │                                   │
                                   └──────────┬────────────────────────┘
                                              │
                                   ┌──────────▼──────────┐
                                   │     AWS S3          │
                                   │  (workspace data    │
                                   │   + JuiceFS meta)   │
                                   └─────────────────────┘
```

---

## Part 1: The Orchestrator

The orchestrator is the brain. It runs on a dedicated server and exposes a REST API and a gRPC server. It doesn't run any VMs itself — it routes work to agents.

When a user runs `mags run -w myproject 'npm test'`, here's what happens:

1. **REST API** receives the job, validates the workspace name, creates a database record
2. **Job scheduler** picks the best agent — either by **workspace affinity** (route to the agent that last ran this workspace, because it probably has a warm cached VM) or by **least-loaded** selection
3. **gRPC call** sends the job to the selected agent
4. Agent executes, returns results, orchestrator updates the database

The orchestrator also runs an **SSH proxy manager**. When a persistent VM goes to sleep, the orchestrator keeps a TCP port listening. If someone SSH's into it, the proxy wakes the VM on an agent and forwards the connection transparently. The user doesn't know the VM was sleeping.

---

## Part 2: Agent Servers and the VM Pool

Each agent is a bare-metal server running Firecracker — Amazon's microVM hypervisor (the same one powering AWS Lambda). We currently run two agents.

### Pre-Warmed VM Pool

Cold-booting a Firecracker VM takes ~2 seconds. That's fast for a VM, but we wanted sub-second. So we pre-warm them.

Each agent maintains a pool of already-booted VMs sitting idle:

```
Pool state at any moment:
  idle:  [VM-a1] [VM-a2] [VM-a3]     ← booted, SSH-ready, waiting
  busy:  [VM-b1]                      ← running a job right now
  warm:  [VM-c1:ws-myproject]         ← workspace still mounted, 5-min TTL
```

When a job arrives, the executor grabs an idle VM in <100ms. No boot wait. The pool replenishes in the background.

### How Many VMs Per Agent?

Each Firecracker VM runs with **2 vCPUs, 1GB RAM, and a 2GB rootfs disk** by default (configurable per deployment). The pool uses **capacity-based scaling** — instead of a hard cap, it monitors real-time CPU and memory utilization on the host. If either exceeds 90%, no new VMs are created.

The math is simple: **memory is the bottleneck**. Firecracker oversubscribes CPU (VMs share host cores via KVM time-slicing), so even a 4-core host can comfortably run 15+ VMs if the workloads are bursty. But each VM reserves its full 1GB of RAM from the host.

Our agent servers each have **64GB RAM**. At the 90% threshold that's ~57GB usable for VMs. With 1GB per VM, that's a theoretical max of **~57 concurrent VMs per agent**. In practice, the host OS, JuiceFS cache, and rootfs copies (2GB each in `/tmp`) eat into that — so **40-50 concurrent VMs per agent** is the realistic ceiling, giving us **80-100 across both agents**.

We keep a minimum of 3 idle VMs pre-warmed at all times so there's always instant capacity for incoming jobs.

The pool auto-scales in both directions: it creates VMs when idle count drops below the minimum, and destroys idle VMs that haven't been used in 5 minutes (as long as the minimum is maintained).

### Network: TAP Interfaces and a Bridge

Each VM gets its own TAP interface attached to a Linux bridge on a private subnet:

```
Host kernel
  └── bridge (private subnet)
        ├── tap-vm-a1 → VM gets internal IP via DHCP
        ├── tap-vm-a2 → VM gets internal IP via DHCP
        └── tap-vm-a3 → VM gets internal IP via DHCP
```

VMs get internal IPv4 addresses. For external URL access, we can assign IPv6 via EUI-64 from the VM's MAC address and set up proxy NDP on the host. But most access goes through the HTTP reverse proxy.

### HTTP Reverse Proxy

Each agent runs an HTTP proxy. When a user enables URL access for their VM, the proxy registers a subdomain-to-VM mapping:

```
<unique-id>.apps.magpiecloud.com → internal-vm-ip:8080
```

Cloudflare has a wildcard DNS record pointing `*.apps.magpiecloud.com` to the agent. The proxy reads the `Host` header, extracts the subdomain, and reverse-proxies to the VM's internal IP. WebSocket connections (for browser automation via CDP) are supported too.

---

## Part 3: Workspace Persistence with JuiceFS + OverlayFS

This is the most interesting part of the stack. The problem: VMs are ephemeral (destroyed after each job), but workspaces need to persist. Users run `mags run -w myproject 'npm install'` and expect `node_modules` to be there on the next run.

### The Mount Stack

```
┌──────────────────────────────────────────┐
│           /overlay (merged view)          │  ← chroot target for scripts
├──────────────────────────────────────────┤
│  upper: /tmp/overlay-upper (local disk)  │  ← fast writes go here
│  lower: / (rootfs)                       │  ← base Alpine Linux
├──────────────────────────────────────────┤
│           /jfs (JuiceFS mount)           │  ← S3-backed FUSE filesystem
│           SQLite metadata (local)        │
│           Data chunks → S3               │
└──────────────────────────────────────────┘
```

Here's the flow:

1. **Download metadata**: Fetch the SQLite metadata file from S3 via a pre-signed URL
2. **Mount JuiceFS**: Local SQLite for metadata (sub-millisecond ops), S3 for data chunks
3. **Restore overlay upper**: Copy saved changes from JuiceFS into the local overlay upper directory
4. **Mount OverlayFS**: Merge the base rootfs with the restored changes. The user sees a complete filesystem where their previous files are present
5. **Execute script** inside a chroot of `/overlay`
6. **On completion**: Copy overlay changes back to JuiceFS, unmount JuiceFS (flushes metadata), upload metadata to S3

**Why OverlayFS on top of JuiceFS?** Because OverlayFS can't use a FUSE filesystem as its upper layer (writes would be too slow). So we write to local disk and sync to JuiceFS on completion. This gives us the speed of local disk with the durability of S3.

### A Hard Lesson: JuiceFS Metadata

JuiceFS keeps metadata in memory and writes to the SQLite file lazily. If you try to back up the SQLite file while JuiceFS is mounted, you get stale data. You **must** unmount JuiceFS to flush metadata to disk, then upload it to S3.

We also learned that `cp -a` (copy all) is dangerous — it overwrites files with new S3 chunk IDs, breaking any child VMs that have older metadata pointing to the old chunks. We switched to `cp -au` (update only: skip files that are newer in the destination).

---

## Part 4: The Warm VM Cache

This is our newest optimization. The problem: workspace mounting takes ~2.5 seconds (download metadata, format/mount JuiceFS, setup OverlayFS). If you're iterating — running `mags run -w myproject 'npm test'` every 30 seconds — that overhead is painful.

### How It Works

Instead of unmounting and releasing the VM after a job completes, we **park it**:

```
Job completes on VM-a1 (workspace: myproject)
    │
    ├── Close SSH (don't unmount!)
    ├── SyncNow() — upload metadata to S3 (workspace stays mounted)
    └── ParkWarm(VM-a1, "myproject") — move to warm cache
        │
        └── warm cache: { "myproject": VM-a1 }
            TTL: 5 minutes
```

When the next job arrives for the same workspace:

```
New job for workspace "myproject"
    │
    ├── AcquireWarm("myproject") → VM-a1 (hit!)
    ├── Skip entire mount sequence
    ├── Execute script immediately
    └── ~100ms total (vs ~2.5s cold)
```

### Orchestrator-Side Affinity

The warm cache only works if consecutive jobs for the same workspace land on the same agent. So we added **workspace affinity routing**:

```go
// In the job scheduler:
if job.WorkspaceID != "" {
    // Find the agent that last completed a job for this workspace
    agent = findAgentWithWorkspaceAffinity(job.UserID, job.WorkspaceID)
}
if agent == nil {
    agent = findAvailableAgentWithPool() // fallback: least loaded
}
```

It queries the most recent completed job for the same workspace and routes to that agent. If the agent is unhealthy, it falls back to least-loaded.

### Cache Expiry

A background loop runs every 30 seconds and evicts warm VMs older than 5 minutes:

1. Check if the VM process is still alive (signal 0)
2. If dead, destroy and replace
3. If expired, call the expiry callback: SSH in, unmount workspace, sync to S3, release VM back to the idle pool

The VM isn't destroyed — it goes back to the idle pool for reuse by other jobs. Only the workspace mount is cleaned up.

### Performance Impact

| Scenario | Before | After |
|----------|--------|-------|
| First run (cold) | ~4s | ~4s |
| Second run within 5 min | ~4s | **~0.1s** |
| Ephemeral run (no workspace) | ~0.1s | ~0.1s |

For iterative development workflows, this is a 40x improvement.

---

## Part 5: Sleep/Wake for Persistent VMs

Persistent VMs (`mags new myvm`) stay alive for SSH access and long-running processes. But idle VMs waste resources. So we put them to sleep.

The orchestrator checks every 60 seconds: if a persistent VM has been idle for 10 minutes, it:

1. Syncs the workspace to S3
2. Terminates the VM on the agent
3. Keeps the SSH proxy port open on the orchestrator

When someone SSH's into the sleeping VM:

1. The orchestrator's sleeping proxy accepts the TCP connection
2. Triggers the wake callback
3. A new VM is provisioned on an agent, workspace is mounted from S3
4. The SSH connection is forwarded to the new VM

The user sees a ~6 second pause, then they're in. Their files are exactly as they left them.

---

## What's Next

- **Warm cache for persistent VMs**: Currently warm cache only helps ephemeral workspace runs. We could keep persistent VMs warm across sleep/wake cycles too.
- **Multi-region agents**: Right now both agents are in the same datacenter. Adding agents in other regions would reduce latency for users worldwide.
- **Snapshot-based workspace restore**: Instead of JuiceFS mount, snapshot the entire rootfs to S3 and restore via `dd`. Could be faster for large workspaces.

---

If you want to try Mags: `npm install -g @magpiecloud/mags` and you're running sandboxes in under a minute. Check out [magpiecloud.com](https://magpiecloud.com) for the full docs.
