from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prefeituras', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='prefeitura',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Latitude'),
        ),
        migrations.AddField(
            model_name='prefeitura',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Longitude'),
        ),
    ]

