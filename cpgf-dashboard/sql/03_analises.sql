/* =====================================================================
   03 - ANÁLISES DESCRITIVAS: categoria, fornecedor, período e valor
   ===================================================================== */
USE cpgf;
GO
CREATE OR ALTER VIEW dbo.vw_gasto_base AS
SELECT c.*, 
       COALESCE(f.ramo_atividade, CASE WHEN c.eh_saque = 1 THEN N'Saque em espécie' ELSE N'Não identificado' END) AS ramo_atividade,
       COALESCE(u.tipo_unidade, 'N/D') AS tipo_unidade, COALESCE(u.opera_24h, 0) AS opera_24h
FROM dbo.cpgf c
LEFT JOIN dbo.dim_favorecido_ramo f ON f.cnpj_favorecido = c.doc_favorecido
LEFT JOIN dbo.dim_unidade_contexto u ON u.cod_unidade_gestora = c.cod_unidade_gestora;
GO

-- PERÍODO: gasto mensal e crescimento (igual ao gráfico do painel de referência)
CREATE OR ALTER VIEW dbo.vw_gasto_mensal AS
WITH m AS (SELECT ano_mes, SUM(valor) AS gasto, COUNT(*) AS qtd FROM dbo.vw_gasto_base GROUP BY ano_mes)
SELECT ano_mes, gasto, qtd,
       LAG(gasto) OVER (ORDER BY ano_mes) AS gasto_mes_anterior,
       CAST(100.0 * (gasto - LAG(gasto) OVER (ORDER BY ano_mes)) / NULLIF(LAG(gasto) OVER (ORDER BY ano_mes), 0) AS DECIMAL(8,2)) AS cresc_pct,
       -- comparação com o mesmo mês do ano anterior (isola sazonalidade, ex.: dezembro)
       CAST(100.0 * (gasto - LAG(gasto, 12) OVER (ORDER BY ano_mes)) / NULLIF(LAG(gasto, 12) OVER (ORDER BY ano_mes), 0) AS DECIMAL(8,2)) AS cresc_yoy_pct
FROM m;
GO

-- CATEGORIA
CREATE OR ALTER VIEW dbo.vw_gasto_ramo AS
WITH med AS (
    SELECT DISTINCT ramo_atividade,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor) OVER (PARTITION BY ramo_atividade) AS mediana
    FROM dbo.vw_gasto_base WHERE eh_estorno = 0),
agg AS (
    SELECT ramo_atividade, SUM(valor) AS gasto, COUNT(*) AS qtd, AVG(valor) AS ticket_medio
    FROM dbo.vw_gasto_base GROUP BY ramo_atividade)
SELECT a.*, m.mediana
FROM agg a JOIN med m ON m.ramo_atividade = a.ramo_atividade;
GO

-- FORNECEDOR: ranking e participação acumulada (curva ABC)
CREATE OR ALTER VIEW dbo.vw_fornecedores_abc AS
WITH t AS (
    SELECT doc_favorecido, MAX(favorecido) AS favorecido, MAX(ramo_atividade) AS ramo_atividade,
           SUM(valor) AS gasto, COUNT(*) AS qtd, COUNT(DISTINCT cod_unidade_gestora) AS unidades
    FROM dbo.vw_gasto_base WHERE sigiloso = 0 AND sem_favorecido = 0 AND eh_saque = 0
    GROUP BY doc_favorecido)
SELECT RANK() OVER (ORDER BY gasto DESC) AS posicao, *,
       CAST(100.0 * gasto / SUM(gasto) OVER () AS DECIMAL(6,3)) AS pct_total,
       CAST(100.0 * SUM(gasto) OVER (ORDER BY gasto DESC ROWS UNBOUNDED PRECEDING) / SUM(gasto) OVER () AS DECIMAL(6,2)) AS pct_acumulado
FROM t;
GO

-- VALOR: faixas de valor da transação
CREATE OR ALTER VIEW dbo.vw_faixas_valor AS
SELECT faixa, COUNT(*) AS qtd, SUM(valor) AS gasto
FROM (SELECT valor, CASE WHEN valor < 0 THEN N'0. Estorno'
                         WHEN valor < 100 THEN N'1. até R$ 100'
                         WHEN valor < 500 THEN N'2. R$ 100–500'
                         WHEN valor < 1000 THEN N'3. R$ 500–1 mil'
                         WHEN valor < 2500 THEN N'4. R$ 1–2,5 mil'
                         ELSE N'5. acima de R$ 2,5 mil' END AS faixa FROM dbo.cpgf) x
GROUP BY faixa;
GO

-- UNIDADE: resumo para comparação entre pares (mesmo tipo de unidade)
CREATE OR ALTER VIEW dbo.vw_unidade_resumo AS
SELECT cod_unidade_gestora, MAX(unidade) AS unidade, MAX(tipo_unidade) AS tipo_unidade, MAX(orgao_superior) AS orgao_superior,
       SUM(valor) AS gasto, COUNT(*) AS qtd, COUNT(DISTINCT doc_favorecido) AS fornecedores,
       SUM(CASE WHEN eh_saque = 1 THEN valor ELSE 0 END) AS gasto_saque
FROM dbo.vw_gasto_base GROUP BY cod_unidade_gestora;
GO
