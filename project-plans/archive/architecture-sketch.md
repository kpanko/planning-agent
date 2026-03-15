# AI Todoist Assistant: Architecture Sketch

## What We're Building

A daily conversational assistant that knows your tasks, calendar, and history well enough that you can say "what should I do?" and get a useful, contextualized answer — without having to explain your life from scratch each time.

---

## System Overview

```
┌─────────────────────────────────────────────────────┐
│                   YOU (conversation)                 │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Conversation Interface                  │
│         (chat UI, CLI, or messaging app)             │
└──────────┬──────────────────────────────┬───────────┘
           │ start of conversation        │ end of conversation
           ▼                              ▼
┌─────────────────────┐       ┌───────────────────────┐
│  Context Assembly   │       │  Memory Extraction    │
│  (builds system     │       │  (pulls durable info  │
│   prompt)           │       │   from transcript)    │
└──────┬──────────────┘       └──────────┬────────────┘
       │ reads from                      │ writes to
       ▼                                 ▼
┌─────────────────────────────────────────────────────┐
│              Persistent Store                        │
│              (~/.todoist-assistant/)                        │
│                                                     │
│  ┌──────────────┐ ┌───────────────┐ ┌────────────┐ │
│  │ values.md    │ │ memories.json │ │ convos/    │ │
│  └──────────────┘ └───────────────┘ └────────────┘ │
└──────┬──────────────────────────────────────────────┘
       │ also reads from
       ▼
┌─────────────────────────────────────────────────────┐
│              External Data Sources                   │
│                                                     │
│  ┌───────────┐  ┌────────────┐  ┌───────────────┐  │
│  │  Todoist   │  │  Calendar  │  │  Weather API  │  │
│  │   (API)    │  │   (API)    │  │  (optional)   │  │
│  └───────────┘  └────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## The Two Key Operations

### 1. Context Assembly (start of conversation)

Every time you start a conversation, the system builds a system prompt from these sources:

#### A. Values & Priorities (system-maintained, not user-written)

The user never writes or maintains this document. The system builds it through conversation and keeps it updated over time.

**Initial creation: Onboarding conversation**

The very first time the system runs, there's no Todoist data, no calendar, no context. Just a conversation designed to draw out what matters. The system prompt for this conversation is different from daily use:

```
You are helping a new user set up a daily guidance system.
Your goal is to understand what matters to them — not to plan
their week or organize their tasks.

Have a natural conversation. Ask about:
- What's weighing on them right now
- What would make this week/month feel like a success
- What parts of life feel neglected
- What they keep meaning to do but don't start
- What they care about vs. what they feel obligated to do

Don't ask all of these. Follow the conversation naturally.
Spend about 10-15 minutes. When you have a reasonable picture,
summarize what you've heard and ask if it sounds right.

Keep it warm and low-pressure. This isn't an intake form.
```

After this conversation, the memory extraction step generates the initial values doc:

```
Example (system-generated):
- Family is a top priority. Kids' activities and quality time matter.
  Daughter has a school recital coming up in March.
- Finances cause background stress. Taxes are due April 15, currently
  blocked on a missing W-2.
- Health: wants to exercise 3x/week but hasn't been consistent.
  No specific plan, just general intention.
- Career: interested in learning [topic] but described it as
  "not urgent" — more of a curiosity than a commitment.
- Home maintenance piles up and creates stress. Furnace needs
  attention. General clutter bothers them.
- Spanish learning is on the list but may be more obligation
  than genuine interest — watch for deferral patterns.
```

**Ongoing maintenance: Every daily conversation refines it**

The memory extraction step (described below) doesn't just extract facts — it also updates the values doc when warranted. Examples:

- User says "I really need to start prioritizing my health" → health moves up in emphasis
- User consistently defers Spanish and eventually says "honestly I don't care about this" → Spanish is removed
- User mentions a new project they're excited about → it gets added
- User's kid finishes the recital → that specific detail is resolved, but "family is a priority" remains

**The user can view it if they want** ("show me what you think my priorities are") and correct it ("that's not right, actually X matters more than Y"). But they never have to. It's an internal system artifact, not a user deliverable.

**Staleness protection:** If the values doc hasn't been meaningfully updated in 30+ days, the system can ask a lightweight check-in question during a daily conversation: "It's been a while since we talked about what matters most to you. Has anything shifted?"

#### B. Todoist Snapshot
Pulled fresh via API at conversation start. Not a raw dump — a structured summary.

**What to include:**
- Tasks due today and overdue (with project and any notes)
- Tasks due this week (grouped by project)
- Recently completed tasks (last 3 days — shows momentum)
- Tasks rescheduled more than twice (shows avoidance/stuckness)
- "Someday/Maybe" items mentioned only as background context

**What to exclude:**
- Recurring tasks that are routine and handled (e.g., "take vitamins")
- Completed tasks older than 3 days
- Full project hierarchies — just project names as labels

**Format sent to Claude:**

```
## Tasks Due Today
- File Q4 estimated taxes (project: Finances, overdue by 3 days)
- Pick up dry cleaning (project: Errands)
- Review daughter's permission slip (project: Family)

## This Week
- Schedule furnace inspection (project: Home, rescheduled 4 times)
- Finish slide deck for Wednesday meeting (project: Work)
- Return Amazon package (project: Errands)

## Recently Completed (last 3 days)
- Paid electric bill
- Cleaned kitchen counters
- Sent birthday card to Mom

## Repeatedly Deferred
- Schedule furnace inspection (4 reschedules over 2 weeks)
- Start Spanish lesson on Duolingo (rescheduled 6 times)
```

**Implementation:** A Python function that calls Todoist's REST API, categorizes tasks by the rules above, and formats them as text. This is rule-based, not AI — it should be fast and deterministic.

#### C. Calendar Context
Pulled fresh via API (Google Calendar or similar).

**What to include:**
- Today's events with times (gives sense of available windows)
- Tomorrow's early events (affects tonight's suggestions)
- General pattern note if derivable ("3 meetings today — heavier than usual")

**Format:**

```
## Today (Tuesday, Feb 16)
- 9:00–10:00 Team standup
- 12:00–1:00 Lunch with Sarah
- 3:00–3:30 Dentist appointment
- Evening: open

## Tomorrow
- 8:00 AM early meeting — may want to prep tonight
```

#### D. Memories
Retrieved from persistent store. These are things learned from prior conversations.

**Format:**

```
## Active Memories
- Waiting on W-2 from employer before finishing taxes (mentioned Feb 12)
- Furnace has been making a rattling noise — wants to get it checked
  before scheduling inspection (mentioned Feb 14)
- Daughter's school recital is March 8, needs to arrange time off
- Prefers to batch errands on Saturday mornings
- Low energy on days after poor sleep — mentioned this twice
- Has been thinking about volunteering at the library but hasn't decided

## Expired/Resolved
(not sent to Claude, but kept in DB for reference)
```

#### E. Recent Interaction Summary
A brief note about the last 1–2 conversations so Claude has continuity.

```
## Last Conversation (Feb 15, evening)
- Talked about the upcoming week
- Decided to focus on taxes once W-2 arrives
- Completed: sorted mail, identified 3 things to shred
- Deferred: furnace inspection ("want to investigate the noise first")
- Mood: seemed tired but willing to do small things
```

#### F. Current Context
Automatically derived, no API needed.

```
## Right Now
- Day: Tuesday, February 16, 2026
- Time: 7:15 PM
- Day type: workday (based on calendar)
```

---

### 2. Memory Extraction (end of conversation)

After each conversation, a second Claude call processes the transcript and extracts memories.

**Prompt structure:**

```
Here is today's conversation transcript:
[full transcript]

Here are the existing memories:
[current memory list]

Here is the current values/priorities summary:
[current values doc]

Please extract:

1. NEW FACTS: Concrete things to remember (blockers, dates,
   commitments, preferences discovered).
   
2. UPDATED FACTS: Existing memories that should be revised
   based on new information.

3. RESOLVED: Existing memories that are no longer relevant
   (task was completed, blocker was removed, date passed).

4. OPEN THREADS: Things the user mentioned wanting to think
   about or come back to, but that aren't Todoist tasks.

5. OBSERVATIONS: Patterns you noticed about energy, preferences,
   or behavior. Mark these as low-confidence until confirmed
   by multiple conversations.

6. VALUES DOC UPDATES: Any changes to the user's values or
   priorities that emerged in this conversation. Include
   additions, removals, and emphasis shifts. Return null
   if no changes are warranted — don't update just because
   a topic was discussed.

Return as structured JSON.
```

**Output example:**

```json
{
  "new_facts": [
    {
      "content": "W-2 arrived in the mail today",
      "source_date": "2026-02-16",
      "expiry": null
    },
    {
      "content": "Wants to do taxes this weekend now that W-2 is here",
      "source_date": "2026-02-16",
      "expiry": "2026-02-23"
    }
  ],
  "updated_facts": [
    {
      "original": "Waiting on W-2 from employer before finishing taxes",
      "updated": "W-2 received Feb 16. Taxes no longer blocked.",
      "action": "resolve_and_replace"
    }
  ],
  "resolved": [
    "Waiting on W-2 from employer before finishing taxes"
  ],
  "open_threads": [
    "Considering whether to sign daughter up for summer soccer — needs to check schedule conflicts"
  ],
  "observations": [
    {
      "content": "Had more energy tonight than expected after a meeting-heavy day — might not always need to assume low energy after meetings",
      "confidence": "low",
      "confirming_count": 1
    }
  ],
  "values_doc_updates": {
    "additions": [
      "Mentioned wanting to volunteer at the library — new interest, low commitment so far"
    ],
    "removals": [],
    "emphasis_shifts": [
      "Health came up unprompted twice — may be increasing in priority"
    ],
    "full_rewrite_needed": false
  }
}
```

**Memory management rules:**
- Facts with expiry dates auto-expire
- Observations need 3+ confirming instances before being treated as reliable
- Resolved items are archived, not deleted (useful for future reference)
- Total active memory list should stay under ~50 items; if it grows beyond that, a periodic consolidation pass merges or prunes

---

## The System Prompt

Everything above gets assembled into a single system prompt. Here's the skeleton:

```
You are a daily guidance assistant for [user]. Your job is to help
them decide what to do right now based on what's on their plate,
what matters to them, and how they seem to be doing today.

## How to behave
- Suggest one thing at a time. Never present a list of options.
- Be concrete. "Open the taxes folder and find the W-2" not
  "work on taxes."
- Keep it brief. This is a conversation, not a report.
- If they say "not that," suggest something else or ask what's
  getting in the way. One question max.
- If they're done, let them be done. No guilt, no "are you sure?"
- Never use moral language. No "you should" or "you've been
  putting this off."
- Explain briefly *why* you're suggesting something when it's
  not obvious.
- If you notice a mismatch between stated values and behavior,
  you can gently raise it, but don't push.
- Short responses. A sentence or two unless they ask for more.

## Their values and priorities
[values doc contents]

## What's on their plate
[Todoist snapshot]

## Today's schedule
[calendar context]

## Things to remember from past conversations
[active memories]

## Last conversation
[recent interaction summary]

## Right now
[current context]
```

---

## Conversation Interface Options

In order of simplicity to build:

### Option 1: Script + Terminal (MVP)
A Python script you run from the command line. It assembles context, opens an interactive Claude conversation, and extracts memories when you type "done" or quit.

**Pros:** Fastest to build, no UI work, full control.
**Cons:** Must be at your computer, feels like a dev tool.

### Option 2: Simple Web App (local)
A basic web page served locally. Text input, chat display, "Start" button that assembles context behind the scenes.

**Pros:** Friendlier, could run on phone via local network.
**Cons:** More to build, still local-only.

### Option 3: Messaging Integration (Telegram, SMS, Slack)
The system lives in a messaging app you already use. You send a message, it responds.

**Pros:** Lowest friction — you're already in the app. Works on phone. Notifications possible for future ambient mode.
**Cons:** More integration work. Message length limits. Harder to do rich formatting.

**Recommendation:** Start with Option 1 to validate the core loop. Move to Option 3 once you know it's working, because the phone accessibility matters for real daily use.

---

## Data Storage (Flat Files)

Everything lives in a single directory. Human-readable, easy to debug, version-controllable with git if you want history.

```
~/.todoist-assistant/
  values.md                    # system-maintained values & priorities
  memories.json                # all memories with metadata
  conversations/
    2026-02-16.json            # one file per day
    2026-02-15.json
```

### values.md

Plain markdown. Passed directly to Claude as part of the system prompt. The system writes and updates this file — you read it only if you're curious.

```markdown
# Values & Priorities
*Last updated: 2026-02-16 (daily refinement)*

- Family is a top priority. Kids' activities and quality time matter.
  Daughter has a school recital March 8 — needs to arrange time off.
- Finances cause background stress. Taxes due April 15.
  W-2 received Feb 16, no longer blocked.
- Health: wants to exercise 3x/week but hasn't been consistent.
- Career: interested in learning [topic], not urgent.
- Home maintenance piles up and creates stress. Furnace needs attention.
```

### memories.json

A single JSON array. Loaded entirely into memory, filtered in Python. At 50 items this is trivially small.

```json
[
  {
    "id": "m_001",
    "content": "Daughter's school recital is March 8, needs to arrange time off",
    "category": "fact",
    "confidence": "high",
    "confirming_count": 1,
    "source_date": "2026-02-12",
    "expiry_date": "2026-03-09",
    "resolved": false,
    "created_at": "2026-02-12T19:30:00"
  },
  {
    "id": "m_002",
    "content": "Prefers to batch errands on Saturday mornings",
    "category": "observation",
    "confidence": "medium",
    "confirming_count": 3,
    "source_date": "2026-02-05",
    "expiry_date": null,
    "resolved": false,
    "created_at": "2026-02-05T20:15:00"
  },
  {
    "id": "m_003",
    "content": "Considering whether to volunteer at the library",
    "category": "open_thread",
    "confidence": "high",
    "confirming_count": 1,
    "source_date": "2026-02-15",
    "expiry_date": null,
    "resolved": false,
    "created_at": "2026-02-15T21:00:00"
  }
]
```

### conversations/2026-02-16.json

One file per day. Contains the transcript and a summary for use in future context.

```json
{
  "date": "2026-02-16",
  "started_at": "2026-02-16T19:00:00",
  "ended_at": "2026-02-16T19:25:00",
  "summary": "Talked about the upcoming week. W-2 arrived, planning to do taxes this weekend. Completed: sorted mail. Deferred: furnace inspection (wants to investigate noise first). Seemed tired but willing to do small things.",
  "interactions": [
    {
      "suggestion": "Sort through the mail on the counter and separate anything that needs action",
      "outcome": "completed"
    },
    {
      "suggestion": "Call to schedule the furnace inspection",
      "outcome": "deferred",
      "deferral_reason": "Wants to investigate the rattling noise before calling — might affect what to tell them"
    }
  ],
  "transcript": "[full conversation text — kept for memory re-extraction if needed]"
}
```

### Why flat files instead of a database

- **Everything is human-readable.** When the system makes a weird suggestion, open `memories.json` and see exactly what it's working from.
- **Easy to fix by hand.** Wrong memory? Edit the JSON. Values doc drifted? Open it and correct it.
- **Git-friendly.** If you want a history of how your values evolved or what the system remembered over time, `git init` and commit after each conversation.
- **No overhead.** No database server, no ORM, no migrations. Just `json.load()` and `json.dump()`.
- **When to upgrade to SQLite:** If you find yourself writing complex Python to filter and sort memories, or if conversation history grows large enough to search across months of transcripts. That's a future problem — you'll know because the code will feel painful.

---

## Build Order

### Phase 1: Prove the conversation works (days)
1. Build the Todoist snapshot function (Python + Todoist API)
2. Build a minimal context assembler that combines Todoist + current time into a system prompt
3. Run the onboarding conversation to generate the initial values doc
4. Run it as a terminal script that starts a Claude conversation with context
5. Use it for a few days. See if the suggestions are good enough to be useful.

**Skip in Phase 1:** Calendar integration, full memory extraction, conversation logging. The onboarding conversation generates a values doc, but daily memory updates come in Phase 2. The goal is to test whether a context-rich conversation is actually helpful.

### Phase 2: Add memory (1–2 weeks)
6. Add conversation logging (save transcript + summary to daily JSON file)
7. Build memory extraction (post-conversation Claude call)
8. Include memories in context assembly
9. Add the recent interaction summary

**Now test:** Does the system feel like it knows you? Do memories carry forward usefully? Is the memory extraction producing garbage or gold?

### Phase 3: Add calendar and polish (1–2 weeks)
10. Calendar API integration
11. Refine the system prompt based on what's working and what isn't
12. Add memory management (expiry, consolidation, pruning)
13. Consider moving to a messaging interface for daily use

### Phase 4: Ambient mode and beyond (later)
14. Proactive check-ins at useful moments
15. Pattern inference from accumulated observations
16. Email integration (if still wanted)

---

## What This Doesn't Include (Yet)

- **Writing back to Todoist.** The system is read-only for now. If you complete a task through the conversation, you check it off in Todoist yourself. This avoids the completion detection problem entirely.
- **Ambient/proactive mode.** Start with you initiating. Add nudges later.
- **Email.** Tempting but a huge scope expansion. Park it.
- **Inference engine.** The "observations" in memory are a lightweight version. Full behavioral inference comes later, if ever.
- **Multi-device sync.** Flat files are local. Fine for one person on one machine. If you want phone + computer, you could sync the `~/.todoist-assistant/` directory with something like Syncthing or Dropbox, or switch to the messaging interface which is inherently device-independent.

---

## Key Risk: Is This Actually Better Than a Chat Thread?

The whole value proposition is that preloaded context makes the conversation dramatically more useful than a blank ChatGPT thread. If the Todoist snapshot and memories don't materially improve suggestion quality, this is overengineered.

**How to test:** After Phase 1, compare a context-loaded conversation with a blank one. Ask both "what should I do tonight?" and see which answer is more useful. If there's no clear difference, the context assembly needs work before building more.

---

## Rough Effort Estimates

| Phase | What | Time |
|-------|------|------|
| 1 | Values doc + Todoist integration + terminal script | A few evenings |
| 2 | Conversation logging + memory extraction + retrieval | ~1 week of evenings |
| 3 | Calendar + prompt refinement + memory management | ~1 week of evenings |
| 4 | Messaging interface migration | ~1 week of evenings |

Total to a usable daily system: roughly a month of evening/weekend work, with something testable after the first few days.
