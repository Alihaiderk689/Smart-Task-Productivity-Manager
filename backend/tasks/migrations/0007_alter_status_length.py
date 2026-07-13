from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_remove_stale_due_date'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE tasks_task ALTER COLUMN status TYPE VARCHAR(20);",
            ],
            reverse_sql=[
                "ALTER TABLE tasks_task ALTER COLUMN status TYPE VARCHAR(10);",
            ],
        ),
    ]
