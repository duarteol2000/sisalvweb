from django.db import migrations


def seed_globais(apps, schema_editor):
    InfracaoTipo = apps.get_model('autoinfracao', 'InfracaoTipo')

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

    for item in seeds:
        InfracaoTipo.objects.get_or_create(
            prefeitura=None,
            codigo=item["codigo"],
            defaults={
                "nome": item["nome"],
                "descricao": item["nome"],
                "ativo": True,
            },
        )


def unseed_globais(apps, schema_editor):
    InfracaoTipo = apps.get_model('autoinfracao', 'InfracaoTipo')
    codes = [
        "REMEMBRAMENTO", "DESMEMBRAMENTO", "CONSTRUCAO", "LOTEAMENTO", "DEMOLICAO",
        "PUBLICIDADE", "LIC_INSTALACAO", "CONSTR_RENOV", "TERRAPLANAGEM", "DRENAGEM",
        "RELOTEAMENTO", "INFRAESTRUTURA",
    ]
    InfracaoTipo.objects.filter(prefeitura__isnull=True, codigo__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('autoinfracao', '0008_seed_infracao_tipos'),
    ]

    operations = [
        migrations.RunPython(seed_globais, unseed_globais),
    ]
