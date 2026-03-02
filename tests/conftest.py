from todoist_api_python.models import Task, Due


def create_task(
    id,
    content,
    priority=1,
    due_date_str=None,
    is_recurring=False,
    due_string=None,
    due_datetime_str=None,
):
    due = None
    if due_date_str:
        if not due_string:
            due_string = (
                f"every day starting {due_date_str}"
                if is_recurring
                else due_date_str
            )
        due = Due(
            string=due_string,
            date=due_datetime_str or due_date_str,
            is_recurring=is_recurring,
            timezone=None,
        )

    return Task(
        id=id,
        content=content,
        priority=priority,
        due=due,
        assignee_id=None,
        assigner_id=None,
        completed_at=None,
        created_at='2024-01-01T12:00:00Z',
        updated_at='2024-01-01T12:00:00Z',
        creator_id='1',
        description='',
        labels=[],
        order=0,
        parent_id=None,
        project_id='1',
        section_id=None,
        deadline=None,
        duration=None,
        is_collapsed=False,
    )
