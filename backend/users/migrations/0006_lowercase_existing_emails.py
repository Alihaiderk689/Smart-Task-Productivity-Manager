from django.db import migrations


def lowercase_emails(apps, schema_editor):
    """Signup now always normalizes email/username to lowercase (see
    UserSerializer.validate_email), but accounts created before that change
    may still have mixed-case values -- normalize them here so DB-level
    lookups (email__iexact, unique constraints) behave consistently."""
    User = apps.get_model("auth", "User")

    for user in User.objects.exclude(email=""):
        lowered_email = user.email.lower()
        lowered_username = user.username.lower() if user.username else user.username
        email_changed = lowered_email != user.email
        username_changed = lowered_username != user.username

        if not email_changed and not username_changed:
            continue

        # Username has a DB-level unique constraint -- skip the rare case
        # where lowercasing would collide with another existing account
        # rather than crash the migration.
        if username_changed and User.objects.filter(username=lowered_username).exclude(pk=user.pk).exists():
            continue

        user.email = lowered_email
        user.username = lowered_username
        user.save(update_fields=["email", "username"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_emailotp_send_count"),
    ]

    operations = [
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
    ]
