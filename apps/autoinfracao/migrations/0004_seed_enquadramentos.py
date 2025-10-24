from django.db import migrations


def seed_enquadramentos(apps, schema_editor):
    Enquadramento = apps.get_model('autoinfracao', 'Enquadramento')
    Prefeitura = apps.get_model('prefeituras', 'Prefeitura')

    seeds = [
        {
            'codigo': 'EMB-372',
            'artigo': 'Art. 372',
            'descricao': 'Obra iniciada sem aprovação (Embargo)'
        },
        {
            'codigo': 'EMB-372B',
            'artigo': 'Art. 372',
            'descricao': 'Obra em desacordo com projeto aprovado (Embargo)'
        },
        {
            'codigo': 'INT-375',
            'artigo': 'Art. 375',
            'descricao': 'Interdição por más condições (limpeza/salubridade/segurança)'
        },
        {
            'codigo': 'INT-376',
            'artigo': 'Art. 376',
            'descricao': 'Interdição por atividade sem licença'
        },
    ]

    for pref in Prefeitura.objects.all():
        for s in seeds:
            Enquadramento.objects.get_or_create(
                prefeitura_id=pref.id,
                codigo=s['codigo'],
                defaults={
                    'artigo': s['artigo'],
                    'descricao': s['descricao'],
                    'valor_base': None,
                    'ativo': True,
                }
            )


def unseed_enquadramentos(apps, schema_editor):
    Enquadramento = apps.get_model('autoinfracao', 'Enquadramento')
    codigos = ['EMB-372', 'EMB-372B', 'INT-375', 'INT-376']
    Enquadramento.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('autoinfracao', '0003_autoinfracao_prazo_regularizacao_data_and_more'),
        ('prefeituras', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_enquadramentos, unseed_enquadramentos),
    ]
