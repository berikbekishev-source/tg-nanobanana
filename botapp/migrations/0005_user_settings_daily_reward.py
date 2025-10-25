"""
Добавление полей для ежедневных бонусов в настройки пользователя.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('botapp', '0004_promocode_used_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersettings',
            name='daily_reward_streak',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='usersettings',
            name='last_daily_reward_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

