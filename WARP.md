# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

A Python application that automatically reschedules overdue Todoist tasks by redistributing them across upcoming days based on priority and capacity limits. The scheduler respects task priorities and maintains recurring task patterns while ensuring manageable daily workloads.

## Architecture

The codebase follows a simple modular structure:

- **main.py**: Entry point that coordinates the scheduling process
- **scheduler.py**: Core `Scheduler` class containing the task redistribution logic
- **config.py**: Configuration constants and environment variable handling

Key architectural patterns:
- The `Scheduler` class uses recursive scheduling to push tasks to future days when capacity limits are exceeded
- Tasks are sorted by priority (descending) then due date (ascending) to ensure high-priority items get scheduled first
- Recurring tasks preserve their original due string patterns when rescheduled

## Development Commands

### Setup and Dependencies
```bash
# Install dependencies
poetry install

# Install without root package (as configured)  
poetry install --no-root
```

### Testing
```bash
# Run all tests
poetry run python -m pytest

# Run specific test file
poetry run python -m pytest tests/test_basic.py

# Run tests with verbose output
poetry run python -m pytest -v
```

### Code Quality
```bash
# Run Ruff linting
poetry run ruff check

# Run Ruff with auto-fix
poetry run ruff check --fix

# Type checking (Pyright is configured but no direct command shown)
```

### Running the Application
```bash
# Run the scheduler
poetry run python src/todoistScheduler/main.py

# Alternative direct execution
poetry run python main.py
```

## Environment Configuration

Required environment variables:
- `TODOIST_API_KEY`: Your Todoist API key
- `USER_TZ` (optional): User timezone, defaults to "America/New_York"

## Key Configuration Constants

- `TASKS_PER_DAY`: Maximum tasks to schedule per day (default: 5)
- `IGNORE_TASK_TAG`: Tag to exclude tasks from rescheduling (default: 'no_reschedule')

## Testing Structure

Tests use Python's unittest framework with mocking for the Todoist API. The test suite covers:
- Task sorting algorithms
- List slicing utilities  
- Scheduling logic with various scenarios (capacity limits, existing tasks, priority handling)

Test files are located in `tests/` directory with the main test suite in `test_basic.py`.

## GitHub Actions

The project includes a nightly workflow (`.github/workflows/nightly.yml`) that:
- Runs daily at 21:30 UTC
- Uses Python 3.11 and Poetry
- Executes the scheduler with the `TODOIST_API_KEY` secret