from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0009_seed_infracao_tipos_globais'),
    ]

    operations = [
        migrations.RenameField(
            model_name='autoinfracao',
            old_name='criada_por',
            new_name='criado_por',
        ),
        migrations.RenameField(
            model_name='embargo',
            old_name='criada_por',
            new_name='criado_por',
        ),
        migrations.RenameField(
            model_name='interdicao',
            old_name='criada_por',
            new_name='criado_por',
        ),
    ]

