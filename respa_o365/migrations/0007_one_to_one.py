# Generated by Django 2.2.16 on 2021-10-27 16:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('respa_o365', '0006_enforce_unique_calendar_links'),
    ]

    operations = [
        migrations.AlterField(
            model_name='outlookcalendarlink',
            name='resource',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='resources.Resource', verbose_name='Resource'),
        ),
        migrations.AlterField(
            model_name='outlookcalendarlink',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='User'),
        ),
    ]
