"""
Миграция для добавления связи промокодов с пользователями
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('botapp', '0003_add_initial_ai_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='promocode',
            name='used_by',
            field=models.ManyToManyField(
                blank=True,
                related_name='used_promocodes',
                to='botapp.tguser',
            ),
        ),
    ]

