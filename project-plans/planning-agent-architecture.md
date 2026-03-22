# AI Life Planner: Architecture

## What This Is

A personal planning agent that looks at everything you need to do, understands your constraints and habits, and schedules your weeks so you don't have to. It uses Todoist as both the task store and the schedule, Google Calendar as a read-only view of existing commitments, and Claude as the planning intelligence.

You talk to it. It plans for you. You approve, adjust, or push back.

---

## The Problem

You're good at capturing tasks (GTD intake works). You're less good at deciding when to do them. Traditional tools like Motion AI try to solve this but create a different problem: they make you do the planning work upfront (estimate durations, declare blockers, categorize everything) before they'll help you.

What you want:
- AI figures out when things should happen based on deadlines, your habits, your calendar, and common sense
- Fuzzy recurring tasks ("check spare tire roughly every 6 months") are handled naturally
- Seasonal and weather awareness (don't schedule outdoor tasks in January)
- The system respects that you're human — you sleep, you get tired, you have good days and bad days
- You review and approve a plan rather than building one from scratch
- Low cost, leverages tools you already use

## Scope

This system manages **personal tasks only**. Work tasks stay in their own tools (Microsoft calendar, OneNote, etc.). However, the system needs to understand your work schedule because it constrains when personal tasks can happen.

**Work schedule facts the system should know** (stored in memories, can change):
- Hybrid schedule: Mondays and Fridays at home, Tuesday–Thursday in the office
- ~40 hours/week blocked for work, but this mostly marks general availability, not continuous meetings
- At the office: access to printer
- At home: access to home-specific resources (tools, kitchen, yard, etc.)
- Work blocks are soft constraints — small personal tasks (phone calls, quick errands at lunch) can fit in gaps, but deep personal work should be scheduled outside work hours

**What this means for planning:**
- "Print the tax forms" → schedule on a Monday or Friday (home, has printer) or Tue–Thu (office printer). The system should know which printer is relevant.
- "Call to schedule furnace inspection" → could fit in a lunch break on any day
- "Deep clean the kitchen" → weekend or evening, not during work hours
- "Pick up dry cleaning" → lunch break or after work, depending on location relative to office/home

---

## Core Interactions

### 1. Weekly Planning Session (Sunday evening or Monday morning)

The main event. The agent looks at:
- All Todoist tasks (due this week, overdue, upcoming deadlines, fuzzy recurring)
- Your Google Calendar (existing commitments, available windows)
- Your preferences and patterns (morning focus, Saturday errands, etc.)
- Seasonal/weather context
- Memories from recent conversations

It proposes a week:

> "Here's what I'm thinking for this week:
>
> Monday: You have meetings 9–12. I've blocked 1–2pm for the insurance
> paperwork since the deadline is Friday. Evening is open — I left it free
> since Mondays are usually low energy.
>
> Tuesday: Open morning. I put the furnace inspection call at 10am —
> you've been pushing this for weeks and it's a 5-minute call. Afternoon
> you have the dentist at 3.
>
> Saturday morning: Errands batch — return the Amazon package, pick up
> dry cleaning. Also, it's been about 5 months since you checked the
> spare tire, so I added that.
>
> I didn't schedule the garden cleanup because it's going to be in the
> 30s all week. Pushing to late March when temps improve.
>
> Anything you want to change?"

You say "move the insurance thing to Wednesday, I'm not going to feel like it Monday" and it adjusts the task in Todoist. You see the updated schedule in Todoist's Upcoming view.

### 2. Daily Check-in (morning, optional)

Quick review of today's plan:

> "Today you have the team standup at 9, then the furnace call at 10
> which should take 5 minutes. Afternoon is open. Tonight: nothing
> scheduled, but you mentioned wanting to start that book."

You can adjust, add things, or skip the check-in entirely. The plan still exists in Todoist either way.

### 3. On-Demand Replanning

Something came up. You need to reshuffle.

> "Hey, I just found out I have a work emergency this afternoon."
>
> "Got it. I moved the errand run to tomorrow morning and pushed the
> report review to Thursday. The insurance deadline is still Friday
> so I kept that on Wednesday. Everything else stays."

### 4. Capture and Triage

You can also use it as a quick capture tool:

> "I need to get the car inspected sometime in the next month."
>
> "Added to Todoist with a deadline of March 21. I'll find a good
> slot for it in next week's planning. Anything else?"

### 5. Nightly Replan (automated)

Every evening, the system reviews the day:
- What was scheduled but not completed? → Reschedule forward.
- What new tasks appeared in Todoist? → Find slots for them.
- Did inbox count change significantly? → Adjust email processing blocks.
- Any fuzzy recurring tasks newly due? → Work them into the coming days.

This runs automatically (or you trigger it). The result: you wake up to an updated plan that reflects reality, not yesterday's optimistic intentions.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│               YOU (Claude Desktop / CLI)              │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│                    Claude                             │
│            (with system prompt + MCP)                 │
└──┬──────────┬──────────┬───────────┬────────┬────────┘
   │          │          │           │        │
   ▼          ▼          ▼           ▼        ▼
┌───────┐┌────────┐┌──────────┐┌────────┐┌────────────┐
│Todoist││Google  ││Planning  ││ Gmail  ││Weather API │
│  MCP  ││Calendar││Context   ││  MCP   ││ (optional) │
│Server ││  MCP   ││  MCP     ││ Server ││            │
│       ││ Server ││ Server   ││        ││            │
└───────┘└────────┘└──────────┘└────────┘└────────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │ Local Store │
                 │ (flat files)│
                 └─────────────┘
```

### Why MCP Servers?

MCP (Model Context Protocol) lets Claude talk to external services through a standardized interface. The practical benefit: **you don't build a conversation interface.** Claude Desktop (the app you may already have) or Claude Code becomes your UI. You just add MCP servers as tools Claude can use.

This means:
- No web app to build
- No chat interface to maintain
- Claude handles the conversation naturally
- You focus on building the integrations and planning logic

### The Four MCP Servers

#### 1. Todoist MCP Server

Lets Claude read and write your tasks. Todoist is both the task store and the schedule — tasks are assigned dates, times, durations, and reminders to form the plan. Todoist's "Upcoming" calendar view shows the resulting day-by-day schedule.

**Tools it exposes:**
- `get_tasks_due_today` — tasks due today, with project and notes
- `get_tasks_due_this_week` — grouped by project
- `get_overdue_tasks` — anything past due
- `get_recently_completed` — last 7 days (shows momentum)
- `get_repeatedly_deferred` — rescheduled 3+ times (shows avoidance)
- `get_project_tasks(project)` — all tasks in a project
- `get_someday_maybe_tasks` — background context, not scheduled
- `create_task(content, due_date, due_time, duration, project, reminder)` — add a task with full scheduling
- `update_task(id, due_date, due_time, duration, reminder)` — reschedule a task (date, time, duration, reminder)
- `complete_task(id)` — mark done
- `reschedule_task(id, new_date, new_time)` — move a task to a new slot

**Scheduling via Todoist:** When the planning agent schedules a task, it sets the due date, due time, and duration directly on the Todoist task. This means:
- The task shows up in Todoist's Upcoming calendar view on the right day and time
- Todoist handles reminders/notifications natively
- No sync between two systems — the plan and the task list are the same thing
- Rescheduling is just updating the task's date/time in Todoist

**Travel time:** For tasks that involve leaving the house, the system should account for travel time by either adding buffer to the task's duration or creating a brief "travel to X" task before location-dependent tasks.

**Note:** There are existing open-source Todoist MCP servers. Evaluate those first before building from scratch. You may only need to extend one with scheduling-specific tools.

#### 2. Google Calendar MCP Server

Lets Claude see your existing commitments. **Read-only** — the system never writes to your calendar.

**Tools it exposes:**
- `get_events_today` — what's on the calendar today
- `get_events_this_week` — full week view
- `get_events_range(start, end)` — events in a date range
- `get_free_windows(date, min_duration)` — available time blocks (gaps between events)

**Implementation:** Google Calendar API with OAuth. There are existing open-source Google Calendar MCP servers — evaluate those first.

**Why read-only:** Todoist handles all task scheduling (dates, times, durations, reminders). Google Calendar tells the system when you're busy. The system needs to distinguish between:
- **Hard blocks** (meetings, appointments, events with specific times) — truly unavailable
- **Soft blocks** (general work hours) — mostly working, but small personal tasks can fit in gaps

This distinction is handled by the planning logic, not the calendar API. The system knows your work schedule from memory and treats those hours accordingly.

#### 3. Gmail MCP Server

Lets Claude see inbox state and process email.

**Tools it exposes:**
- `get_inbox_count` — number of messages in inbox
- `get_inbox_summary` — sender, subject, date for recent inbox items
- `get_time_since_inbox_zero` — how long since inbox was at zero (derived from tracking)
- `archive_message(id)` — move processed message out of inbox
- `get_messages_by_label(label)` — for action-required, waiting-on, etc.

**How this feeds into planning:**

The "process email" task is dynamic — its priority and estimated duration are derived from inbox state:

- **Priority escalation:** Inbox count of 5 is low priority. Inbox count of 30 is high priority. Inbox count of 100 is urgent.
- **Duration estimation:** Roughly 1–2 minutes per email for triage, more for emails requiring action. 20 emails ≈ 30 min block, 50 emails ≈ 60 min block.
- **Staleness signal:** If it's been 3+ days since inbox zero, bump priority regardless of count — messages are aging and some probably need responses.

The planning agent doesn't need to process your email for you — it schedules time for *you* to process it, sized appropriately based on how much has accumulated.

**The paper inbox analog:** The system can't see your physical inbox, but it can track when you last told it you processed paper mail. Time since last processing serves as a rough proxy for pile size, just like email. This is tracked as a fuzzy recurring task with a short interval (every 2–3 days).

#### 4. Planning Context MCP Server (custom — this is what you build)

This is the "brain" that the off-the-shelf MCP servers don't provide. It manages everything the planning agent needs to know about you that isn't in Todoist or Calendar.

**Tools it exposes:**

```
# Values and preferences
get_values_doc          → returns the current values/priorities markdown
update_values_doc       → rewrites the values doc (called by Claude after
                          conversations that reveal new priorities)

# Memories
get_active_memories     → all non-resolved, non-expired memories
add_memory(content, category, expiry)
resolve_memory(id)
get_memories_by_category(category)

# Fuzzy recurring tasks
get_fuzzy_recurring     → all tasks with flexible schedules
add_fuzzy_recurring(description, interval_days, last_done, seasonal)
update_last_done(id, date)
get_due_soon(days_ahead) → fuzzy tasks approaching their interval

# Conversation history
save_conversation(summary, interactions)
get_recent_conversations(n)  → last n conversation summaries

# Seasonal/weather context
get_current_season      → based on date and location
get_weather_forecast    → next 7 days (if weather API configured)
get_task_constraints    → which tasks have seasonal/weather constraints
```

**Local storage (flat files):**

```
~/.planning-agent/
  values.md                     # system-maintained priorities doc
  memories.json                 # facts, observations, open threads
  fuzzy-recurring.json          # "check spare tire every ~6 months"
  scheduling_patterns.json      # learned completion, duration, deferral patterns
  conversations/
    2026-02-21.json             # daily conversation logs
  config.json                   # location, preferences, API keys
```

---

## Fuzzy Recurring Tasks

Todoist handles strict recurring tasks fine ("take vitamins every morning"). What it doesn't handle is tasks with flexible intervals and seasonal constraints. These live in the planning context store.

```json
[
  {
    "id": "fr_001",
    "description": "Check spare tire pressure and condition",
    "interval_days": 180,
    "flexibility_days": 30,
    "last_done": "2025-09-15",
    "seasonal_constraint": null,
    "preferred_context": "weekend, at home",
    "estimated_minutes": 15
  },
  {
    "id": "fr_002",
    "description": "Clean gutters",
    "interval_days": 180,
    "flexibility_days": 45,
    "last_done": "2025-10-20",
    "seasonal_constraint": "not_winter",
    "preferred_context": "weekend, dry weather, daylight",
    "estimated_minutes": 120
  },
  {
    "id": "fr_003",
    "description": "Replace HVAC filter",
    "interval_days": 90,
    "flexibility_days": 14,
    "last_done": "2025-12-01",
    "seasonal_constraint": null,
    "preferred_context": "anytime, at home",
    "estimated_minutes": 10
  },
  {
    "id": "fr_004",
    "description": "Deep clean kitchen appliances",
    "interval_days": 90,
    "flexibility_days": 30,
    "last_done": "2025-11-15",
    "seasonal_constraint": null,
    "preferred_context": "weekend morning, high energy",
    "estimated_minutes": 60
  }
]
```

The planning agent uses `interval_days` and `last_done` to know when something is approaching due, `flexibility_days` to know how much wiggle room there is, and `seasonal_constraint` and `preferred_context` to pick an appropriate time.

During weekly planning, Claude calls `get_due_soon(14)` and gets back anything that's within two weeks of its target date. It then schedules those alongside deadline-driven tasks from Todoist.

---

## The System Prompt

This is loaded into Claude's context every conversation (via Claude Desktop's project instructions or a system prompt file).

```
You are a personal planning agent. Your job is to manage the user's
time so they can focus on doing things rather than deciding what to do.

## Your capabilities
You have access to their Todoist tasks, Google Calendar, and a
planning context store that tracks their values, memories, fuzzy
recurring tasks, and conversation history.

## How to behave

### Planning
- When asked to plan a week, look at ALL inputs: Todoist tasks,
  calendar commitments, fuzzy recurring tasks due soon, weather,
  and their stated values and preferences.
- Propose a concrete schedule. Don't present options — make decisions
  and let them adjust.
- Explain your reasoning briefly. "I scheduled the furnace call
  Tuesday morning because you have a free window and it's been
  deferred 4 times."
- Respect energy patterns. Don't schedule hard tasks during known
  low-energy times.
- Leave buffer. Don't fill every hour. People need margin.
- Be honest about trade-offs. "You have 5 hours of tasks and 3 hours
  of free time this week. Something has to move. What matters most?"

### Scheduling rules
- Check Google Calendar for existing commitments. Distinguish between
  hard blocks (meetings, appointments — truly unavailable) and soft
  blocks (general work hours — mostly focused on work but small
  personal tasks are possible in gaps).
- During work hours, only schedule small personal tasks (phone calls,
  quick errands at lunch). Save larger personal tasks for before/after
  work and weekends.
- Schedule tasks by setting due date, time, and duration in Todoist.
  The user sees the plan in Todoist's Upcoming view.
- Respect seasonal and weather constraints on fuzzy recurring tasks.
- Tasks with hard deadlines get priority over flexible ones.
- Batch similar tasks when possible (errands together, admin together).
- Account for travel time on tasks that require leaving the house.
- Don't schedule tasks before 8am or after 9pm unless the user
  has indicated otherwise.
- Leave at least one weekend half-day unscheduled for rest/spontaneity.
- Consult memories for location-dependent constraints (e.g., printer
  access, what's available at home vs. office).

### Conversation style
- Short responses unless they ask for detail.
- One suggestion or question at a time.
- If they push back, adjust without guilt or justification.
- Never say "you should" or "you've been putting this off."
- If you notice a pattern (always deferring something), mention it
  gently once, then respect their decision.

### Memory
- After each conversation, save a summary and any new memories.
- Update the values doc if priorities have clearly shifted.
- Track when fuzzy recurring tasks are completed.
- Remember stated preferences ("I hate making phone calls before noon").

## Their values and priorities
[loaded from values.md via planning context MCP]

## Active memories
[loaded from memories.json via planning context MCP]

## Recent conversation summaries
[loaded via planning context MCP]
```

---

## The Onboarding Flow

First time the user runs the system, Claude has no context. The first conversation does three things:

1. **Values conversation** — What matters to you? What's stressing you out? What keeps falling through the cracks? (10–15 minutes, natural conversation)

2. **Fuzzy recurring task capture** — "Are there things you need to do periodically but don't have on a strict schedule? Like home maintenance, car stuff, health checkups?" Claude helps build the initial fuzzy-recurring.json.

3. **Preference capture** — "When do you usually have the most energy? Do you prefer to batch errands? Any times that are off-limits?" This goes into memories and the values doc.

After onboarding, Claude does an initial scan of Todoist and Calendar and proposes the first week's plan.

---

## Cost Analysis

### API Costs

- **Claude API calls:** Each planning conversation is maybe 5K–15K input tokens (system prompt + context) and 1K–3K output tokens. At Sonnet pricing (~$3/M input, $15/M output), that's roughly $0.02–0.08 per conversation. Even daily use is under $3/month.
- **If using Claude Desktop (Pro subscription):** Conversations are included in the subscription. MCP server calls are local. The main cost is the subscription you may already have.
- **Google Calendar API:** Free tier is generous (1M queries/day). Effectively free.
- **Todoist API:** Free, included with any Todoist plan.
- **Weather API:** Free tiers available (OpenWeatherMap, etc.). Optional.

### Infrastructure Costs

- **MCP servers run locally** on your machine. No hosting costs.
- **Flat file storage.** No database costs.
- **Total ongoing cost:** Either your existing Claude Pro subscription, or a few dollars/month in API calls. Effectively negligible.

---

## Build Order

### Phase 1: MCP Servers + Basic Planning (1–2 weeks)

1. **Evaluate existing MCP servers** for Todoist, Google Calendar, and Gmail. Install and test them with Claude Desktop. See what works out of the box.
2. **Build the Planning Context MCP server.** Start with just:
   - `get_values_doc` / `update_values_doc`
   - `get_active_memories` / `add_memory` / `resolve_memory`
   - `save_conversation` / `get_recent_conversations`
3. **Write the system prompt.** This is where the planning intelligence lives.
4. **Run the onboarding conversation** to generate the initial values doc.
5. **Try a weekly planning session.** See if Claude can look at your Todoist, your calendar, and your values doc and produce a reasonable week.

**Goal:** Can Claude propose a week that feels roughly right? If yes, keep going. If not, the problem is in the system prompt or the data quality — fix before adding more.

### Phase 2: Full Scheduling + Fuzzy Recurring (1–2 weeks)

6. **Enable Todoist write access.** Let Claude set dates, times, durations, and reminders on tasks to build the schedule.
7. **Add fuzzy recurring tasks** to the planning context. Build the capture and tracking tools.
8. **Add weather/seasonal awareness** (optional but easy — just an API call included in context).
9. **Add Gmail inbox signal.** Wire up inbox count and staleness tracking to feed into planning.
10. **Build the nightly replan.** Script that triggers a replanning conversation or runs the replan logic automatically.
11. **Refine the system prompt** based on Phase 1 experience.

**Goal:** The weekly plan actually shows up in Todoist's Upcoming view with dates, times, and durations. Fuzzy tasks get scheduled at appropriate times.

### Phase 3: Memory and Learning (1–2 weeks)

12. **Improve memory extraction.** Post-conversation summaries, preference capture, pattern observation.
13. **Add the daily check-in flow.** Quick morning review of today's plan.
14. **Add replanning support.** "My afternoon just blew up, what do I move?"
15. **Memory management.** Expiry, consolidation, staleness protection on values doc.

15b. **Add scheduling pattern extraction** to the post-conversation
pipeline. The extraction prompt is expanded to look for evidence of
scheduling patterns — tasks that took longer than estimated, completion
counts vs scheduled counts, categories that get deferred repeatedly.
Patterns are natural-language observations stored in
`scheduling_patterns.json`, maintained by the extraction agent,
and loaded into context at the start of each conversation.

**Goal:** The system gets better over time. Week 4 plans are noticeably smarter than week 1 plans.

### Phase 4: Polish and Automation (later)

16. **Scheduled planning prompts.** System reminds you Sunday evening to do weekly planning.
17. **Mobile access.** Messaging integration (Telegram, SMS) for on-the-go interaction.
18. **Dashboard or summary view.** What's planned this week, what's overdue, what fuzzy tasks are coming up.

---

## What's Different From the Previous Design

| Previous (Decision Assistant) | New (Planning Agent) |
|------|------|
| Waits for you to ask "what should I do?" | Proactively plans your week |
| Read-only on calendar and Todoist | Reads calendar, reads and writes Todoist |
| Suggests one task at a time | Proposes a full schedule |
| Conversation is the product | Todoist Upcoming view is the product, conversation is the interface |
| No scheduling intelligence | Understands deadlines, energy, seasons, buffers |
| Fuzzy recurring tasks not supported | First-class concept |

## What Stays the Same

- Todoist is the task store AND the schedule (no migration, and the plan lives where your tasks already are)
- Google Calendar is read-only context for existing commitments
- Values doc, generated through conversation, not written by you
- Memory layer for cross-session continuity
- Flat file storage, human-readable
- Conversational interface (now via Claude Desktop + MCP)
- Non-judgmental tone, no guilt, no nagging

---

---

## What This Doesn't Include (Yet)

- **Work task management.** Work uses Microsoft Calendar and OneNote — a different ecosystem. The system reads your work schedule as a constraint but doesn't manage work tasks. Extending to work would require Microsoft Graph API integration and is a separate project.
- **Ambient/proactive mode.** Start with you initiating conversations. Add nudges later.
- **Email processing.** Gmail integration provides inbox signals for planning, but the system doesn't read, sort, or respond to email for you.
- **Full behavioral inference.** The "observations" in memory are a lightweight version. Full pattern analysis comes later, if ever.
- **Mobile access.** MCP servers run locally. Phone interaction via messaging integration is a future phase.

---

## Design Decisions

These questions were open; here's where we landed:

### 1. Schedule everything except Someday/Maybe

The system schedules all tasks in Todoist with dates, times, and durations. Items in a Someday/Maybe project (or equivalent) are visible as context but not scheduled. The nightly replan picks up anything undone from today and finds it a new slot — no task falls through the cracks just because one day went sideways.

**Nightly replan:** Each evening (automated or triggered), the system reviews what was scheduled today, checks what actually got done (via Todoist completion status), and reshuffles undone items into the coming days. This means the plan is always current and you never wake up to a stale schedule.

### 2. Prioritization is a mix

When there's more to do than time allows, the system uses a combination of:
- **Hard deadlines** (non-negotiable — taxes due April 15)
- **Values alignment** (family tasks get weight because you said family matters)
- **Escalating urgency** (inbox at 100 emails, task deferred 6 times)
- **User input** (when the system can't decide, it asks — but only as a last resort)

There's no rigid formula. The system makes its best judgment and proposes it. You adjust. Over time, your adjustments teach it your real priorities.

### 3. Account for travel time

When tasks involve leaving the house or moving between locations, the system adds travel buffer. Errand batches should be sequenced geographically when possible.

### 4. Plans go off the rails — adjust automatically

The nightly replan handles this by default. For mid-day disruptions, the user can trigger a replan ("my afternoon just blew up") and the system reshuffles. The key principle: undone tasks always get rescheduled forward, never silently dropped.

### 5. Mobile access is desirable but deferred

The MCP approach is desktop-first. Mobile interaction can come later via a messaging integration (Telegram, SMS) or a lightweight web interface. Not a blocker for the core system.

### 6. Duration estimation comes from everywhere

- **Claude's common sense** for a first guess ("calling to schedule an appointment" ≈ 10 min)
- **User correction** during planning review ("that'll take longer, make it an hour")
- **Derived signals** (inbox count → email processing duration)
- **Historical patterns** — the post-conversation extraction
  pipeline captures scheduling patterns (completion rates,
  duration accuracy, deferral tendencies) in
  `scheduling_patterns.json`. These are natural-language
  observations maintained by the extraction agent, loaded into
  context at conversation start, and used to calibrate estimates

The system should default to slightly overestimating rather than packing the day too tight.
