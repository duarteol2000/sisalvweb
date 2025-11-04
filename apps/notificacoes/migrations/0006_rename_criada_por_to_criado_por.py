from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notificacoes', '0005_notificacao_area_m2_notificacao_area_mezanino_m2_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='notificacao',
            old_name='criada_por',
            new_name='criado_por',
        ),
    ]

