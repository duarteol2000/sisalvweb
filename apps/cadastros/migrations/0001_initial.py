from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('prefeituras', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Pessoa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('PF', 'Pessoa Física'), ('PJ', 'Pessoa Jurídica')], default='PF', max_length=2)),
                ('nome_razao', models.CharField(max_length=180)),
                ('doc_tipo', models.CharField(choices=[('CPF', 'CPF'), ('CNPJ', 'CNPJ'), ('OUTRO', 'Outro')], default='OUTRO', max_length=5)),
                ('doc_num', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('telefone', models.CharField(blank=True, max_length=20)),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('prefeitura', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pessoas', to='prefeituras.prefeitura')),
            ],
            options={
                'db_table': 'cad_pessoa',
                'ordering': ['nome_razao'],
                'verbose_name': 'Pessoa',
                'verbose_name_plural': 'Pessoas',
            },
        ),
        migrations.CreateModel(
            name='Imovel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inscricao', models.CharField(blank=True, max_length=40, verbose_name='Inscrição imobiliária')),
                ('logradouro', models.CharField(max_length=140)),
                ('numero', models.CharField(blank=True, max_length=20)),
                ('complemento', models.CharField(blank=True, max_length=60)),
                ('bairro', models.CharField(max_length=80)),
                ('cidade', models.CharField(max_length=80)),
                ('uf', models.CharField(max_length=2)),
                ('cep', models.CharField(blank=True, max_length=9)),
                ('latitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('prefeitura', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='imoveis', to='prefeituras.prefeitura')),
            ],
            options={
                'db_table': 'cad_imovel',
                'ordering': ['cidade', 'bairro', 'logradouro'],
                'verbose_name': 'Imóvel',
                'verbose_name_plural': 'Imóveis',
            },
        ),
        migrations.CreateModel(
            name='ImovelVinculo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('papel', models.CharField(choices=[('PROPRIETARIO', 'Proprietário'), ('POSSUIDOR', 'Possuidor'), ('LOCATARIO', 'Locatário'), ('RESPONSAVEL', 'Responsável')], default='PROPRIETARIO', max_length=20)),
                ('inicio', models.DateField(blank=True, null=True)),
                ('fim', models.DateField(blank=True, null=True)),
                ('observacao', models.CharField(blank=True, max_length=200)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('imovel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cadastros.imovel')),
                ('pessoa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cadastros.pessoa')),
            ],
            options={
                'db_table': 'cad_imovel_vinculo',
                'verbose_name': 'Vínculo Imóvel–Pessoa',
                'verbose_name_plural': 'Vínculos Imóvel–Pessoa',
            },
        ),
        migrations.AddField(
            model_name='imovel',
            name='pessoas',
            field=models.ManyToManyField(blank=True, related_name='imoveis', through='cadastros.ImovelVinculo', to='cadastros.pessoa'),
        ),
        migrations.AddIndex(
            model_name='pessoa',
            index=models.Index(fields=['prefeitura', 'doc_num'], name='cad_pesso_prefeitu_2d49a1_idx'),
        ),
        migrations.AddIndex(
            model_name='pessoa',
            index=models.Index(fields=['prefeitura', 'nome_razao'], name='cad_pesso_prefeitu_3d2e5a_idx'),
        ),
        migrations.AddIndex(
            model_name='imovel',
            index=models.Index(fields=['prefeitura', 'inscricao'], name='cad_imove_prefeitu_eab0d7_idx'),
        ),
        migrations.AddIndex(
            model_name='imovel',
            index=models.Index(fields=['prefeitura', 'bairro'], name='cad_imove_prefeitu_75f0f4_idx'),
        ),
        migrations.AddIndex(
            model_name='imovelvinculo',
            index=models.Index(fields=['imovel', 'pessoa', 'papel'], name='cad_imove_imovel_i_d5f8f8_idx'),
        ),
    ]

