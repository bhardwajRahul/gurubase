# Generated by Django 4.2.18 on 2025-02-03 13:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_datasource_scrape_tool'),
    ]

    operations = [
        migrations.AddField(
            model_name='outofcontextquestion',
            name='source',
            field=models.CharField(choices=[('USER', 'USER'), ('RAW_QUESTION', 'RAW_QUESTION'), ('REDDIT', 'REDDIT'), ('SUMMARY QUESTION', 'SUMMARY QUESTION'), ('WIDGET QUESTION', 'WIDGET QUESTION'), ('API', 'API'), ('DISCORD', 'DISCORD'), ('SLACK', 'SLACK')], default='USER', max_length=50),
        ),
    ]
