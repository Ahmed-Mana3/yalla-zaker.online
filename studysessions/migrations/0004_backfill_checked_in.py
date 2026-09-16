from django.db import migrations


def mark_existing_finished_as_checked_in(apps, schema_editor):
    StudySession = apps.get_model("studysessions", "StudySession")
    StudySession.objects.filter(status="finished").update(checked_in=True)


class Migration(migrations.Migration):

    dependencies = [
        ("studysessions", "0003_studysession_checked_in_studysession_manual_seconds_and_more"),
    ]

    operations = [
        migrations.RunPython(mark_existing_finished_as_checked_in, migrations.RunPython.noop),
    ]
