from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0006_aif_homolog_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoinfracao',
            name='regularizado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

