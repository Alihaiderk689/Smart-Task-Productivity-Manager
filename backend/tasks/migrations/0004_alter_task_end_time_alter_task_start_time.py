from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_task_add_missing_time_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE tasks_task ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::timestamptz;",
                "ALTER TABLE tasks_task ALTER COLUMN end_time TYPE TIMESTAMPTZ USING end_time::timestamptz;",
            ],
            reverse_sql=[
                "ALTER TABLE tasks_task ALTER COLUMN end_time TYPE TIMESTAMP WITH TIME ZONE USING end_time::timestamptz;",
                "ALTER TABLE tasks_task ALTER COLUMN start_time TYPE TIMESTAMP WITH TIME ZONE USING start_time::timestamptz;",
            ],
        ),
    ]
