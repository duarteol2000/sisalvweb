from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0001_initial'),
        ('notificacoes', '0007_notificacao_pontoref_oco'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='imovel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notificacoes', to='cadastros.imovel'),
        ),
        migrations.AddField(
            model_name='notificacao',
            name='pessoa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notificacoes', to='cadastros.pessoa'),
        ),
    ]

