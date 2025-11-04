from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('denuncias', '0002_denunciaanexo_altura_px_denunciaanexo_hash_sha256_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='denuncia',
            name='local_oco_pontoref',
            field=models.CharField(blank=True, max_length=140, verbose_name='Ponto de referência'),
        ),
    ]
