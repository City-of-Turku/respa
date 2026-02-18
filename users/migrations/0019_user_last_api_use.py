# Generated migration: add last_api_use from django-helusers AbstractUser
# (django-helusers 0.14+ adds this field; users.User extends helusers.models.AbstractUser)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0018_create_login_method_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='last_api_use',
            field=models.DateField(blank=True, null=True, verbose_name='Latest API token usage date'),
        ),
    ]
