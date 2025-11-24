from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('denuncias', '0012_denuncia_processo'),
    ]

    operations = [
        migrations.AddField(
            model_name='denuncia',
            name='ocorrido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

