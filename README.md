# Todoist Scheduler

A smart task scheduler for Todoist that automatically reschedules overdue tasks based on priority and available capacity.

## Features

- **Smart Rescheduling**: Automatically reschedules overdue tasks to future days based on priority
- **Priority-Based Sorting**: Higher priority tasks (P4) are scheduled before lower priority tasks
- **Daily Capacity Management**: Configurable limit on tasks per day to prevent overwhelming schedules
- **Recurring Task Support**: Properly handles recurring tasks while preserving their recurrence patterns
- **Flexible Filtering**: Ignores P1 tasks and tasks with custom tags (e.g., `@no_reschedule`)

## How It Works

The scheduler:
1. Fetches all overdue tasks from your Todoist account
2. Sorts them by priority (highest first) and original due date
3. Distributes them across future days based on your daily task capacity
4. Respects existing scheduled tasks when determining placement
5. Pushes lower-priority tasks to later days if a day is full

## Installation

### Prerequisites

- Python 3.10 or higher
- [Poetry](https://python-poetry.org/) for dependency management
- A Todoist account and API token

### Setup

1. Clone the repository:
```bash
git clone https://github.com/kpanko/todoistScheduler.git
cd todoistScheduler
```

2. Install dependencies:
```bash
poetry install
```

3. Set up your environment variables:
```bash
export TODOIST_API_KEY="your_api_key_here"
export USER_TZ="America/New_York"  # Optional, defaults to America/New_York
```

## Usage

Run the scheduler:
```bash
poetry run python src/todoistScheduler/main.py
```

Or use it as a module:
```bash
cd src
poetry run python -m todoistScheduler.main
```

## Configuration

You can customize the scheduler by setting environment variables:

- `TODOIST_API_KEY` (required): Your Todoist API token
- `USER_TZ` (optional): Your timezone (default: `America/New_York`)
- `TASKS_PER_DAY` (optional): Maximum tasks per day (default: `5`)
- `IGNORE_TASK_TAG` (optional): Tag to exclude tasks from rescheduling (default: `no_reschedule`)

You can also modify the constants in `src/todoistScheduler/config.py`.

## Development

### Running Tests

```bash
poetry run pytest
```

### Project Structure

```
todoistScheduler/
├── src/
│   └── todoistScheduler/
│       ├── __init__.py
│       ├── main.py          # Entry point
│       ├── scheduler.py     # Core scheduling logic
│       └── config.py        # Configuration settings
├── tests/
│   └── test_basic.py        # Unit tests
├── pyproject.toml           # Poetry configuration
└── README.md
```

## License

MIT

## Author

Kevin Panko (pankok@gmail.com)
