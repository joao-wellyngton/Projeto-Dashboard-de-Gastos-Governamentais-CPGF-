# Guia Power BI — CPGF

Dois caminhos: **A)** ligar o Power BI nas views do SQL Server (recomendado) ou **B)** ler os CSVs de `out/`.

## 1. Fonte de dados
**A) SQL Server:** Obter dados → SQL Server → banco `cpgf`. Importe (modo Import):
`vw_gasto_base`, `vw_gasto_mensal`, `vw_fornecedores_abc`, `vw_unidade_resumo`, `vw_triagem`, `vw_qualidade_dados`.

**B) CSV (Power Query M):**
```m
let
  Fonte = Csv.Document(File.Contents("C:\dados\cpgf\out\transacoes_classificadas.csv"),
          [Delimiter=";", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
  Cab   = Table.PromoteHeaders(Fonte, [PromoteAllScalars=true]),
  Tipos = Table.TransformColumns(Cab, {{"valor", each Number.FromText(_, "pt-BR"), type number},
                                       {"score", Int64.From, Int64.Type}}),
  Data  = Table.TransformColumnTypes(Tipos, {{"data", type date}}, "en-CA")   // yyyy-mm-dd
in Data
```

## 2. Modelo
Tabela fato `Transacoes` (= `vw_triagem` ou CSV). Dimensões:
- `dCalendario` (DAX abaixo), relação 1:N em `Transacoes[data_transacao]`.
- `dUnidade` (unidade, tipo_unidade, orgao_superior), relação 1:N.
- `dFornecedor` (doc_favorecido, favorecido, ramo_atividade), relação 1:N.
Direção do filtro: única (dimensão → fato).

```dax
dCalendario =
ADDCOLUMNS(
  CALENDAR(DATE(2025,1,1), DATE(2026,12,31)),
  "Ano", YEAR([Date]), "MesNum", MONTH([Date]),
  "AnoMes", FORMAT([Date], "yyyy-mm"),
  "MesRotulo", FORMAT([Date], "mmm/yy"),
  "FimDeExercicio", IF(MONTH([Date]) IN {11,12}, "Sim", "Não")
)
```
Marque `dCalendario` como tabela de datas. Ordene `MesRotulo` por `AnoMes`.

## 3. Medidas DAX
```dax
Gasto Total        = SUM(Transacoes[valor])
Transações         = COUNTROWS(Transacoes)
Ticket Médio       = DIVIDE([Gasto Total], [Transações])
Gasto Mês Anterior = CALCULATE([Gasto Total], DATEADD(dCalendario[Date], -1, MONTH))
Cresc. MoM %       = DIVIDE([Gasto Total] - [Gasto Mês Anterior], [Gasto Mês Anterior])
Gasto Ano Anterior = CALCULATE([Gasto Total], SAMEPERIODLASTYEAR(dCalendario[Date]))
Cresc. YoY %       = DIVIDE([Gasto Total] - [Gasto Ano Anterior], [Gasto Ano Anterior])

-- Atipicidades
Transações Atípicas   = CALCULATE([Transações], Transacoes[score] > 0)
% Atípico             = DIVIDE([Transações Atípicas], [Transações])
Prioridade Alta (qtd) = CALCULATE([Transações], Transacoes[classe] = "Atípico - prioridade alta")
Prioridade Alta (R$)  = CALCULATE([Gasto Total], Transacoes[classe] = "Atípico - prioridade alta")
Com Contexto (qtd)    = CALCULATE([Transações], Transacoes[classe] = "Atípico com contexto provável")

-- Concentração de fornecedor (Top N)
Gasto Fornecedor = CALCULATE([Gasto Total], Transacoes[sigiloso] = 0)
Share Fornecedor = DIVIDE([Gasto Fornecedor], CALCULATE([Gasto Fornecedor], ALL(dFornecedor)))
Gasto Acumulado %  =
VAR _g = [Gasto Fornecedor]
VAR _t = CALCULATE([Gasto Fornecedor], ALL(dFornecedor))
RETURN DIVIDE(
  SUMX(FILTER(ALL(dFornecedor), [Gasto Fornecedor] >= _g), [Gasto Fornecedor]), _t)

-- Comparação entre pares (mesmo tipo de unidade)
Gasto por Unidade (tipo) =
AVERAGEX(VALUES(dUnidade[unidade]), [Gasto Total])
Desvio vs Pares =
DIVIDE([Gasto Total] - CALCULATE([Gasto por Unidade (tipo)], ALLEXCEPT(dUnidade, dUnidade[tipo_unidade])),
       CALCULATE([Gasto por Unidade (tipo)], ALLEXCEPT(dUnidade, dUnidade[tipo_unidade])))
```

## 4. Páginas (mesmo estilo verde do painel de referência)
1. **Visão geral** — cartões (Transações, Gasto Total, Ticket Médio); colunas por mês com `Cresc. MoM %`; barras por `ramo_atividade`; barras por órgão superior; mapa ou tabela de unidades. Segmentações: órgão superior, ano/mês.
2. **Fornecedores** — tabela Top 15 com barra de dados em `Gasto Fornecedor`; curva ABC (`Gasto Acumulado %`); `Share Fornecedor` por unidade. Exclua sigilosos.
3. **Atipicidades** — cartões por classe; colunas empilhadas por mês e classe; barras por regra (`regras` separado em linhas via Power Query “Dividir coluna por delimitador → em linhas”); matriz unidade × regra.
4. **Fila de investigação** — tabela filtrada por `score > 0`, ordenada por score e valor, com **drill-through** para detalhe da transação. Coloque as hipóteses legítimas como tooltip (`hipoteses`).
5. **Qualidade dos dados** — `vw_qualidade_dados` em tabela com % da base e a explicação do tratamento.
6. **Metodologia** — caixa de texto com regras, pesos, parâmetros e limites (copie do README).

## 5. Boas práticas do diferencial
- Nunca use as palavras “fraude” ou “irregular” em títulos. Use **“atipicidade”**, **“indício”**, **“fila de triagem”**.
- Cor: vermelho só para *prioridade alta*; âmbar para *observar*; azul para *contexto provável*. Sempre com ícone e rótulo (não só cor).
- Nov/dez em tom diferente no gráfico mensal e `Cresc. YoY %` no tooltip para separar sazonalidade de anomalia.
- Rodapé em todas as páginas: “Alertas são hipóteses de trabalho; só a apuração documental distingue erro, exceção autorizada e irregularidade.”
