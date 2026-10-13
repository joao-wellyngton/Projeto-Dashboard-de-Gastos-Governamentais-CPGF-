"""
Pipeline de análise do CPGF: limpeza -> features -> regras de atipicidade -> triagem -> agregados do dashboard.

Funciona igual com os CSVs reais do Portal da Transparência (mesmas colunas):
    python src/analise_cpgf.py --entrada data/raw/cpgf_simulado.csv
    python src/analise_cpgf.py --entrada "data/raw/202501_CPGF.csv" --entrada "data/raw/202502_CPGF.csv"

Princípio central: uma regra disparada = ATIPICIDADE (pede contexto), NUNCA acusação.
A classificação final separa "atípico sem contexto" de "atípico com contexto provável".
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
OUT = RAIZ / "out"
OUT.mkdir(exist_ok=True)

# ----------------------------------------------------------- parâmetros (ajuste à realidade)
P = {
    "limite_unitario": 4000.00,      # teto por compra (parâmetro: confira a norma vigente)
    "faixa_fracionamento": 0.70,     # compras entre 70% e 100% do limite
    "min_compras_fracionamento": 3,  # nº mínimo de compras no mesmo dia/portador/favorecido
    "saque_redondo_min": 1500,       # saque múltiplo de 100 acima disso
    "mad_k": 4.0,                    # outlier robusto: (ln valor - mediana) / (1,4826*MAD) > k, por ramo
    "share_concentracao": 0.35,      # favorecido > 35% do gasto da unidade no mês
    "min_gasto_concentracao": 8000,
}
PESOS = {  # peso do indício; score >= 3 => prioridade alta
    "R1_FRACIONAMENTO": 3, "R2_SAQUE_REDONDO": 2, "R3_FIM_DE_SEMANA": 1,
    "R4_VALOR_EXTREMO": 2, "R5_CONCENTRACAO": 2, "R6_DUPLICIDADE": 1,
}
HIPOTESES = {  # explicações legítimas plausíveis, mostradas junto de cada alerta
    "R1_FRACIONAMENTO": "Compras recorrentes de reposição no mesmo fornecedor; item vendido em lotes; falta de limite no cartão no dia",
    "R2_SAQUE_REDONDO": "Saque autorizado para despesa de pronto pagamento (ex.: pequenos reparos, diárias de campo)",
    "R3_FIM_DE_SEMANA": "Plantão, evento, viagem a serviço ou compra on-line com data de processamento no fim de semana",
    "R4_VALOR_EXTREMO": "Equipamento ou serviço pontual de valor maior que o típico do ramo; erro de digitação na origem",
    "R5_CONCENTRACAO": "Fornecedor único na região; contrato/ata de registro de preços; unidade pequena com poucos fornecedores",
    "R6_DUPLICIDADE": "Erro de carga do extrato OU duas compras idênticas legítimas (sem ID da transação é impossível distinguir)",
}


# ----------------------------------------------------------- 1. leitura e limpeza
def ler(arquivos):
    partes = [pd.read_csv(a, sep=";", encoding="latin-1", dtype=str) for a in arquivos]
    df = pd.concat(partes, ignore_index=True)
    ren = {
        "CÓDIGO ÓRGÃO SUPERIOR": "cod_sup", "NOME ÓRGÃO SUPERIOR": "orgao_superior", "CÓDIGO ÓRGÃO": "cod_orgao",
        "NOME ÓRGÃO": "orgao", "CÓDIGO UNIDADE GESTORA": "cod_ug", "NOME UNIDADE GESTORA": "unidade",
        "ANO EXTRATO": "ano_extrato", "MÊS EXTRATO": "mes_extrato", "CPF PORTADOR": "cpf_portador",
        "NOME PORTADOR": "portador", "CNPJ OU CPF FAVORECIDO": "doc_favorecido", "NOME FAVORECIDO": "favorecido",
        "TRANSAÇÃO": "transacao", "DATA TRANSAÇÃO": "data", "VALOR TRANSAÇÃO": "valor",
    }
    return df.rename(columns=ren)


def limpar(df):
    qualidade = {"linhas_brutas": int(len(df))}
    df["valor"] = pd.to_numeric(df["valor"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
    qualidade["valor_invalido"] = int(df.valor.isna().sum())
    qualidade["data_invalida"] = int(df.data.isna().sum())
    df = df.dropna(subset=["valor", "data"]).copy()
    df["ano_mes"] = df.data.dt.to_period("M").astype(str)
    df["eh_saque"] = df.transacao.str.upper().str.startswith("SAQUE")
    df["eh_estorno"] = df.valor < 0
    df["sigiloso"] = df.favorecido.str.lower().eq("sigiloso")
    df["sem_favorecido"] = df.favorecido.str.lower().str.startswith("sem informa")
    df["extrato_ym"] = df.ano_extrato.astype(int) * 100 + df.mes_extrato.astype(int)
    df["mes_extrato_difere"] = df.extrato_ym != (df.data.dt.year * 100 + df.data.dt.month)
    qualidade.update({
        "estornos_negativos": int(df.eh_estorno.sum()),
        "favorecido_sigiloso": int(df.sigiloso.sum()),
        "favorecido_sem_informacao": int(df.sem_favorecido.sum()),
        "saques": int(df.eh_saque.sum()),
        "mes_extrato_diferente_da_transacao": int(df.mes_extrato_difere.sum()),
        "linhas_totalmente_duplicadas": int(df.duplicated(keep="first").sum()),
        "cpf_mascarado": int(df.cpf_portador.str.contains(r"\*", regex=True).sum()),
    })
    return df.reset_index(drop=True), qualidade


def enriquecer(df):
    fav = pd.read_csv(RAW / "dim_favorecido_ramo.csv", sep=";", dtype=str)
    uni = pd.read_csv(RAW / "dim_unidade_contexto.csv", sep=";", dtype=str)
    ev = pd.read_csv(RAW / "dim_eventos_legitimos.csv", sep=";", dtype=str)
    df = df.merge(fav[["cnpj_favorecido", "ramo_atividade"]], left_on="doc_favorecido", right_on="cnpj_favorecido", how="left")
    df["ramo_atividade"] = df.ramo_atividade.fillna(pd.Series(np.where(df.eh_saque, "Saque em espécie", "Não identificado"), index=df.index))
    df = df.merge(uni, left_on="cod_ug", right_on="cod_unidade_gestora", how="left")
    df["opera_24h"] = df.opera_24h.fillna("0").astype(int)
    df["tipo_unidade"] = df.tipo_unidade.fillna("N/D")
    ev["chave"] = ev.cod_unidade_gestora + "-" + ev.mes
    df["evento_legitimo"] = (df.cod_ug + "-" + df.data.dt.month.astype(str)).isin(set(ev.chave))
    return df


# ----------------------------------------------------------- 2. regras de atipicidade
def regras(df):
    f = pd.DataFrame(False, index=df.index, columns=list(PESOS))
    compra = ~df.eh_saque & ~df.eh_estorno

    # R1 fracionamento: >=3 compras/dia, mesmo portador+favorecido, cada uma na faixa logo abaixo do limite
    lim = P["limite_unitario"]
    na_faixa = compra & df.valor.between(lim * P["faixa_fracionamento"], lim)
    g = df[na_faixa].groupby(["cpf_portador", "doc_favorecido", "data"]).valor.transform("size")
    f.loc[g[g >= P["min_compras_fracionamento"]].index, "R1_FRACIONAMENTO"] = True

    # R2 saque redondo alto
    f["R2_SAQUE_REDONDO"] = df.eh_saque & (df.valor >= P["saque_redondo_min"]) & (df.valor % 100 == 0)

    # R3 fim de semana em unidade que NÃO opera 24h
    f["R3_FIM_DE_SEMANA"] = compra & (df.data.dt.weekday >= 5) & (df.opera_24h == 0)

    # R4 valor extremo: desvio robusto (mediana/MAD) em escala log, dentro do ramo
    base = df[compra & (df.valor > 0)]
    lv = np.log(base.valor)
    med = lv.groupby(base.ramo_atividade).transform("median")
    mad = (lv - med).abs().groupby(base.ramo_atividade).transform("median").replace(0, np.nan)
    z = (lv - med) / (1.4826 * mad)
    f.loc[z[z > P["mad_k"]].index, "R4_VALOR_EXTREMO"] = True

    # R5 concentração: um favorecido > X% do gasto da unidade no mês
    gasto_ug = df[compra].groupby(["cod_ug", "ano_mes"]).valor.transform("sum")
    gasto_fav = df[compra].groupby(["cod_ug", "ano_mes", "doc_favorecido"]).valor.transform("sum")
    share = gasto_fav / gasto_ug
    ok = (share > P["share_concentracao"]) & (gasto_ug > P["min_gasto_concentracao"]) & ~df.loc[compra.index[compra], "sigiloso"]
    f.loc[ok[ok].index, "R5_CONCENTRACAO"] = True

    # R6 duplicidade (mesmo portador, favorecido, valor e dia)
    f["R6_DUPLICIDADE"] = compra & df.duplicated(["cpf_portador", "doc_favorecido", "valor", "data"], keep=False) & (df.valor > 300)
    return f


def contexto_legitimo(df, f):
    """Reduz (não zera) o peso quando existe explicação estrutural conhecida."""
    ctx = pd.Series("", index=df.index)
    dez = df.data.dt.month.isin([11, 12])
    m = f["R4_VALOR_EXTREMO"] & dez
    ctx[m] += "fim de exercício (nov/dez); "
    m = f["R5_CONCENTRACAO"] & df.evento_legitimo
    ctx[m] += "evento anual cadastrado na unidade; "
    m = f["R4_VALOR_EXTREMO"] & df.evento_legitimo
    ctx[m] += "evento anual cadastrado na unidade; "
    return ctx


def pontuar(df):
    f = regras(df)
    ctx = contexto_legitimo(df, f)
    score = sum(f[r].astype(int) * w for r, w in PESOS.items())
    score = score - (ctx != "").astype(int) * 2
    score = score.clip(lower=0).where(f.any(axis=1), 0)
    regras_txt = f.apply(lambda r: ", ".join(c for c in f.columns if r[c]), axis=1)
    classe = np.select(
        [(f.any(axis=1)) & (ctx != "") & (score < 3), score >= 3, score >= 1],
        ["Atípico com contexto provável", "Atípico - prioridade alta", "Atípico - observar"],
        default="Sem indício",
    )
    hip = regras_txt.map(lambda t: " | ".join(HIPOTESES[x.strip()] for x in t.split(",") if x.strip()))
    return f, score, regras_txt, ctx.str.rstrip("; "), classe, hip


# ----------------------------------------------------------- 3. agregados para o dashboard
def agregar(df, f, qualidade, metricas):
    compra = df[~df.eh_saque]
    cubo = (df.assign(qtd=1).groupby(["ano_mes", "orgao_superior", "ramo_atividade"], as_index=False)
              .agg(valor=("valor", "sum"), qtd=("qtd", "sum")))
    cubo["valor"] = cubo.valor.round(2)
    fornec = (compra[~compra.sigiloso & ~compra.sem_favorecido].groupby(["orgao_superior", "doc_favorecido", "favorecido", "ramo_atividade"], as_index=False)
              .agg(valor=("valor", "sum"), qtd=("valor", "size")))
    fornec = fornec.sort_values("valor", ascending=False).groupby("orgao_superior").head(60)
    fornec["valor"] = fornec.valor.round(2)
    ug_mes = (df.groupby(["orgao_superior", "unidade", "tipo_unidade"], as_index=False)
                .agg(valor=("valor", "sum"), qtd=("valor", "size"),
                     atipicos=("classe", lambda s: int((s != "Sem indício").sum()))))
    ug_mes["valor"] = ug_mes.valor.round(2)
    ug_mes["pct_atipico"] = (ug_mes.atipicos / ug_mes.qtd * 100).round(2)
    dow = df.assign(dia=df.data.dt.weekday).groupby("dia").valor.sum().round(2).to_dict()
    flag_mes = (df[df.classe != "Sem indício"].groupby(["ano_mes", "orgao_superior", "classe"])
                  .agg(n=("valor", "size"), valor=("valor", "sum")).reset_index())
    flag_mes["valor"] = flag_mes.valor.round(2)
    forn_todos = (compra[~compra.sigiloso & ~compra.sem_favorecido].groupby(["doc_favorecido", "favorecido", "ramo_atividade"], as_index=False)
                  .agg(valor=("valor", "sum"), qtd=("valor", "size"), unidades=("cod_ug", "nunique"))
                  .sort_values("valor", ascending=False).head(60))
    forn_todos["valor"] = forn_todos.valor.round(2)
    reg_org = f.groupby(df.orgao_superior).sum().astype(int).to_dict("index")
    top = df[df.classe != "Sem indício"].sort_values(["score", "valor"], ascending=False).head(600)
    alertas = top[["data", "orgao_superior", "unidade", "portador", "favorecido", "ramo_atividade", "transacao",
                   "valor", "score", "classe", "regras", "contexto", "hipoteses"]].copy()
    alertas["data"] = alertas.data.dt.strftime("%Y-%m-%d")
    resumo_regras = {r: int(f[r].sum()) for r in f.columns}
    return {
        "gerado_com": "dados SIMULADOS" if metricas.get("simulado") else "dados reais",
        "periodo": [df.ano_mes.min(), df.ano_mes.max()],
        "kpis": {
            "transacoes": int(len(df)), "gasto_total": round(float(df.valor.sum()), 2),
            "unidades": int(df.cod_ug.nunique()), "fornecedores": int(compra.doc_favorecido.nunique()),
            "atipicas": int((df.classe != "Sem indício").sum()), "prioridade_alta": int((df.classe == "Atípico - prioridade alta").sum()),
            "com_contexto": int((df.classe == "Atípico com contexto provável").sum()),
            "valor_prioridade_alta": round(float(df[df.classe == "Atípico - prioridade alta"].valor.sum()), 2),
        },
        "parametros": P, "pesos": PESOS, "hipoteses": HIPOTESES,
        "cubo": cubo.to_dict("records"), "fornecedores": fornec.to_dict("records"),
        "fornecedores_todos": forn_todos.to_dict("records"), "regras_por_orgao": reg_org,
        "unidades": ug_mes.to_dict("records"), "dia_semana": dow, "atipicos_mes": flag_mes.to_dict("records"),
        "alertas": alertas.to_dict("records"), "regras_disparos": resumo_regras,
        "qualidade": qualidade, "validacao": metricas,
    }


def validar(df, f):
    """Compara com o gabarito (só existe na base simulada)."""
    p = RAW / "gabarito_anomalias.csv"
    if not p.exists():
        return {}
    gt = pd.read_csv(p, sep=";", decimal=",")
    gt_idx = set(gt.linha - 1)  # posição no CSV bruto; df mantém a ordem (sem dropna relevante)
    pred_idx = set(df.index[df.regras != ""])
    tp = len(gt_idx & pred_idx)
    mapa = {"FRACIONAMENTO": "R1_FRACIONAMENTO", "SAQUE_REDONDO": "R2_SAQUE_REDONDO", "FIM_DE_SEMANA_ADM": "R3_FIM_DE_SEMANA",
            "VALOR_EXTREMO": "R4_VALOR_EXTREMO", "CONCENTRACAO": "R5_CONCENTRACAO", "DUPLICIDADE": "R6_DUPLICIDADE"}
    por_tipo = {}
    for t, r in mapa.items():
        idx = set(gt[gt.tipo_anomalia_injetada == t].linha - 1)
        det = set(df.index[f[r]])
        por_tipo[t] = {"injetadas": len(idx), "detectadas": len(idx & det),
                       "recall_%": round(100 * len(idx & det) / max(len(idx), 1), 1),
                       "disparos_regra": len(det), "precisao_%": round(100 * len(idx & det) / max(len(det), 1), 1)}
    return {
        "simulado": True, "injetadas": len(gt_idx), "sinalizadas": len(pred_idx), "acertos": tp,
        "recall_%": round(100 * tp / len(gt_idx), 1), "precisao_%": round(100 * tp / max(len(pred_idx), 1), 1),
        "por_tipo": por_tipo,
        "nota": "Precisão baixa é esperada: a base normal também gera atipicidades legítimas (fim de exercício, eventos, "
                "hospitais 24h). Esse é o ponto: alerta ≠ irregularidade.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", action="append", default=[str(RAW / "cpgf_simulado.csv")])
    a = ap.parse_args()
    entradas = a.entrada[1:] if len(a.entrada) > 1 else a.entrada
    df, qualidade = limpar(ler(entradas))
    df = enriquecer(df)
    f, score, regras_txt, ctx, classe, hip = pontuar(df)
    df["score"], df["regras"], df["contexto"], df["classe"], df["hipoteses"] = score, regras_txt, ctx, classe, hip
    metricas = validar(df, f)
    compra_ = ~df.eh_saque & ~df.eh_estorno
    qualidade["fim_semana_em_unidade_24h_nao_sinalizado"] = int((compra_ & (df.data.dt.weekday >= 5) & (df.opera_24h == 1)).sum())
    qualidade["gasto_nov_dez_vs_media_demais_meses_%"] = round(float(
        (df[df.data.dt.month.isin([11, 12])].groupby("ano_mes").valor.sum().mean()
         / df[~df.data.dt.month.isin([11, 12])].groupby("ano_mes").valor.sum().mean() - 1) * 100), 1)
    pacote = agregar(df, f, qualidade, metricas)
    (OUT / "dashboard_data.json").write_text(json.dumps(pacote, ensure_ascii=False, default=str), encoding="utf-8")
    cols = ["data", "orgao_superior", "unidade", "tipo_unidade", "portador", "doc_favorecido", "favorecido", "ramo_atividade",
            "transacao", "valor", "score", "classe", "regras", "contexto"]
    df[cols].to_csv(OUT / "transacoes_classificadas.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    df[df.classe != "Sem indício"][cols + ["hipoteses"]].sort_values(["score", "valor"], ascending=False) \
        .to_csv(OUT / "fila_investigacao.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(json.dumps({"kpis": pacote["kpis"], "qualidade": qualidade, "validacao": metricas,
                      "classes": df.classe.value_counts().to_dict()}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
