# 🏉 Huddle — Autonomous Hackathon Project Manager & Scrum Master

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.12-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![CrewAI](https://img.shields.io/badge/CrewAI-0.130.0-FF4F00.svg?logo=ai&logoColor=white)](https://crewai.com)
[![Gemini](https://img.shields.io/badge/Google_Gemini-2.0_Flash-4285F4.svg?logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-asyncpg-336791.svg?logo=postgresql&logoColor=white)](https://github.com/MagicStack/asyncpg)
[![Telegram](https://img.shields.io/badge/Telegram_Bot-python--telegram--bot-2CA5E0.svg?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **An autonomous AI Scrum Master and Coach that guides hackathon teams from initial ideation to demo day directly inside Telegram.**

---

## 📖 Overview

**Huddle** is an intelligent, multi-agent project management system designed specifically for the intense, time-constrained environment of hackathons. Operating inside group chats on Telegram, Huddle autonomously guides teams through every phase of development:

1. **Intelligent Onboarding**: Extracts team constraints, deadlines, headcount, and skillsets from conversational messages.
2. **Ruthless Scope Critique**: Eliminates scope creep, identifies hidden technical gaps (auth, seed data, deployments), and protects the MVP.
3. **Skill-Aware Task Planning**: Decomposes the project into actionable, milestone-driven tasks tailored to team member skills and hourly deadlines.
4. **Proactive Blocker Detection**: Monitored via an asynchronous background scheduler, flagging stuck developers or missed check-ins before they derail the team.
5. **Evidence-Based Pitch Generation**: Synthesizes real check-ins into an honest, compelling demo-day pitch outline—guaranteeing no unbuilt features make it to the presentation.

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph "Telegram Interface"
        TG_USER[Team Members] -->|Chat Messages & Updates| TG_API[Telegram Bot API]
        TG_API -->|Webhook POST /webhook/telegram| API_GATEWAY[FastAPI Application]
        TG_BOT[Telegram Client Wrapper] -->|Formatted Alerts & Feedback| TG_API
    end

    subgraph "Huddle Core (FastAPI Engine)"
        API_GATEWAY --> ROUTER{Stage Router}
        ROUTER -->|No Deadline| STAGE_ONBOARD[Onboarding Extractor]
        ROUTER -->|No MVP Features| STAGE_CRITIC[Scope & Gap Critic]
        ROUTER -->|No Tasks Logged| STAGE_PLANNER[Roadmap Planner]
        ROUTER -->|Regular Updates| STAGE_CHECKIN[Check-in Logger]
        
        SCHEDULER[APScheduler Background Worker] -->|Periodic Trigger| AGENT_BLOCKER[Blocker Watcher Agent]
        
        MANUAL_TRIGGER[Manual /trigger-* Endpoints] --> AGENT_PITCH[Pitch Coach Agent]
        MANUAL_TRIGGER --> AGENT_BLOCKER
    end

    subgraph "Multi-Agent Intelligence (CrewAI + Gemini)"
        STAGE_CRITIC --> AGENT_CRITIC[ScopeAndGapCritic Agent]
        STAGE_PLANNER --> AGENT_PLANNER[RoadmapPlanner Agent]
        
        AGENT_CRITIC -.->|LiteLLM| GEMINI[Google Gemini 2.0 Flash]
        AGENT_PLANNER -.->|LiteLLM| GEMINI
        AGENT_BLOCKER -.->|LiteLLM| GEMINI
        AGENT_PITCH -.->|LiteLLM| GEMINI
        STAGE_ONBOARD -.->|Direct Extraction| GEMINI
    end

    subgraph "Persistence Layer (PostgreSQL)"
        DB_POOL[(asyncpg Connection Pool)]
        STAGE_ONBOARD --> DB_POOL
        STAGE_CRITIC --> DB_POOL
        STAGE_PLANNER --> DB_POOL
        STAGE_CHECKIN --> DB_POOL
        AGENT_BLOCKER --> DB_POOL
        AGENT_PITCH --> DB_POOL
    end

    AGENT_CRITIC --> TG_BOT
    AGENT_PLANNER --> TG_BOT
    AGENT_BLOCKER --> TG_BOT
    AGENT_PITCH --> TG_BOT
```

---

## 🤖 Multi-Agent Ecosystem

Huddle coordinates specialized autonomous agents powered by **CrewAI** and **Google Gemini 2.0 Flash**:

```mermaid
classDiagram
    class ScopeAndGapCritic {
        +Role: Scope and Gap Critic
        +Input: Team concept, skills, headcount, deadline
        +Output: mvp_features, cut_features, missing_pieces, risk_note
        +Goal: Eliminate scope creep & flag unconsidered technical prerequisites
    }

    class RoadmapPlanner {
        +Role: Roadmap Planner
        +Input: MVP scope, team skill matrix, deadline hours
        +Output: tasks[], roadmap milestones[]
        +Goal: Allocate concrete tasks by skill and hourly target offsets
    }

    class BlockerWatcher {
        +Role: Hackathon Blocker Watcher
        +Input: Task list, recent check-in logs, timestamp deltas
        +Output: blocked_tasks[], should_escalate, escalation_message
        +Goal: Catch stuck developers or 2+ missed check-ins proactively
    }

    class PitchCoach {
        +Role: Hackathon Pitch Coach
        +Input: MVP scope, full chronological check-in history
        +Output: problem, solution, what_we_built[], not_demoed[], demo_flow[]
        +Goal: Generate evidence-backed demo script reflecting actual progress
    }

    ScopeAndGapCritic --> RoadmapPlanner : Seeds validated MVP scope
    RoadmapPlanner --> BlockerWatcher : Tracks scheduled tasks against check-ins
    BlockerWatcher --> PitchCoach : Provides verified progress logs
```

### Agent Breakdown & Output Contracts

#### 1. Scope & Gap Critic (`agents/CRITIC.py`)
* **Role**: Seasoned hackathon judge & technical mentor.
* **Function**: `run_critic(team_id: int) -> dict`
* **JSON Contract**:
  ```json
  {
    "mvp_features": [{"feature": "Core auth & dashboard", "why_mvp": "Essential for demo flow"}],
    "cut_features": [{"feature": "Multi-tenant billing", "why_cut": "Zero demo value for 24h sprint"}],
    "missing_pieces": [{"gap": "Mock data seeder", "why_it_matters": "Empty graphs will look broken to judges"}],
    "risk_note": "Single biggest risk is unconfigured OAuth redirect URIs."
  }
  ```

#### 2. Roadmap & Task Planner (`agents/PLANNER.PY`)
* **Role**: Agile sprint master.
* **Function**: `run_planner(team_id: int) -> dict`
* **JSON Contract**:
  ```json
  {
    "tasks": [
      {
        "title": "Setup PostgreSQL asyncpg connection pool",
        "assigned_to": "backend",
        "reasoning": "Foundation for checkin tracking",
        "target_hour": 2
      }
    ],
    "roadmap": [
      {"milestone": "Database & Webhook live", "target_hour": 3},
      {"milestone": "Core MVP flow working", "target_hour": 16},
      {"milestone": "Feature freeze & demo rehearsal", "target_hour": 22}
    ]
  }
  ```

#### 3. Blocker Watcher (`agents/blocker.py`)
* **Role**: Empathetic team lead monitoring check-in frequency and sentiment.
* **Function**: `run_blocker_check(team_id: int) -> dict`
* **Escalation Rule**: Triggered when a task encounters **2+ missed consecutive check-ins** or **explicit stuck sentiment**.
* **JSON Contract**:
  ```json
  {
    "blocked_tasks": [{"task_id": 4, "reason": "OAuth token refresh loop failing"}],
    "should_escalate": true,
    "escalation_message": "@alex It looks like the auth integration is blocked. Does anyone have Google Console experience to jump in?"
  }
  ```

#### 4. Pitch Coach (`agents/pitch.py`)
* **Role**: Demo-day presentation coach.
* **Function**: `run_pitch(team_id: int) -> dict`
* **Integrity Guard**: If an MVP feature lacks verified check-in evidence, it is automatically moved to `not_demoed` to protect the team from judge cross-examination.
* **JSON Contract**:
  ```json
  {
    "problem": "Hackathon teams lose momentum due to scope creep and silent blockers.",
    "solution": "An autonomous AI project manager inside Telegram that keeps teams aligned and shipping.",
    "what_we_built": ["Automated scope critique engine", "Async check-in watcher", "Live pitch synthesizer"],
    "not_demoed": ["Voice message transcription"],
    "demo_flow": [
      "Show initial free-text setup in Telegram",
      "Demonstrate automatic scope critique",
      "Simulate blocker detection and instant escalation"
    ]
  }
  ```

---

## 🔄 Lifecycle & State Progression

```mermaid
stateDiagram-v2
    [*] --> Onboarding : First message in Telegram group
    
    state Onboarding {
        [*] --> ParseMessage : LiteLLM extracts parameters
        ParseMessage --> TeamCreated : Stores deadline, headcount, skills
    }

    TeamCreated --> ScopeReview : User posts project concept
    
    state ScopeReview {
        [*] --> RunCritic : ScopeAndGapCritic analyzes concept
        RunCritic --> SaveMVP : Stores MVP, cut features & gaps
        SaveMVP --> PostScopeSummary : Telegram scope response
    }

    ScopeReview --> Planning : Scope finalized
    
    state Planning {
        [*] --> RunPlanner : RoadmapPlanner decomposes MVP
        RunPlanner --> SaveTasks : Populates tasks & roadmap tables
        SaveTasks --> PostRoadmap : Sends timeline to Telegram
    }

    Planning --> ActiveSprint : Tasks populated

    state ActiveSprint {
        [*] --> CheckInCycle : APScheduler nudges team
        CheckInCycle --> LogCheckIn : Member replies with progress
        LogCheckIn --> EvaluateBlockers : BlockerWatcher audits state
        EvaluateBlockers --> EscalateAlert : should_escalate = true
        EvaluateBlockers --> CheckInCycle : Normal progress
    }

    ActiveSprint --> DemoDay : /trigger-pitch called
    
    state DemoDay {
        [*] --> RunPitchCoach : PitchCoach reviews check-in evidence
        RunPitchCoach --> GenerateOutline : Filters unverified claims
        GenerateOutline --> FinalPitch : Posts pitch script to chat
    }

    DemoDay --> [*]
```

---

## 🗄️ Database Schema

The database is built on **PostgreSQL** with native `JSONB` support for structured agent outputs and dynamic arrays.

```mermaid
erDiagram
    teams ||--o{ tasks : "owns"
    teams ||--o{ checkins : "logs"
    teams ||--o{ raw_messages : "records"
    tasks ||--o{ checkins : "references"

    teams {
        serial id PK
        bigint chat_id UK "Unique Telegram Chat ID"
        text team_name "Extracted team name"
        timestamp deadline "Calculated completion deadline"
        int headcount "Number of team members"
        jsonb skills "Skill breakdown per member"
        jsonb mvp_features "Scope critic approved features"
        jsonb cut_features "Features cut to preserve deadline"
        jsonb missing_pieces "Identified technical prerequisites"
        jsonb roadmap "Hourly milestone schedule"
        timestamp created_at
    }

    tasks {
        serial id PK
        int team_id FK "References teams(id)"
        text title "Actionable task title"
        text reasoning "Tied to specific MVP feature"
        text assigned_to "Role/Skill assignment"
        int target_hour "Hour offset from kickoff"
        text status "'todo' | 'in_progress' | 'blocked' | 'done'"
        timestamp created_at
    }

    checkins {
        serial id PK
        int task_id FK "References tasks(id)"
        int team_id FK "References teams(id)"
        text author "Telegram username or name"
        text message "Check-in content"
        boolean is_blocked "Blocker indicator flag"
        timestamp created_at
    }

    raw_messages {
        serial id PK
        int team_id FK "References teams(id)"
        text author "Sender identity"
        text message "Raw message text"
        timestamp created_at
    }
```

---

## 🚀 Getting Started

### Prerequisites

* **Python 3.10+**
* **PostgreSQL** instance (local or hosted e.g. Neon, Supabase, Railway)
* **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))
* **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))

---

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/I-U-5-H/huddle_bot.git
   cd huddle_bot
   ```

2. **Set Up a Virtual Environment**
   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   .\venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   # Database Configuration
   DATABASE_URL=postgresql://postgres:password@localhost:5432/huddle

   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

   # LLM Provider Configuration
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini/gemini-2.0-flash

   # Scheduler Configuration
   BLOCKER_CHECK_INTERVAL_HOURS=3
   ```

---

### Running the Application

1. **Start the FastAPI Server**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *On startup, Huddle automatically initializes the database pool, executes `db/schema.sql`, and starts the APScheduler.*

2. **Expose Localhost (for Webhook Development)**
   Use [ngrok](https://ngrok.com/) or [localtunnel](https://localtunnel.github.io/www/):
   ```bash
   ngrok http 8000
   ```

3. **Set the Telegram Webhook**
   Register your public URL with the Telegram Bot API:
   ```bash
   curl -F "url=https://your-domain.ngrok-free.app/webhook/telegram" \
        https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook
   ```

4. **Verify Health**
   ```bash
   curl http://localhost:8000/health
   # Response: {"ok": true}
   ```

---

## 📡 API & Demo-Day Triggers

Huddle includes manual trigger endpoints for live demonstrations and testing:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/webhook/telegram` | `POST` | Primary webhook endpoint for Telegram chat updates |
| `/health` | `GET` | Health check endpoint |
| `/trigger-pitch/{team_id}` | `POST` | Manually triggers the **Pitch Coach** agent and sends the pitch script directly to the team's Telegram chat |
| `/trigger-reminder/{team_id}` | `POST` | Manually triggers the **Blocker Watcher** check and sends any escalation to the Telegram chat |

---

## 📁 Repository Structure

```
Huddle/
├── agents/
│   ├── __init__.py
│   ├── CRITIC.py          # Scope & Gap Critic (CrewAI + Gemini)
│   ├── PLANNER.PY         # Roadmap & Task Planner (CrewAI + Gemini)
│   ├── blocker.py         # Blocker Watcher & Escalation Agent
│   └── pitch.py           # Evidence-based Pitch Coach Agent
├── db/
│   ├── __init__.py
│   ├── connection.py      # asyncpg connection pool & event-loop bridge
│   ├── queries.py         # Type-safe database queries & JSONB parser
│   └── schema.sql         # PostgreSQL schema definition & indexes
├── main.py                # FastAPI lifecycle, webhook router & manual endpoints
├── scheduler.py           # APScheduler background runner for periodic check-ins
├── telegram_client.py     # python-telegram-bot wrapper & message formatters
├── requirements.txt       # Core dependencies
└── README.md              # Project documentation
```

---

## 🛡️ Reliability & Production Best Practices

* **Zero Webhook Failures**: All webhook exceptions and JSON parsing anomalies are safely caught to prevent Telegram 500 retry storms.
* **Async-to-Sync Engine Bridge**: Provides a threadsafe event loop bridge (`db/connection.py`), enabling CrewAI synchronous agents to interact with `asyncpg` without deadlocks.
* **Message Truncation Guard**: Telegram's 4096-character limit is safely handled with automated truncators in `telegram_client.py`.
* **Database Connection Pooling**: Tuned connection pooling with native `jsonb` encoders/decoders for zero serialization overhead.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
