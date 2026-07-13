from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_add_missing_task_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE tasks_task DROP COLUMN IF EXISTS due_date;",
            ],
            reverse_sql=[
                "ALTER TABLE tasks_task ADD COLUMN IF NOT EXISTS due_date DATE;",
            ],
        ),
    ]
