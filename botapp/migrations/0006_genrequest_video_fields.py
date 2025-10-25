from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('botapp', '0005_user_settings_daily_reward'),
    ]

    operations = [
        migrations.AddField(
            model_name='genrequest',
            name='aspect_ratio',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='genrequest',
            name='provider_job_id',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='genrequest',
            name='provider_metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='genrequest',
            name='source_media',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

