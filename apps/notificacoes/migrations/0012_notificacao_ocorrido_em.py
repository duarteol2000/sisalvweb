from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notificacoes', '0011_notificacao_fiscais'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='ocorrido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

