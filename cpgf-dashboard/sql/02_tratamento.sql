/* =====================================================================
   02 - TRATAMENTO  (stg.cpgf_raw -> dbo.cpgf)
   Problemas reais tratados: decimal com vírgula, data dd/mm/aaaa, favorecido sigiloso / sem informação,
   estornos negativos, mês do extrato diferente do mês da transação, duplicidades.
   ===================================================================== */
USE cpgf;
GO
DROP TABLE IF EXISTS dbo.cpgf;

SELECT
    ROW_NUMBER() OVER (ORDER BY (SELECT NULL))                                   AS id_linha,
    r.cod_orgao_superior, r.nome_orgao_superior AS orgao_superior,
    r.cod_orgao, r.nome_orgao AS orgao,
    r.cod_unidade_gestora, r.nome_unidade_gestora AS unidade,
    TRY_CONVERT(INT, r.ano_extrato) * 100 + TRY_CONVERT(INT, r.mes_extrato)      AS ano_mes_extrato,
    r.cpf_portador, r.nome_portador AS portador,
    r.doc_favorecido, r.nome_favorecido AS favorecido,
    r.transacao,
    TRY_CONVERT(DATE, r.data_transacao, 103)                                     AS data_transacao,
    TRY_CONVERT(DECIMAL(14,2), REPLACE(REPLACE(r.valor_transacao, '.', ''), ',', '.')) AS valor
INTO dbo.cpgf
FROM stg.cpgf_raw r;

ALTER TABLE dbo.cpgf ADD
    ano_mes        AS (YEAR(data_transacao) * 100 + MONTH(data_transacao)) PERSISTED,
    eh_saque       AS (CASE WHEN transacao LIKE 'SAQUE%' THEN 1 ELSE 0 END) PERSISTED,
    eh_estorno     AS (CASE WHEN valor < 0 THEN 1 ELSE 0 END) PERSISTED,
    sigiloso       AS (CASE WHEN favorecido = 'Sigiloso' THEN 1 ELSE 0 END) PERSISTED,
    sem_favorecido AS (CASE WHEN favorecido LIKE 'Sem informa%' THEN 1 ELSE 0 END) PERSISTED;

CREATE INDEX ix_cpgf_ug_mes  ON dbo.cpgf (cod_unidade_gestora, ano_mes) INCLUDE (valor);
CREATE INDEX ix_cpgf_fav     ON dbo.cpgf (doc_favorecido) INCLUDE (valor, data_transacao);
CREATE INDEX ix_cpgf_portador ON dbo.cpgf (cpf_portador, data_transacao);
GO

/* ---- Relatório de qualidade (vira uma página do Power BI) ---- */
CREATE OR ALTER VIEW dbo.vw_qualidade_dados AS
SELECT N'Linhas carregadas'                         AS indicador, COUNT(*) AS qtd FROM dbo.cpgf
UNION ALL SELECT N'Valor inválido (não convertido)',  COUNT(*) FROM dbo.cpgf WHERE valor IS NULL
UNION ALL SELECT N'Data inválida (não convertida)',   COUNT(*) FROM dbo.cpgf WHERE data_transacao IS NULL
UNION ALL SELECT N'Estornos (valor negativo)',        COUNT(*) FROM dbo.cpgf WHERE eh_estorno = 1
UNION ALL SELECT N'Favorecido sigiloso',              COUNT(*) FROM dbo.cpgf WHERE sigiloso = 1
UNION ALL SELECT N'Favorecido sem informação',        COUNT(*) FROM dbo.cpgf WHERE sem_favorecido = 1
UNION ALL SELECT N'Saques em espécie',                COUNT(*) FROM dbo.cpgf WHERE eh_saque = 1
UNION ALL SELECT N'Mês do extrato ≠ mês da transação', COUNT(*) FROM dbo.cpgf WHERE ano_mes_extrato <> ano_mes
UNION ALL SELECT N'Linhas repetidas (mesmo portador/favorecido/valor/dia)', COUNT(*) - COUNT(DISTINCT CONCAT(cpf_portador,'|',doc_favorecido,'|',valor,'|',data_transacao))
           FROM dbo.cpgf;
GO
