# Generated by Django 3.2.20 on 2023-09-26 07:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0149_create_maintenance_app'),
    ]

    operations = [
        migrations.AddField(
            model_name='resource',
            name='send_sms_notification',
            field=models.BooleanField(default=False, help_text='SMS will be sent to reserver in addition to email notifications. Reservation requires phone number field to be set.', verbose_name='Send reservation SMS'),
        ),
    ]
