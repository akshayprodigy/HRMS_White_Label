from app.api.v1.endpoints.timesheets import build_task_utilization
from app.models.task import Subtask, Task


def test_build_task_utilization_nested_seconds_top_level_display():
    task = Task(
        id=1,
        title="Parent Task",
        project_id=10,
        creator_id=99,
        assignee_id=None,
        estimated_hours=10,
    )

    top_level = Subtask(
        id=101,
        title="Top",
        task_id=task.id,
        parent_subtask_id=None,
        assignee_id=None,
        estimated_hours=4,
    )
    nested = Subtask(
        id=102,
        title="Nested",
        task_id=task.id,
        parent_subtask_id=top_level.id,
        assignee_id=None,
        estimated_hours=2,
    )

    used_map = {
        (task.id, None): 60,
        (task.id, top_level.id): 120,
        (task.id, nested.id): 300,
    }

    task_read, _estimated, used_total_seconds = build_task_utilization(
        task=task,
        subtasks=[top_level, nested],
        used_map=used_map,
        user_map={},
    )

    assert task_read.used_task_seconds == 60
    assert task_read.used_subtask_seconds == 420
    assert used_total_seconds == 480

    assert [st.id for st in task_read.subtasks] == [top_level.id]
    assert task_read.subtasks[0].used_seconds == 120
