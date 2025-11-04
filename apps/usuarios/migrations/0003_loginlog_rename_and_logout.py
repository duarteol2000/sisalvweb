from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_usuariologinlog'),
    ]

    operations = [
        migrations.RenameField(
            model_name='usuariologinlog',
            old_name='criado_em',
            new_name='logado_em',
        ),
        migrations.AddField(
            model_name='usuariologinlog',
            name='logout_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

