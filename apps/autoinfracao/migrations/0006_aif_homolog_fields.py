from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
        ('autoinfracao', '0005_multa_item_homologado_no_quantidade'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoinfracao',
            name='homologado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='autoinfracao',
            name='homologado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='aif_homologados', to='usuarios.usuario'),
        ),
    ]

