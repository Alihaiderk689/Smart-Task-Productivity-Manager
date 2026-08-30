# Indexes auth_user.email -- Django's stock User model only indexes/
# uniques `username`, so every email-keyed lookup (login, signup's
# uniqueness check, OTP verify/resend, password reset, Google login) was
# doing a full sequential scan on this table -- the single hottest lookup
# column in the app (see SCALABILITY_AUDIT.md's C5). `auth_user` is
# Django's built-in table, not a model owned by this app, so this uses
# raw SQL rather than AddIndexConcurrently (which needs a model in this
# app's migration state).
#
# Two indexes, matching the two lookup shapes actually used in the
# codebase (grep confirmed both are in real use, see users/views.py and
# users/serializers.py):
#   - a plain btree on email, for the exact-match `email=` lookups.
#   - an expression index on UPPER(email), for the `email__iexact`
#     lookups (Postgres compiles __iexact as UPPER(...) = UPPER(...) for
#     a plain CharField, which a plain btree index does NOT accelerate).
#
# Deliberately NOT a unique constraint/index: this environment has no way
# to confirm production has zero duplicate emails today, and a unique
# index that fails to build because of an existing duplicate would break
# the deploy. Before adding one, run this against the production DB to
# confirm it's safe:
#   SELECT lower(email) FROM auth_user GROUP BY lower(email) HAVING count(*) > 1;
# (an empty result means it's safe to add a unique index in a follow-up
# migration).

from django.db import migrations

# CREATE/DROP INDEX CONCURRENTLY can't run inside a transaction (Postgres
# restriction) -- required so this doesn't take a table-level lock that
# blocks writes to auth_user for the duration of the index build. Same
# reasoning as tasks/migrations/0013's AddIndexConcurrently.
class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("users", "0006_lowercase_existing_emails"),
    ]

    operations = [
        migrations.RunSQL(
            sql='CREATE INDEX CONCURRENTLY IF NOT EXISTS auth_user_email_idx ON auth_user (email);',
            reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS auth_user_email_idx;',
        ),
        migrations.RunSQL(
            sql='CREATE INDEX CONCURRENTLY IF NOT EXISTS auth_user_email_upper_idx ON auth_user (UPPER(email));',
            reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS auth_user_email_upper_idx;',
        ),
    ]
