# Generated by Django 2.2.27 on 2022-03-11 07:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('resources', '0132_add_stamp_to_resource_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaintenanceMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of creation')),
                ('modified_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of modification')),
                ('message', models.TextField(verbose_name='Message')),
                ('message_fi', models.TextField(null=True, verbose_name='Message')),
                ('message_en', models.TextField(null=True, verbose_name='Message')),
                ('message_sv', models.TextField(null=True, verbose_name='Message')),
                ('start', models.DateTimeField(verbose_name='Begin time')),
                ('end', models.DateTimeField(verbose_name='End time')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='maintenancemessage_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='maintenancemessage_modified', to=settings.AUTH_USER_MODEL, verbose_name='Modified by')),
            ],
            options={
                'verbose_name': 'maintenance message',
                'verbose_name_plural': 'maintenance messages',
                'ordering': ('start',),
            },
        ),
    ]
