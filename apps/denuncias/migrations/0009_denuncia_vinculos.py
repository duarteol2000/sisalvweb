from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0001_initial'),
        ('denuncias', '0008_denuncia_local_oco_pontoref'),
    ]

    operations = [
        migrations.AddField(
            model_name='denuncia',
            name='imovel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='denuncias', to='cadastros.imovel'),
        ),
        migrations.AddField(
            model_name='denuncia',
            name='pessoa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='denuncias', to='cadastros.pessoa'),
        ),
    ]

