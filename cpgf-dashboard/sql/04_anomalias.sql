/* =====================================================================
   04 - ATIPICIDADES E TRIAGEM
   Diferencial do projeto: uma regra disparada = ATIPICIDADE (pede contexto), não irregularidade.
   Cada alerta carrega as hipóteses legítimas plausíveis e o contexto estrutural conhecido.
   ===================================================================== */
USE cpgf;
GO
CREATE OR ALTER VIEW dbo.vw_flags AS
WITH p AS (
    SELECT MAX(CASE WHEN chave='limite_unitario'           THEN valor END) AS lim,
           MAX(CASE WHEN chave='faixa_fracionamento'       THEN valor END) AS faixa,
           MAX(CASE WHEN chave='min_compras_fracionamento' THEN valor END) AS min_comp,
           MAX(CASE WHEN chave='saque_redondo_min'         THEN valor END) AS saque_min,
           MAX(CASE WHEN chave='mad_k'                     THEN valor END) AS k,
           MAX(CASE WHEN chave='share_concentracao'        THEN valor END) AS share,
           MAX(CASE WHEN chave='min_gasto_concentracao'    THEN valor END) AS min_gasto
    FROM dbo.parametros),
b AS (   -- base + log do valor + medianas por ramo
    SELECT g.*, CASE WHEN g.eh_saque = 0 AND g.valor > 0 THEN LOG(g.valor) END AS lv
    FROM dbo.vw_gasto_base g),
med AS (
    SELECT b.*, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lv) OVER (PARTITION BY ramo_atividade) AS med_lv
    FROM b),
mad AS (
    SELECT med.*, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(lv - med_lv)) OVER (PARTITION BY ramo_atividade) AS mad_lv
    FROM med),
cnt AS (
    SELECT mad.*,
           -- R1: nº de compras na faixa logo abaixo do limite, no mesmo dia/portador/favorecido
           SUM(CASE WHEN eh_saque = 0 AND valor BETWEEN p.lim * p.faixa AND p.lim THEN 1 ELSE 0 END)
               OVER (PARTITION BY cpf_portador, doc_favorecido, data_transacao) AS n_faixa_dia,
           SUM(CASE WHEN eh_saque = 0 AND eh_estorno = 0 THEN valor ELSE 0 END)
               OVER (PARTITION BY cod_unidade_gestora, ano_mes) AS gasto_ug_mes,
           SUM(CASE WHEN eh_saque = 0 AND eh_estorno = 0 THEN valor ELSE 0 END)
               OVER (PARTITION BY cod_unidade_gestora, ano_mes, doc_favorecido) AS gasto_fav_ug_mes,
           COUNT(*) OVER (PARTITION BY cpf_portador, doc_favorecido, valor, data_transacao) AS n_igual
    FROM mad CROSS JOIN p)
SELECT c.id_linha, c.data_transacao, c.ano_mes, c.orgao_superior, c.cod_unidade_gestora, c.unidade, c.tipo_unidade,
       c.portador, c.cpf_portador, c.doc_favorecido, c.favorecido, c.ramo_atividade, c.transacao, c.valor,
       CASE WHEN c.eh_saque = 0 AND c.eh_estorno = 0 AND c.valor BETWEEN p.lim * p.faixa AND p.lim
                 AND c.n_faixa_dia >= p.min_comp THEN 1 ELSE 0 END                                          AS R1_FRACIONAMENTO,
       CASE WHEN c.eh_saque = 1 AND c.valor >= p.saque_min AND c.valor % 100 = 0 THEN 1 ELSE 0 END          AS R2_SAQUE_REDONDO,
       CASE WHEN c.eh_saque = 0 AND c.eh_estorno = 0 AND (DATEPART(WEEKDAY, c.data_transacao) + @@DATEFIRST) % 7 IN (0, 1)
                 AND c.opera_24h = 0 THEN 1 ELSE 0 END                                                      AS R3_FIM_DE_SEMANA,   -- independe de @@DATEFIRST (0=sáb, 1=dom)
       CASE WHEN c.lv IS NOT NULL AND c.mad_lv > 0 AND (c.lv - c.med_lv) / (1.4826 * c.mad_lv) > p.k THEN 1 ELSE 0 END AS R4_VALOR_EXTREMO,
       CASE WHEN c.eh_saque = 0 AND c.eh_estorno = 0 AND c.sigiloso = 0 AND c.gasto_ug_mes > p.min_gasto
                 AND c.gasto_fav_ug_mes / NULLIF(c.gasto_ug_mes, 0) > p.share THEN 1 ELSE 0 END             AS R5_CONCENTRACAO,
       CASE WHEN c.eh_saque = 0 AND c.eh_estorno = 0 AND c.n_igual > 1 AND c.valor > 300 THEN 1 ELSE 0 END  AS R6_DUPLICIDADE,
       CASE WHEN MONTH(c.data_transacao) IN (11, 12) THEN 1 ELSE 0 END                                      AS ctx_fim_exercicio,
       CASE WHEN EXISTS (SELECT 1 FROM dbo.dim_eventos_legitimos e
                         WHERE e.cod_unidade_gestora = c.cod_unidade_gestora AND e.mes = MONTH(c.data_transacao)) THEN 1 ELSE 0 END AS ctx_evento
FROM cnt c CROSS JOIN p;
GO

CREATE OR ALTER VIEW dbo.vw_triagem AS
WITH s AS (
    SELECT f.*,
           R1_FRACIONAMENTO * 3 + R2_SAQUE_REDONDO * 2 + R3_FIM_DE_SEMANA * 1
         + R4_VALOR_EXTREMO * 2 + R5_CONCENTRACAO * 2 + R6_DUPLICIDADE * 1 AS score_bruto,
           CASE WHEN (R4_VALOR_EXTREMO = 1 AND ctx_fim_exercicio = 1)
                  OR ((R4_VALOR_EXTREMO = 1 OR R5_CONCENTRACAO = 1) AND ctx_evento = 1) THEN 1 ELSE 0 END AS tem_contexto
    FROM dbo.vw_flags f)
SELECT *,
       CASE WHEN score_bruto = 0 THEN 0 ELSE CASE WHEN score_bruto - 2 * tem_contexto < 0 THEN 0 ELSE score_bruto - 2 * tem_contexto END END AS score,
       CASE WHEN score_bruto = 0 THEN N'Sem indício'
            WHEN tem_contexto = 1 AND score_bruto - 2 < 3 THEN N'Atípico com contexto provável'
            WHEN score_bruto - 2 * tem_contexto >= 3 THEN N'Atípico - prioridade alta'
            ELSE N'Atípico - observar' END AS classe,
       CONCAT_WS(', ',
           CASE WHEN R1_FRACIONAMENTO = 1 THEN 'R1_FRACIONAMENTO' END, CASE WHEN R2_SAQUE_REDONDO = 1 THEN 'R2_SAQUE_REDONDO' END,
           CASE WHEN R3_FIM_DE_SEMANA = 1 THEN 'R3_FIM_DE_SEMANA' END, CASE WHEN R4_VALOR_EXTREMO = 1 THEN 'R4_VALOR_EXTREMO' END,
           CASE WHEN R5_CONCENTRACAO = 1 THEN 'R5_CONCENTRACAO' END,   CASE WHEN R6_DUPLICIDADE = 1 THEN 'R6_DUPLICIDADE' END) AS regras
FROM s;
GO

-- Fila de investigação: priorizada por score e valor
CREATE OR ALTER VIEW dbo.vw_fila_investigacao AS
SELECT TOP (1000) PERCENT * FROM dbo.vw_triagem WHERE classe <> N'Sem indício' ORDER BY score DESC, valor DESC;
GO

-- Resumo por regra: quantas atipicidades e quanto R$ estão em jogo
SELECT v.regra, COUNT(*) AS disparos, SUM(t.valor) AS valor_envolvido
FROM dbo.vw_triagem t
CROSS APPLY (VALUES ('R1_FRACIONAMENTO', t.R1_FRACIONAMENTO), ('R2_SAQUE_REDONDO', t.R2_SAQUE_REDONDO),
                    ('R3_FIM_DE_SEMANA', t.R3_FIM_DE_SEMANA), ('R4_VALOR_EXTREMO', t.R4_VALOR_EXTREMO),
                    ('R5_CONCENTRACAO', t.R5_CONCENTRACAO), ('R6_DUPLICIDADE', t.R6_DUPLICIDADE)) v(regra, flag)
WHERE v.flag = 1
GROUP BY v.regra
ORDER BY disparos DESC;
GO
