from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notificacoes', '0006_rename_criada_por_to_criado_por'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='pontoref_oco',
            field=models.CharField(blank=True, max_length=140, verbose_name='Ponto de referência'),
        ),
    ]

