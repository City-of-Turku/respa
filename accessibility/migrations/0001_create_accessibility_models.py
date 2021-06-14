# Generated by Django 2.2.21 on 2021-06-14 05:47

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SentenceGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('name_fi', models.CharField(max_length=255, null=True)),
                ('name_en', models.CharField(max_length=255, null=True)),
                ('name_sv', models.CharField(max_length=255, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ServiceEntrance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of creation')),
                ('modified_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of modification')),
                ('is_main_entrance', models.BooleanField(default=False)),
                ('location', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('name', models.CharField(max_length=255)),
                ('name_fi', models.CharField(max_length=255, null=True)),
                ('name_en', models.CharField(max_length=255, null=True)),
                ('name_sv', models.CharField(max_length=255, null=True)),
                ('photo_url', models.URLField(max_length=1000, null=True)),
                ('street_view_url', models.URLField(max_length=1000, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serviceentrance_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serviceentrance_modified', to=settings.AUTH_USER_MODEL, verbose_name='Modified by')),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='ServicePoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('system_id', models.UUIDField(null=True)),
                ('code', models.PositiveIntegerField()),
                ('name', models.CharField(max_length=255)),
                ('name_fi', models.CharField(max_length=255, null=True)),
                ('name_en', models.CharField(max_length=255, null=True)),
                ('name_sv', models.CharField(max_length=255, null=True)),
            ],
            options={
                'ordering': ('code',),
            },
        ),
        migrations.CreateModel(
            name='ServiceRequirement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of creation')),
                ('modified_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of modification')),
                ('text', models.TextField(null=True)),
                ('text_fi', models.TextField(null=True)),
                ('text_en', models.TextField(null=True)),
                ('text_sv', models.TextField(null=True)),
                ('is_indoor_requirement', models.BooleanField(null=True)),
                ('evaluation_zone', models.CharField(max_length=255)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='servicerequirement_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='servicerequirement_modified', to=settings.AUTH_USER_MODEL, verbose_name='Modified by')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ServiceShortage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of creation')),
                ('modified_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of modification')),
                ('viewpoint', models.PositiveIntegerField()),
                ('shortage', models.CharField(max_length=1000)),
                ('shortage_fi', models.CharField(max_length=1000, null=True)),
                ('shortage_en', models.CharField(max_length=1000, null=True)),
                ('shortage_sv', models.CharField(max_length=1000, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serviceshortage_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serviceshortage_modified', to=settings.AUTH_USER_MODEL, verbose_name='Modified by')),
                ('service_point', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_shortages', to='accessibility.ServicePoint')),
                ('service_requirement', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_shortages', to='accessibility.ServiceRequirement')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ServiceSentence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of creation')),
                ('modified_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Time of modification')),
                ('sentence_order_text', models.CharField(blank=True, max_length=255, null=True)),
                ('sentence_order_text_fi', models.CharField(blank=True, max_length=255, null=True)),
                ('sentence_order_text_en', models.CharField(blank=True, max_length=255, null=True)),
                ('sentence_order_text_sv', models.CharField(blank=True, max_length=255, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='servicesentence_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='servicesentence_modified', to=settings.AUTH_USER_MODEL, verbose_name='Modified by')),
                ('sentence_group', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_sentences', to='accessibility.SentenceGroup')),
                ('service_entrance', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_sentences', to='accessibility.ServiceEntrance')),
                ('service_point', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_sentences', to='accessibility.ServicePoint')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='serviceentrance',
            name='service_point',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_entrances', to='accessibility.ServicePoint'),
        ),
        migrations.CreateModel(
            name='Sentence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sentence', models.TextField()),
                ('sentence_fi', models.TextField(null=True)),
                ('sentence_en', models.TextField(null=True)),
                ('sentence_sv', models.TextField(null=True)),
                ('group', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sentences', to='accessibility.SentenceGroup')),
            ],
        ),
    ]
