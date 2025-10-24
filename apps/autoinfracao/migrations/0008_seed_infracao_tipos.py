from django.db import migrations


def seed_infracao_tipos(apps, schema_editor):
    InfracaoTipo = apps.get_model('autoinfracao', 'InfracaoTipo')
    Prefeitura = apps.get_model('prefeituras', 'Prefeitura')

    seeds = [
        {"codigo": "REMEMBRAMENTO", "nome": "Remembramento"},
        {"codigo": "DESMEMBRAMENTO", "nome": "Desmembramento"},
        {"codigo": "CONSTRUCAO", "nome": "Construção"},
        {"codigo": "LOTEAMENTO", "nome": "Loteamento"},
        {"codigo": "DEMOLICAO", "nome": "Demolição"},
        {"codigo": "PUBLICIDADE", "nome": "Publicidade"},
        {"codigo": "LIC_INSTALACAO", "nome": "Licença de Instalação"},
        {"codigo": "CONSTR_RENOV", "nome": "Construção/Renovação"},
        {"codigo": "TERRAPLANAGEM", "nome": "Terraplanagem"},
        {"codigo": "DRENAGEM", "nome": "Drenagem"},
        {"codigo": "RELOTEAMENTO", "nome": "Reloteamento"},
        {"codigo": "INFRAESTRUTURA", "nome": "Infraestrutura"},
    ]

    for pref in Prefeitura.objects.all():
        for item in seeds:
            InfracaoTipo.objects.get_or_create(
                prefeitura_id=pref.id,
                codigo=item["codigo"],
                defaults={
                    "nome": item["nome"],
                    "descricao": item["nome"],
                    "ativo": True,
                },
            )


def unseed_infracao_tipos(apps, schema_editor):
    InfracaoTipo = apps.get_model('autoinfracao', 'InfracaoTipo')
    codigos = [
        "REMEMBRAMENTO", "DESMEMBRAMENTO", "CONSTRUCAO", "LOTEAMENTO", "DEMOLICAO",
        "PUBLICIDADE", "LIC_INSTALACAO", "CONSTR_RENOV", "TERRAPLANAGEM", "DRENAGEM",
        "RELOTEAMENTO", "INFRAESTRUTURA",
    ]
    InfracaoTipo.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0007_aif_regularizado_em'),
        ('prefeituras', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_infracao_tipos, unseed_infracao_tipos),
    ]

