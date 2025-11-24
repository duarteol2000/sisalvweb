from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0015_autoinfracao_processo'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoinfracao',
            name='ocorrido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

