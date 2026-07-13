from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_alter_task_end_time_alter_task_start_time'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE tasks_task ADD COLUMN IF NOT EXISTS start_time TIMESTAMPTZ;",
                "ALTER TABLE tasks_task ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;",
                "ALTER TABLE tasks_task ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;",
                "ALTER TABLE tasks_task ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;",
            ],
            reverse_sql=[
                "ALTER TABLE tasks_task DROP COLUMN IF EXISTS completed_at;",
                "ALTER TABLE tasks_task DROP COLUMN IF EXISTS started_at;",
                "ALTER TABLE tasks_task DROP COLUMN IF EXISTS end_time;",
                "ALTER TABLE tasks_task DROP COLUMN IF EXISTS start_time;",
            ],
        ),
    ]
