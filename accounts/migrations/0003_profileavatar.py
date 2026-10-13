import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_profile_last_seen'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='avatar_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ProfileAvatar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(max_length=20)),
                ('data', models.BinaryField()),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='avatar_file', to='accounts.profile')),
            ],
        ),
    ]
