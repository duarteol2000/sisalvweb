from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0004_seed_enquadramentos'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoinfracaomultaitem',
            name='valor_homologado',
            field=models.DecimalField(null=True, blank=True, max_digits=12, decimal_places=2),
        ),
        migrations.RemoveField(
            model_name='autoinfracaomultaitem',
            name='quantidade',
        ),
    ]

