from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0001_initial'),
        ('autoinfracao', '0011_alter_autoinfracao_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoinfracao',
            name='imovel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='autos_infracao_ref', to='cadastros.imovel'),
        ),
        migrations.AddField(
            model_name='autoinfracao',
            name='pessoa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='autos_infracao_ref', to='cadastros.pessoa'),
        ),
    ]

