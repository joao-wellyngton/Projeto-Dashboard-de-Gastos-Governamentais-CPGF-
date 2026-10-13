/* =====================================================================
   01 - SCHEMA E CARGA  (SQL Server 2019+)
   Camadas: stg (bruto, tudo texto)  ->  dbo (tipado e tratado)
   Ajuste @CAMINHO para a pasta onde estão os CSVs.
   ===================================================================== */
IF DB_ID('cpgf') IS NULL CREATE DATABASE cpgf;
GO
USE cpgf;
GO
IF SCHEMA_ID('stg') IS NULL EXEC('CREATE SCHEMA stg');
GO

DROP TABLE IF EXISTS stg.cpgf_raw;
CREATE TABLE stg.cpgf_raw (
    cod_orgao_superior   NVARCHAR(20),  nome_orgao_superior NVARCHAR(200),
    cod_orgao            NVARCHAR(20),  nome_orgao          NVARCHAR(200),
    cod_unidade_gestora  NVARCHAR(20),  nome_unidade_gestora NVARCHAR(200),
    ano_extrato          NVARCHAR(10),  mes_extrato         NVARCHAR(10),
    cpf_portador         NVARCHAR(30),  nome_portador       NVARCHAR(200),
    doc_favorecido       NVARCHAR(40),  nome_favorecido     NVARCHAR(300),
    transacao            NVARCHAR(100), data_transacao      NVARCHAR(20),
    valor_transacao      NVARCHAR(30)
);

-- Arquivo do portal: ';' como separador, aspas, ISO-8859-1 (CODEPAGE 1252), 1ª linha = cabeçalho
BULK INSERT stg.cpgf_raw
FROM 'C:\dados\cpgf\cpgf_simulado.csv'          -- << troque pelo caminho real (ou por cada AAAAMM_CPGF.csv)
WITH (FORMAT = 'CSV', FIELDQUOTE = '"', FIELDTERMINATOR = ';', ROWTERMINATOR = '0x0a',
      FIRSTROW = 2, CODEPAGE = '1252', TABLOCK);

-- Dimensões de apoio (UTF-8)
DROP TABLE IF EXISTS dbo.dim_favorecido_ramo, dbo.dim_unidade_contexto, dbo.dim_eventos_legitimos;
CREATE TABLE dbo.dim_favorecido_ramo (cnpj_favorecido NVARCHAR(40) PRIMARY KEY, nome_favorecido NVARCHAR(300), ramo_atividade NVARCHAR(100));
CREATE TABLE dbo.dim_unidade_contexto (cod_unidade_gestora NVARCHAR(20) PRIMARY KEY, tipo_unidade NVARCHAR(30), opera_24h BIT);
CREATE TABLE dbo.dim_eventos_legitimos (cod_unidade_gestora NVARCHAR(20), mes TINYINT, motivo NVARCHAR(200));

BULK INSERT dbo.dim_favorecido_ramo FROM 'C:\dados\cpgf\dim_favorecido_ramo.csv'
WITH (FORMAT='CSV', FIELDTERMINATOR=';', ROWTERMINATOR='0x0a', FIRSTROW=2, CODEPAGE='65001');
BULK INSERT dbo.dim_unidade_contexto FROM 'C:\dados\cpgf\dim_unidade_contexto.csv'
WITH (FORMAT='CSV', FIELDTERMINATOR=';', ROWTERMINATOR='0x0a', FIRSTROW=2, CODEPAGE='65001');
BULK INSERT dbo.dim_eventos_legitimos FROM 'C:\dados\cpgf\dim_eventos_legitimos.csv'
WITH (FORMAT='CSV', FIELDTERMINATOR=';', ROWTERMINATOR='0x0a', FIRSTROW=2, CODEPAGE='65001');

-- Parâmetros das regras (mudar aqui não exige reescrever as views)
DROP TABLE IF EXISTS dbo.parametros;
CREATE TABLE dbo.parametros (chave VARCHAR(50) PRIMARY KEY, valor DECIMAL(14,4), descricao NVARCHAR(200));
INSERT dbo.parametros VALUES
 ('limite_unitario',            4000,  N'Teto por compra (confira a norma vigente)'),
 ('faixa_fracionamento',        0.70,  N'Compras entre 70% e 100% do limite'),
 ('min_compras_fracionamento',  3,     N'Mínimo de compras no mesmo dia/portador/favorecido'),
 ('saque_redondo_min',          1500,  N'Saque múltiplo de 100 acima deste valor'),
 ('mad_k',                      4.0,   N'Outlier robusto em escala log, por ramo'),
 ('share_concentracao',         0.35,  N'Favorecido > 35% do gasto da unidade no mês'),
 ('min_gasto_concentracao',     8000,  N'Gasto mínimo mensal da unidade para avaliar concentração');
GO
