from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("autoinfracao", "0016_autoinfracao_ocorrido_em"),
    ]

    operations = [
        migrations.AddField(
            model_name="autoinfracao",
            name="num_quartos",
            field=models.PositiveIntegerField(
                verbose_name="Número de quartos", null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="autoinfracao",
            name="num_leitos",
            field=models.PositiveIntegerField(
                verbose_name="Número de leitos", null=True, blank=True
            ),
        ),
    ]

