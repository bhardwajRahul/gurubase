# Generated by Django 4.2.18 on 2025-02-05 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_outofcontextquestion_source'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='outofcontextquestion',
            index=models.Index(fields=['guru_type', 'date_created'], name='core_outofc_guru_ty_a23c4d_idx'),
        ),
        migrations.AddIndex(
            model_name='outofcontextquestion',
            index=models.Index(fields=['source'], name='core_outofc_source_1328c9_idx'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['date_created'], name='core_questi_date_cr_c8d35b_idx'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['source'], name='core_questi_source_55b1ff_idx'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['guru_type', 'date_created'], name='core_questi_guru_ty_47eb4b_idx'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['guru_type', 'source'], name='core_questi_guru_ty_7690ae_idx'),
        ),
    ]
