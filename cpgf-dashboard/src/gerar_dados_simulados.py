"""
Gera uma base SIMULADA que imita o layout do CPGF (Cartão de Pagamento do Governo Federal)
publicado no Portal da Transparência.

ATENÇÃO: todos os órgãos, portadores, CPFs, CNPJs e favorecidos são FICTÍCIOS.
Nenhuma pessoa ou empresa real é representada.

Imita o formato real: CSV ';' , ISO-8859-1, decimal com vírgula, datas dd/mm/aaaa, CPF mascarado,
favorecido sigiloso / sem informação em saques, estornos negativos, linhas duplicadas e
mês de extrato diferente do mês da transação.

Também injeta anomalias com "gabarito" (data/raw/gabarito_anomalias.csv) para medir o detector,
e atipicidades LEGÍTIMAS (fim de exercício, hospital 24h, evento anual) para provar que
anomalia != irregularidade.

Uso:  python src/gerar_dados_simulados.py
"""
import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)
RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "raw"
SAIDA.mkdir(parents=True, exist_ok=True)

INICIO, FIM = "2025-01-01", "2026-09-30"
LIMITE_UNITARIO = 4000.00  # limite fictício por transação (parametrizável no detector)

# ---------------------------------------------------------------- dimensões
ORGAOS_SUP = {
    "10000": "Ministério Simulado da Saúde",
    "20000": "Ministério Simulado da Educação",
    "30000": "Ministério Simulado da Defesa",
    "40000": "Ministério Simulado da Justiça",
    "50000": "Ministério Simulado da Agricultura",
    "60000": "Ministério Simulado da Ciência",
    "70000": "Ministério Simulado da Fazenda",
    "80000": "Ministério Simulado do Meio Ambiente",
}
# tipo da unidade -> (rótulo, opera 24h/fim de semana?, volume médio mensal, ramos preferidos)
TIPOS = {
    "HOSPITAL":  ("Hospital Federal",      True,  95, ["Material médico-hospitalar", "Farmácia", "Alimentos e supermercado", "Combustível", "Limpeza e conservação"]),
    "FORCAS":    ("Comando Regional",      True,  80, ["Combustível", "Manutenção veicular", "Alimentos e supermercado", "Hospedagem", "Informática e eletrônicos"]),
    "EDUCACAO":  ("Instituto Federal",     False, 60, ["Material de escritório", "Informática e eletrônicos", "Serviços gráficos", "Alimentos e supermercado", "Limpeza e conservação"]),
    "PESQUISA":  ("Centro de Pesquisa",    False, 45, ["Informática e eletrônicos", "Material de laboratório", "Hospedagem", "Passagens e transporte", "Combustível"]),
    "ADMIN":     ("Superintendência",      False, 50, ["Material de escritório", "Combustível", "Hospedagem", "Passagens e transporte", "Serviços gráficos"]),
}
CIDADES = ["Alfa", "Beta", "Gama", "Delta", "Épsilon", "Zeta", "Eta", "Teta", "Iota", "Kappa",
           "Lambda", "Mi", "Ni", "Csi", "Ômicron", "Pi", "Rô", "Sigma", "Tau", "Ípsilon"]
RAMOS_MU = {  # mediana da compra (R$) por ramo
    "Combustível": 220, "Alimentos e supermercado": 310, "Material de escritório": 260,
    "Manutenção veicular": 680, "Hospedagem": 540, "Passagens e transporte": 470,
    "Limpeza e conservação": 240, "Informática e eletrônicos": 820,
    "Material médico-hospitalar": 640, "Farmácia": 190, "Serviços gráficos": 390,
    "Material de laboratório": 720,
}
NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gisele", "Hugo", "Iara", "João", "Karen",
         "Lucas", "Marta", "Nuno", "Olívia", "Paulo", "Quitéria", "Rafael", "Sara", "Tiago", "Úrsula",
         "Vitor", "Wanda", "Xavier", "Yara", "Zeca"]
SOBRENOMES = ["Almeida", "Barros", "Cardoso", "Dias", "Esteves", "Fontes", "Guedes", "Horta", "Ibrahim",
              "Jardim", "Klein", "Leal", "Moura", "Nogueira", "Ornelas", "Pires", "Queiroz", "Ramos",
              "Seixas", "Tavares", "Uchoa", "Valadares", "Xavier", "Zanetti"]
PREFIXOS_FAV = {
    "Combustível": ["Posto", "Auto Posto"], "Alimentos e supermercado": ["Supermercado", "Mercadinho", "Atacado"],
    "Material de escritório": ["Papelaria", "Comercial"], "Manutenção veicular": ["Oficina", "Auto Center"],
    "Hospedagem": ["Hotel", "Pousada"], "Passagens e transporte": ["Viagens", "Transportes"],
    "Limpeza e conservação": ["Distribuidora", "Higiene"], "Informática e eletrônicos": ["Tech", "Informática"],
    "Material médico-hospitalar": ["Hospitalar", "MedSupply"], "Farmácia": ["Farmácia", "Drogaria"],
    "Serviços gráficos": ["Gráfica", "Impressos"], "Material de laboratório": ["Lab", "Científica"],
}
SUF_FAV = ["Horizonte", "Central", "Estrela", "Vale Verde", "Progresso", "Nova Era", "Aliança", "Planalto",
           "Brasília Sim", "Sol Nascente", "Três Rios", "Boa Vista", "União", "Imperial", "Aurora", "Cruzeiro"]


def cpf_mascarado():
    d = RNG.integers(0, 10, 6)
    return f"***.{d[0]}{d[1]}{d[2]}.{d[3]}{d[4]}{d[5]}-**"


def cnpj_ficticio():
    d = RNG.integers(0, 10, 12)
    s = "".join(map(str, d))
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{RNG.integers(10, 99)}"


# unidades
unidades = []
cod_ug = 100001
orgao_cods = list(ORGAOS_SUP)
tipos_lista = (["HOSPITAL"] * 8 + ["FORCAS"] * 10 + ["EDUCACAO"] * 16 + ["PESQUISA"] * 8 + ["ADMIN"] * 18)
RNG.shuffle(tipos_lista)
for i, tipo in enumerate(tipos_lista):
    sup = orgao_cods[i % len(orgao_cods)]
    rot = TIPOS[tipo][0]
    unidades.append({
        "cod_sup": sup, "nome_sup": ORGAOS_SUP[sup],
        "cod_orgao": str(int(sup) + 1 + i % 5), "nome_orgao": f"{ORGAOS_SUP[sup].replace('Ministério Simulado', 'Órgão Sim.')} {i % 5 + 1}",
        "cod_ug": str(cod_ug + i), "nome_ug": f"{rot} {CIDADES[i % len(CIDADES)]} {i // len(CIDADES) + 1:02d} (SIM)",
        "tipo": tipo,
    })
unid = pd.DataFrame(unidades)

# portadores por unidade
portadores = {}
for u in unid.cod_ug:
    n = int(RNG.integers(3, 9))
    portadores[u] = [(cpf_mascarado(), f"{RNG.choice(NOMES)} {RNG.choice(SOBRENOMES)} {RNG.choice(SOBRENOMES)}".upper())
                     for _ in range(n)]

# favorecidos (fornecedores)
fav = []
for ramo, pref in PREFIXOS_FAV.items():
    for _ in range(int(RNG.integers(22, 45))):
        fav.append({"cnpj": cnpj_ficticio(), "ramo": ramo,
                    "nome": f"{RNG.choice(pref)} {RNG.choice(SUF_FAV)} {RNG.choice(['LTDA', 'ME', 'EIRELI', 'S/A'])}".upper()})
fav = pd.DataFrame(fav).drop_duplicates("cnpj").reset_index(drop=True)
fav_por_ramo = {r: g.index.to_numpy() for r, g in fav.groupby("ramo")}

# ---------------------------------------------------------------- transações normais
meses = pd.period_range(INICIO, FIM, freq="M")
EVENTOS = {}  # evento anual legítimo: (ug, mês) com gasto grande
for u in RNG.choice(unid[unid.tipo.isin(["EDUCACAO", "PESQUISA"])].cod_ug.to_numpy(), 4, replace=False):
    EVENTOS[(u, 9)] = "evento anual (congresso/semana acadêmica)"

linhas = []
for _, u in unid.iterrows():
    rot, h24, vol, ramos = TIPOS[u.tipo]
    pesos_ramo = np.array([0.34, 0.24, 0.18, 0.14, 0.10])
    for per in meses:
        mult = 1.0
        if per.month == 12:
            mult = 1.55           # fim de exercício: atipicidade LEGÍTIMA geral
        elif per.month == 1:
            mult = 0.6
        if (u.cod_ug, per.month) in EVENTOS:
            mult *= 2.3
        n = max(8, int(RNG.poisson(vol * mult * RNG.uniform(0.8, 1.2))))
        dias = per.days_in_month
        for _ in range(n):
            dia = int(RNG.integers(1, dias + 1))
            data = pd.Timestamp(per.year, per.month, dia)
            if data.weekday() >= 5 and not h24 and RNG.random() > 0.03:
                data = data - pd.Timedelta(days=data.weekday() - 4)  # administrativo: empurra para sexta
            if data.month != per.month:
                data = pd.Timestamp(per.year, per.month, 1)
                while data.weekday() >= 5 and not h24:
                    data += pd.Timedelta(days=1)
            ramo = RNG.choice(ramos, p=pesos_ramo)
            cpf, nome_p = portadores[u.cod_ug][int(RNG.integers(0, len(portadores[u.cod_ug])))]
            eh_saque = RNG.random() < 0.025
            if eh_saque:
                valor = round(float(np.clip(RNG.lognormal(np.log(260), 0.55), 50, 1500)) + RNG.integers(0, 99) / 100, 2)
                fcnpj, fnome, trans = "Sem informação", "Sem informação", RNG.choice(["SAQUE - CASH/ATM BB", "SAQUE - UNICA"])
            else:
                f = fav.loc[int(RNG.choice(fav_por_ramo[ramo]))]
                fcnpj, fnome = f.cnpj, f.nome
                valor = round(float(np.clip(RNG.lognormal(np.log(RAMOS_MU[ramo]), 0.62), 8, LIMITE_UNITARIO * 0.98)), 2)
                trans = "COMPRA A/V - R$ - APRES"
                if RNG.random() < 0.02:
                    fcnpj, fnome = "Sigiloso", "Sigiloso"
                elif RNG.random() < 0.008:
                    fnome = "Sem informação"
                if RNG.random() < 0.008:
                    valor = -valor  # estorno
            ext = pd.Period(data, "M") + (1 if RNG.random() < 0.3 else 0)
            linhas.append((u.cod_sup, u.nome_sup, u.cod_orgao, u.nome_orgao, u.cod_ug, u.nome_ug,
                           ext.year, ext.month, cpf, nome_p, fcnpj, fnome, trans, data, valor, ""))

cols = ["CÓDIGO ÓRGÃO SUPERIOR", "NOME ÓRGÃO SUPERIOR", "CÓDIGO ÓRGÃO", "NOME ÓRGÃO", "CÓDIGO UNIDADE GESTORA",
        "NOME UNIDADE GESTORA", "ANO EXTRATO", "MÊS EXTRATO", "CPF PORTADOR", "NOME PORTADOR",
        "CNPJ OU CPF FAVORECIDO", "NOME FAVORECIDO", "TRANSAÇÃO", "DATA TRANSAÇÃO", "VALOR TRANSAÇÃO", "_gt"]
df = pd.DataFrame(linhas, columns=cols)

# ---------------------------------------------------------------- anomalias injetadas (com gabarito)
inj = []
uid = unid.set_index("cod_ug")


def nova_linha(ug, data, valor, fav_row=None, saque=False, gt=""):
    u = uid.loc[ug]
    cpf, nome_p = portadores[ug][int(RNG.integers(0, len(portadores[ug])))]
    if saque:
        fc, fn, tr = "Sem informação", "Sem informação", "SAQUE - CASH/ATM BB"
    else:
        fc, fn, tr = fav_row.cnpj, fav_row.nome, "COMPRA A/V - R$ - APRES"
    ext = pd.Period(data, "M")
    return (u.cod_sup, u.nome_sup, u.cod_orgao, u.nome_orgao, ug, u.nome_ug, ext.year, ext.month,
            cpf, nome_p, fc, fn, tr, data, round(valor, 2), gt)


def dia_util(per, h24=False, fim_semana=False):
    while True:
        d = pd.Timestamp(per.year, per.month, int(RNG.integers(1, per.days_in_month + 1)))
        if fim_semana and d.weekday() >= 5:
            return d
        if not fim_semana and (h24 or d.weekday() < 5):
            return d


adm = unid[unid.tipo.isin(["ADMIN", "EDUCACAO", "PESQUISA"])].cod_ug.to_numpy()
h24s = unid[unid.tipo.isin(["HOSPITAL", "FORCAS"])].cod_ug.to_numpy()
todas = unid.cod_ug.to_numpy()

# 1) FRACIONAMENTO: 3-5 compras no mesmo dia, mesmo portador+favorecido, cada uma logo abaixo do limite
for _ in range(45):
    ug = RNG.choice(todas); per = RNG.choice(meses)
    f = fav.loc[int(RNG.integers(0, len(fav)))]; d = dia_util(per)
    cpf, nome_p = portadores[ug][0]
    for _ in range(int(RNG.integers(3, 6))):
        r = list(nova_linha(ug, d, RNG.uniform(0.80, 0.985) * LIMITE_UNITARIO, f, gt="FRACIONAMENTO"))
        r[8], r[9] = cpf, nome_p
        inj.append(tuple(r))
# 2) SAQUE REDONDO alto
for _ in range(40):
    ug = RNG.choice(todas); per = RNG.choice(meses)
    inj.append(nova_linha(ug, dia_util(per), float(RNG.choice([2000, 2500, 3000, 3500, 4000, 5000])), saque=True, gt="SAQUE_REDONDO"))
# 3) FIM DE SEMANA em unidade administrativa (não opera 24h)
for _ in range(55):
    ug = RNG.choice(adm); per = RNG.choice(meses)
    f = fav.loc[int(RNG.integers(0, len(fav)))]
    inj.append(nova_linha(ug, dia_util(per, fim_semana=True), RNG.uniform(400, 3500), f, gt="FIM_DE_SEMANA_ADM"))
# 4) VALOR EXTREMO (muito acima do típico do ramo)
for _ in range(35):
    ug = RNG.choice(todas); per = RNG.choice([m for m in meses if m.month not in (11, 12)])
    f = fav.loc[int(RNG.integers(0, len(fav)))]
    inj.append(nova_linha(ug, dia_util(per), RAMOS_MU[f.ramo] * RNG.uniform(14, 30), f, gt="VALOR_EXTREMO"))
# 5) CONCENTRAÇÃO em um favorecido numa unidade pequena
for ug in RNG.choice(adm, 5, replace=False):
    f = fav.loc[int(RNG.integers(0, len(fav)))]
    for per in RNG.choice(meses, 10, replace=False):
        for _ in range(int(RNG.integers(6, 12))):
            inj.append(nova_linha(ug, dia_util(per), RNG.uniform(500, 3400), f, gt="CONCENTRACAO"))
# 6) DUPLICIDADE (mesmo portador, favorecido, valor, data — pode ser erro de carga OU compra repetida legítima)
base_idx = RNG.choice(df.index[(df["VALOR TRANSAÇÃO"] > 300) & (df["TRANSAÇÃO"].str.startswith("COMPRA"))], 60, replace=False)
for i in base_idx:
    r = df.loc[i].copy(); r["_gt"] = "DUPLICIDADE"
    inj.append(tuple(r.values))

df = pd.concat([df, pd.DataFrame(inj, columns=cols)], ignore_index=True)
df = df[(df["DATA TRANSAÇÃO"] >= INICIO) & (df["DATA TRANSAÇÃO"] <= FIM)]
df = df.sort_values(["DATA TRANSAÇÃO", "CÓDIGO UNIDADE GESTORA"], kind="stable").reset_index(drop=True)
df["linha"] = np.arange(1, len(df) + 1)

# gabarito (linha = posição 1-based no CSV, sem contar o cabeçalho)
df.loc[df["_gt"] != "", ["linha", "CÓDIGO UNIDADE GESTORA", "DATA TRANSAÇÃO", "VALOR TRANSAÇÃO", "_gt"]].rename(
    columns={"_gt": "tipo_anomalia_injetada"}).to_csv(SAIDA / "gabarito_anomalias.csv", index=False, sep=";", decimal=",", encoding="utf-8")

# ---------------------------------------------------------------- escreve CSV no formato "portal"
raw = df.drop(columns=["_gt", "linha"]).copy()
raw["DATA TRANSAÇÃO"] = raw["DATA TRANSAÇÃO"].dt.strftime("%d/%m/%Y")
raw["VALOR TRANSAÇÃO"] = raw["VALOR TRANSAÇÃO"].map(lambda v: f"{v:.2f}".replace(".", ","))
raw.to_csv(SAIDA / "cpgf_simulado.csv", sep=";", index=False, encoding="latin-1", quoting=1)

# dimensão de fornecedores (na vida real viria do cruzamento CNPJ -> CNAE da Receita)
fav[["cnpj", "nome", "ramo"]].rename(columns={"cnpj": "cnpj_favorecido", "nome": "nome_favorecido", "ramo": "ramo_atividade"}) \
    .to_csv(SAIDA / "dim_favorecido_ramo.csv", sep=";", index=False, encoding="utf-8")
unid[["cod_ug", "tipo"]].rename(columns={"cod_ug": "cod_unidade_gestora", "tipo": "tipo_unidade"}) \
    .assign(opera_24h=lambda d: d.tipo_unidade.isin(["HOSPITAL", "FORCAS"]).astype(int)) \
    .to_csv(SAIDA / "dim_unidade_contexto.csv", sep=";", index=False, encoding="utf-8")
pd.DataFrame([{"cod_unidade_gestora": u, "mes": m, "motivo": t} for (u, m), t in EVENTOS.items()]) \
    .to_csv(SAIDA / "dim_eventos_legitimos.csv", sep=";", index=False, encoding="utf-8")

print(f"linhas: {len(raw):,}  | anomalias injetadas: {(df['_gt'] != '').sum()}  | período {INICIO} a {FIM}")
print(df["_gt"].replace("", "NORMAL").value_counts().to_string())
