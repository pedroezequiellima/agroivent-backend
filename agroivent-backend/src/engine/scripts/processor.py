from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text


@dataclass
class ProcessamentoConfig:
    projeto_id: str
    caminho_arquivo: str
    tipo_inventario: str
    fator_forma: float
    fator_empilhamento: float
    area_total_projeto: float
    area_parcela: float
    dmc: float
    database_url: str


_COLUNAS_MAP = {
    "nome_comum": ["nome comum", "nome_comum", "especie", "espécie"],
    "cap": ["cap", "circunferencia_peito", "circunferência_peito"],
    "cnb": ["cnb", "circunferencia_base", "circunferência_base"],
    "altura_comercial": ["altura_comercial", "altura", "h_comercial", "altura comercial"],
    "densidade_madeira": ["densidade", "densidade_madeira", "densidade básica", "densidade_basica"],
    "produto": ["produto", "destinacao", "destinação"],
    "coordenada_x": ["coordenada_x", "coord_x", "x", "longitude"],
    "coordenada_y": ["coordenada_y", "coord_y", "y", "latitude"],
    "parcela": ["parcela", "id_parcela", "talhao", "talao", "unidade_amostral"],
}


def _normalizar_nome_coluna(nome: str) -> str:
    return (
        str(nome)
        .strip()
        .lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("-", "_")
    )


def _resolver_coluna(df: pd.DataFrame, nome_canonico: str) -> str | None:
    aliases = {_normalizar_nome_coluna(x) for x in _COLUNAS_MAP.get(nome_canonico, [])}
    for coluna in df.columns:
        if _normalizar_nome_coluna(coluna) in aliases:
            return coluna
    return None


def _ler_planilha(path: str) -> pd.DataFrame:
    return pd.read_excel(path)


def _carregar_especies(engine) -> tuple[dict[str, dict[str, Any]], list[str]]:
    especies: dict[str, dict[str, Any]] = {}
    avisos: list[str] = []
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, nome_comum, nome_cientifico
                FROM especies
                """
            )
        ).mappings()
        for row in rows:
            nome_key = _normalizar_nome_coluna(row["nome_comum"] or "")
            especies[nome_key] = {
                "id": row["id"],
                "nome_cientifico": row["nome_cientifico"],
            }
    if not especies:
        avisos.append("Tabela especies vazia; normalizacao taxonomica nao aplicada.")
    return especies, avisos


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _classe_diametrica(dap: float) -> str:
    if dap < 20:
        return "I"
    if dap < 40:
        return "II"
    if dap < 60:
        return "III"
    if dap < 80:
        return "IV"
    return "V"


def _erro_amostral_percent(volume_por_parcela: pd.Series, probabilidade: float = 0.90) -> dict[str, float]:
    n = int(volume_por_parcela.shape[0])
    if n <= 1:
        return {
            "media": float(volume_por_parcela.mean()) if n else 0.0,
            "variancia": 0.0,
            "desvio_padrao": 0.0,
            "erro_amostragem": 0.0,
            "intensidade_amostral": n,
            "intensidade_recomendada": float(n),
        }

    media = float(volume_por_parcela.mean())
    variancia = float(volume_por_parcela.var(ddof=1))
    desvio = float(math.sqrt(variancia))
    erro_padrao = desvio / math.sqrt(n)
    alpha = 1 - probabilidade
    t_crit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    erro_abs = t_crit * erro_padrao
    erro_percent = (erro_abs / media * 100) if media > 0 else 0.0
    erro_admissivel = 0.20
    intensidade_recomendada = ((t_crit**2) * variancia) / ((erro_admissivel * media) ** 2) if media > 0 else float(n)
    return {
        "media": media,
        "variancia": variancia,
        "desvio_padrao": desvio,
        "erro_amostragem": erro_percent,
        "intensidade_amostral": n,
        "intensidade_recomendada": max(float(n), float(intensidade_recomendada)),
    }


def _agrupar_quadros(
    df_calc: pd.DataFrame,
    tipo_inventario: str,
    area_total_projeto: float,
    fc_parcela: float,
) -> dict[str, Any]:
    if tipo_inventario == "AMOSTRAGEM":
        fator_ha = fc_parcela
    else:
        fator_ha = 1.0 / max(area_total_projeto, 1.0)

    quadro_classes_df = (
        df_calc.groupby("classe_diametrica", as_index=False)
        .agg(
            n_individuos=("classe_diametrica", "count"),
            area_basal_g03_m2=("g_03", "sum"),
            area_basal_g13_m2=("g_13", "sum"),
            volume_real_m3=("volume_real", "sum"),
            volume_empilhado_st=("volume_st", "sum"),
            peso_verde_kg=("peso_verde", "sum"),
            peso_seco_kg=("peso_seco", "sum"),
        )
        .sort_values("classe_diametrica")
    )
    for coluna in [
        "n_individuos",
        "area_basal_g03_m2",
        "area_basal_g13_m2",
        "volume_real_m3",
        "volume_empilhado_st",
        "peso_verde_kg",
        "peso_seco_kg",
    ]:
        quadro_classes_df[f"{coluna}_ha"] = quadro_classes_df[coluna] * fator_ha

    quadro_especies_df = (
        df_calc.groupby(["nome_cientifico", "situacao"], as_index=False)
        .agg(
            n_individuos=("nome_cientifico", "count"),
            area_basal_g13_m2=("g_13", "sum"),
            volume_real_m3=("volume_real", "sum"),
            volume_empilhado_st=("volume_st", "sum"),
        )
        .sort_values(["nome_cientifico", "situacao"])
    )
    total_individuos = max(int(df_calc.shape[0]), 1)
    quadro_especies_df["percentual_individuos"] = (quadro_especies_df["n_individuos"] / total_individuos) * 100.0
    for coluna in ["n_individuos", "area_basal_g13_m2", "volume_real_m3", "volume_empilhado_st"]:
        quadro_especies_df[f"{coluna}_ha"] = quadro_especies_df[coluna] * fator_ha

    quadro_produtos_df = (
        df_calc.groupby("produto", as_index=False)
        .agg(
            volume_real_m3=("volume_real", "sum"),
            volume_empilhado_st=("volume_st", "sum"),
        )
        .sort_values("produto")
    )
    quadro_produtos_df["carvao_mdc_estimado"] = quadro_produtos_df["volume_empilhado_st"] * 0.7
    quadro_produtos_df["postes_m3_estimado"] = quadro_produtos_df["volume_real_m3"] * 0.15

    # Quadro fitossociologico (densidade, frequencia, dominancia e IVI)
    n_parcelas = max(int(df_calc["parcela"].nunique()), 1)
    fit_df = (
        df_calc.groupby("nome_cientifico", as_index=False)
        .agg(
            n_individuos=("nome_cientifico", "count"),
            area_basal_g13_m2=("g_13", "sum"),
            parcelas_ocorrencia=("parcela", "nunique"),
        )
        .sort_values("nome_cientifico")
    )
    fit_df["densidade_abs"] = fit_df["n_individuos"] * fator_ha
    soma_densidade_abs = max(float(fit_df["densidade_abs"].sum()), 1e-9)
    fit_df["densidade_rel"] = (fit_df["densidade_abs"] / soma_densidade_abs) * 100.0

    fit_df["frequencia_abs"] = (fit_df["parcelas_ocorrencia"] / n_parcelas) * 100.0
    soma_frequencia_abs = max(float(fit_df["frequencia_abs"].sum()), 1e-9)
    fit_df["frequencia_rel"] = (fit_df["frequencia_abs"] / soma_frequencia_abs) * 100.0

    fit_df["dominancia_abs"] = fit_df["area_basal_g13_m2"] * fator_ha
    soma_dominancia_abs = max(float(fit_df["dominancia_abs"].sum()), 1e-9)
    fit_df["dominancia_rel"] = (fit_df["dominancia_abs"] / soma_dominancia_abs) * 100.0

    fit_df["ivi"] = fit_df["densidade_rel"] + fit_df["frequencia_rel"] + fit_df["dominancia_rel"]
    fit_df = fit_df.sort_values("ivi", ascending=False)

    return {
        "quadro_classes_diametricas": quadro_classes_df.to_dict(orient="records"),
        "quadro_especies": quadro_especies_df.to_dict(orient="records"),
        "quadro_produtos_rcf": quadro_produtos_df.to_dict(orient="records"),
        "quadro_fitossociologico": fit_df.to_dict(orient="records"),
    }


def _exportar_resultados(
    projeto_id: str,
    tipo_inventario: str,
    memoria_calculo: dict[str, Any],
    quadros_cprh: dict[str, Any],
) -> dict[str, str]:
    base_dir = Path(__file__).resolve().parent / "outputs"
    base_dir.mkdir(parents=True, exist_ok=True)
    prefixo = f"{projeto_id}_{tipo_inventario.lower()}"

    memoria_path = base_dir / f"{prefixo}_memoria_calculo.json"
    quadros_path = base_dir / f"{prefixo}_quadros_cprh.json"
    memoria_path.write_text(json.dumps(memoria_calculo, ensure_ascii=False, indent=2), encoding="utf-8")
    quadros_path.write_text(json.dumps(quadros_cprh, ensure_ascii=False, indent=2), encoding="utf-8")

    export_paths: dict[str, str] = {
        "memoria_calculo_json": str(memoria_path),
        "quadros_cprh_json": str(quadros_path),
    }

    for nome_quadro, registros in quadros_cprh.items():
        csv_path = base_dir / f"{prefixo}_{nome_quadro}.csv"
        pd.DataFrame(registros).to_csv(csv_path, index=False, encoding="utf-8")
        export_paths[f"{nome_quadro}_csv"] = str(csv_path)

    return export_paths


def processar_inventario(config: ProcessamentoConfig) -> dict[str, Any]:
    engine = create_engine(config.database_url)
    df = _ler_planilha(config.caminho_arquivo)
    if df.empty:
        raise ValueError("Planilha vazia: nenhum registro para processar.")

    especies_map, avisos = _carregar_especies(engine)
    col_nome = _resolver_coluna(df, "nome_comum")
    col_cap = _resolver_coluna(df, "cap")
    col_cnb = _resolver_coluna(df, "cnb")
    col_altura = _resolver_coluna(df, "altura_comercial")
    col_densidade = _resolver_coluna(df, "densidade_madeira")
    col_produto = _resolver_coluna(df, "produto")
    col_x = _resolver_coluna(df, "coordenada_x")
    col_y = _resolver_coluna(df, "coordenada_y")
    col_parcela = _resolver_coluna(df, "parcela")

    if not col_cap or not col_altura:
        raise ValueError("Colunas obrigatorias ausentes: CAP e altura_comercial.")

    fc = 10000.0 / max(config.area_parcela, 1.0)
    arvores_insert: list[dict[str, Any]] = []
    registros_calculo: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        nome_comum = str(row[col_nome]).strip() if col_nome else ""
        cap = _to_float(row[col_cap], 0.0)
        cnb = _to_float(row[col_cnb], cap) if col_cnb else cap
        altura = _to_float(row[col_altura], 0.0)
        densidade = _to_float(row[col_densidade], 0.7) if col_densidade else 0.7
        produto = str(row[col_produto]).strip().lower() if col_produto else "lenha"
        coord_x = _to_float(row[col_x], None) if col_x else None
        coord_y = _to_float(row[col_y], None) if col_y else None

        if cap <= 0 or altura <= 0:
            avisos.append(f"Linha {idx + 2}: CAP/altura ausente ou invalido; linha ignorada.")
            continue

        dap = cap / math.pi
        dnb = cnb / math.pi
        g_13 = (math.pi * (dap ** 2)) / 40000.0
        g_03 = (math.pi * (dnb ** 2)) / 40000.0
        volume_cil = g_13 * altura
        volume_real = volume_cil * config.fator_forma
        volume_st = volume_real * config.fator_empilhamento
        peso_verde = volume_real * densidade * 1000.0
        peso_seco = peso_verde * 0.7

        especie = especies_map.get(_normalizar_nome_coluna(nome_comum), None)
        if not especie and nome_comum:
            avisos.append(
                f"Linha {idx + 2}: especie '{nome_comum}' nao encontrada; classificada como nao identificada."
            )
        especie_id = especie["id"] if especie else None
        nome_cientifico = especie["nome_cientifico"] if especie else "Especie Nao Identificada"

        classe = _classe_diametrica(dap)
        situacao = "EXPLORAR" if dap >= config.dmc else "REMANESCENTE"
        parcela_id = str(row[col_parcela]).strip() if col_parcela and not pd.isna(row[col_parcela]) else "P1"

        arvores_insert.append(
            {
                "projeto_id": config.projeto_id,
                "especie_id": especie_id,
                "cap": round(cap, 2),
                "altura_comercial": round(altura, 2),
                "volume_m3": round(volume_real, 4),
                "volume_estereo_st": round(volume_st, 4),
                "classe_diametrica": classe,
                "qualidade_fuste": 1,
                "situacao": situacao,
                "localizacao": f"SRID=4326;POINT({coord_x} {coord_y})" if coord_x is not None and coord_y is not None else None,
            }
        )
        registros_calculo.append(
            {
                "linha_planilha": int(idx + 2),
                "parcela": parcela_id,
                "nome_comum": nome_comum or "Nao informado",
                "nome_cientifico": nome_cientifico,
                "produto": produto or "lenha",
                "cap": cap,
                "cnb": cnb,
                "dap": dap,
                "dnb": dnb,
                "g_03": g_03,
                "g_13": g_13,
                "volume_cil": volume_cil,
                "volume_real": volume_real,
                "volume_st": volume_st,
                "peso_verde": peso_verde,
                "peso_seco": peso_seco,
                "classe_diametrica": classe,
                "situacao": situacao,
            }
        )

    if not arvores_insert:
        raise ValueError("Nenhuma arvore valida foi processada.")
    df_calc = pd.DataFrame(registros_calculo)
    volume_por_parcela = df_calc.groupby("parcela", as_index=False)["volume_real"].sum()
    volume_por_parcela_ha = volume_por_parcela["volume_real"] * fc

    with engine.begin() as conn:
        for arv in arvores_insert:
            conn.execute(
                text(
                    """
                    INSERT INTO arvores
                    (projeto_id, especie_id, cap, altura_comercial, volume_m3, volume_estereo_st, classe_diametrica, qualidade_fuste, situacao, localizacao)
                    VALUES
                    (:projeto_id, :especie_id, :cap, :altura_comercial, :volume_m3, :volume_estereo_st, :classe_diametrica, :qualidade_fuste, :situacao,
                    CASE WHEN :localizacao IS NULL THEN NULL ELSE ST_GeogFromText(:localizacao) END)
                    """
                ),
                arv,
            )

        if config.tipo_inventario == "AMOSTRAGEM":
            estat = _erro_amostral_percent(pd.Series(volume_por_parcela_ha), probabilidade=0.90)
        elif config.tipo_inventario == "CENSO_100":
            total_ha = max(config.area_total_projeto, 1.0)
            media_ha = sum(item["volume_m3"] for item in arvores_insert) / total_ha
            estat = {
                "media": media_ha,
                "variancia": 0.0,
                "desvio_padrao": 0.0,
                "erro_amostragem": 0.0,
                "intensidade_amostral": len(arvores_insert),
                "intensidade_recomendada": float(len(arvores_insert)),
            }
        else:  # RCF
            total_lenha = sum(
                r["volume_st"] for r in registros_calculo if str(r["produto"]).lower() in {"lenha", "carvao", "carvão"}
            )
            total_carvao = total_lenha * 0.7
            total_postes = sum(r["volume_real"] for r in registros_calculo if str(r["produto"]).lower() == "postes")
            estat = {
                "media": total_lenha,
                "variancia": total_carvao,
                "desvio_padrao": total_postes,
                "erro_amostragem": 0.0,
                "intensidade_amostral": len(arvores_insert),
                "intensidade_recomendada": float(len(arvores_insert)),
            }

        conn.execute(
            text(
                """
                INSERT INTO estatisticas_projeto
                (projeto_id, erro_amostragem, probabilidade, intensidade_amostral, media_volume_ha, variancia, desvio_padrao)
                VALUES
                (:projeto_id, :erro_amostragem, :probabilidade, :intensidade_amostral, :media_volume_ha, :variancia, :desvio_padrao)
                ON CONFLICT (projeto_id)
                DO UPDATE SET
                  erro_amostragem = EXCLUDED.erro_amostragem,
                  probabilidade = EXCLUDED.probabilidade,
                  intensidade_amostral = EXCLUDED.intensidade_amostral,
                  media_volume_ha = EXCLUDED.media_volume_ha,
                  variancia = EXCLUDED.variancia,
                  desvio_padrao = EXCLUDED.desvio_padrao
                """
            ),
            {
                "projeto_id": config.projeto_id,
                "erro_amostragem": round(float(estat["erro_amostragem"]), 2),
                "probabilidade": 0.90,
                "intensidade_amostral": int(estat["intensidade_amostral"]),
                "media_volume_ha": round(float(estat["media"]), 4),
                "variancia": round(float(estat["variancia"]), 8),
                "desvio_padrao": round(float(estat["desvio_padrao"]), 8),
            },
        )

    quadros = _agrupar_quadros(df_calc, config.tipo_inventario, config.area_total_projeto, fc)
    memoria_calculo = {
        "formulas": {
            "dap": "DAP = CAP / pi",
            "dnb": "DNB = CNB / pi",
            "g03": "G0,3 = (pi * DNB^2) / 40000",
            "g13": "G1,3 = (pi * DAP^2) / 40000",
            "volume_cilindrico": "Vcil = G1,3 * H",
            "volume_real": "Vreal = Vcil * fator_forma",
            "volume_empilhado": "Vst = Vreal * fator_empilhamento",
            "conversao_hectare": "fc = 10000 / area_parcela",
            "erro_amostragem": "E% = (t * (s/sqrt(n)) / media) * 100",
        },
        "amostra_linhas": df_calc.head(25).to_dict(orient="records"),
    }
    arquivos_exportados = _exportar_resultados(
        projeto_id=config.projeto_id,
        tipo_inventario=config.tipo_inventario,
        memoria_calculo=memoria_calculo,
        quadros_cprh=quadros,
    )

    return {
        "status": "ok",
        "projeto_id": config.projeto_id,
        "tipo_inventario": config.tipo_inventario,
        "arvores_processadas": len(arvores_insert),
        "erro_amostragem_aprovado": (float(estat["erro_amostragem"]) <= 20.0),
        "estatistica": estat,
        "memoria_calculo": memoria_calculo,
        "quadros_cprh": quadros,
        "arquivos_exportados": arquivos_exportados,
        "avisos": avisos,
    }
