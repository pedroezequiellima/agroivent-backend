"""
Processor.py - Motor de Processamento de Inventário Florestal
================================================================================
Este módulo processa planilhas de inventário florestal e persiste os dados
no PostgreSQL. Foi projetado para ser resiliente a erros e performático.

PRINCÍPIOS DE DESIGN:
- Clean Code: funções pequenas, nomes descritivos, responsabilidade única
- Robustez: nenhuma linha inválida quebra o processo inteiro
- Performance: bulk inserts, transações únicas, processamento em memória
- Segurança: sanitização de dados antes do envio ao banco

INTEGRAÇÃO COM NESTJS:
Para executar este script no contexto assíncrono do NestJS, utilize o padrão
de spawn de processo secundário:

```typescript
// No seu serviço NestJS
import { spawn } from 'child_process';

async function processarPlanilha(config: ProcessamentoConfig) {
  return new Promise((resolve, reject) => {
    const python = spawn('python', [
      'src/engine/scripts/processor.py',
      JSON.stringify(config)
    ], {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONPATH: './src/engine/scripts' }
    });

    let output = '';
    python.stdout.on('data', (data) => output += data);
    python.stderr.on('data', (data) => console.error(data));
    python.on('close', (code) => {
      if (code === 0) resolve(JSON.parse(output));
      else reject(new Error(`Processo falhou com código ${code}`));
    });
  });
}
```

Isso evita bloquear a thread principal do event loop do Node.js.
================================================================================
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text


# =============================================================================
# CONFIGURAÇÃO DO PROCESSAMENTO
# =============================================================================

@dataclass
class ProcessamentoConfig:
    """
    Configuração para processamento de inventário florestal.
    
    Atributos:
        projeto_id: Identificador único do projeto no banco
        caminho_arquivo: Path absoluto para a planilha Excel
        tipo_inventario: Tipo de inventário (AMOSTRAGEM, CENSO_100, RCF)
        fator_forma: Fator de forma para conversão volume cilíndrico -> real
                     Padrão: 0.7 (média para espécies tropicais)
        fator_empilhamento: Fator para conversão m³ -> stéreo (empilhado)
                           Padrão: 0.6 (varia por espécie e formato)
        area_total_projeto: Área total do projeto em hectares
        area_parcela: Área de cada parcela amostral em m²
        dmc: Diâmetro mínimo de corte (cm)
        tipo_referencia_dmc: Referência para DMC (CAP ou DAP)
        database_url: URL de conexão PostgreSQL (asyncpg format)
    """
    projeto_id: str
    caminho_arquivo: str
    tipo_inventario: str
    fator_forma: float
    fator_empilhamento: float
    area_total_projeto: float
    area_parcela: float
    dmc: float
    tipo_referencia_dmc: str
    database_url: str


# =============================================================================
# MAPEAMENTO DE COLUNAS (ROBUSTEZ)
# =============================================================================

# Dicionário de mapeamento: nome canônico -> aliases aceitos
# A lógica de resolução é case-insensitive e trata acentos
_COLUNAS_MAP = {
    # Identificação da árvore
    "arvore": [
        "ARVORE", "ÁRVORE", "Nº ÁRVORE", "Nº", "N", "COD", 
        "CODIGO", "CÓDIGO", "ID", "NUMERO", "NÚMERO"
    ],
    
    # Nome comum (nome popular da espécie)
    "nome_comum": [
        "NOME COMUM", "ESPECIE", "ESPÉCIE", "NOME", "SPP", 
        "ESPÉCIE BOTÂNICA", "DENOMINAÇÃO"
    ],
    
    # Parcela/Unidade Amostral
    "parcela": [
        "UA", "PARCELA", "P", "UNIDADE AMOSTRAL", "PP", 
        "TALHAO", "TALHÃO", "TALHÃO", "PARCELA"
    ],
    
    # --- Medidas Dendrométricas ---
    
    # Circunferência a 1,30m (Peito)
    "cap": [
        "CAP", "C1,3", "CIRCUNFERENCIA", "CIRCUNFERÊNCIA", 
        "CIRCUF. PEITO", "CIRCUNFERÊNCIA A 1,30M"
    ],
    
    # Diâmetro a 1,30m (calculado a partir do CAP)
    "dap": [
        "DAP", "D1,3", "DIAMETRO", "DIÂMETRO", 
        "DIAM. PEITO", "DIÂMETRO A 1,30M"
    ],
    
    # Circunferência a 0,30m (Base) - opcional
    "cnb": [
        "CNB", "CAB", "C0,3", "CIRCUNFERENCIA BASE", 
        "CIRCUNFERÊNCIA A 0,30M"
    ],
    
    # Diâmetro a 0,30m (calculado)
    "dnb": [
        "DNB", "D0,3", "DIAMETRO BASE", 
        "DIÂMETRO A 0,30M"
    ],
    
    # --- Alturas ---
    
    # Altura total (tronco + copa) - usada como fallback
    "altura_total": [
        "HT", "HTOTAL", "H", "ALTURA TOTAL", "ALTURA TOTAL (M)"
    ],
    
    # Altura comercial (tronco utilizável) - preferencial
    "altura_comercial": [
        "HC", "HCOM", "ALTURA DO FUSTE", "ALTURA COMERCIAL",
        "ALTURA COMERCIAL (M)", "H COMERCIAL"
    ],
    
    # --- Qualidade e Situação ---
    
    "qualidade_fuste": [
        "QF", "F", "FORMA", "QUALIDADE", "QUALIDADE DO FUSTE"
    ],
    
    "situacao": [
        "SITUAÇÃO", "SITUACAO", "SIT", "VITALIDADE", "STATUS"
    ],
    
    # --- Produto ---
    
    "produto": [
        "PRODUTO", "DESTINACAO", "DESTINAÇÃO", "USO", 
        "DESTINO", "TIPO PRODUTO"
    ],
    
    "densidade_madeira": [
        "DENSIDADE", "DENSIDADE_MADEIRA", "DENS", 
        "DENSIDADE (G/CM³)", "DENSIDADE BASIC"
    ],
    
    # --- Geolocalização ---
    
    "coordenada_x": [
        "X", "LONGITUDE", "COORD_X", "EASTING", "E"
    ],
    
    "coordenada_y": [
        "Y", "LATITUDE", "COORD_Y", "NORTHING", "N"
    ],
}


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def _normalizar_nome_coluna(nome: str) -> str:
    """
    Normaliza nome de coluna para busca case-insensitive.
    
    Tratamentos aplicados:
    - Remoção de espaços extras
    - Conversão para minúsculas
    - Substituição de caracteres especiais (acentos, ç)
    - Substituição de hífens por underscore
    
    Args:
        nome: Nome original da coluna
        
    Returns:
        Nome normalizado para comparação
    """
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


def _resolver_coluna(df: pd.DataFrame, nome_canonico: str) -> Optional[str]:
    """
    Resolve o nome real da coluna na planilha dado o nome canônico.
    
    O algoritmo verifica cada alias possível até encontrar uma correspondência.
    Isso permite que planilhas de diferentes formatos sejam processadas.
    
    Args:
        df: DataFrame pandas com os dados da planilha
        nome_canonico: Nome canônico da coluna (chave do _COLUNAS_MAP)
        
    Returns:
        Nome da coluna encontrada ou None se não existir
    """
    aliases = {_normalizar_nome_coluna(x) for x in _COLUNAS_MAP.get(nome_canonico, [])}
    for coluna in df.columns:
        if _normalizar_nome_coluna(coluna) in aliases:
            return coluna
    return None


def _ler_planilha(path: str) -> pd.DataFrame:
    """
    Lê planilha Excel detectando automaticamente o cabeçalho.
    
    O algoritmo varre as primeiras 15 linhas em busca de termos que indicam
    o cabeçalho real (CAP, DAP, ALTURA, UA, PARCELA).
    
    Args:
        path: Caminho absoluto para o arquivo Excel
        
    Returns:
        DataFrame com os dados da planilha
    """
    # Lê apenas as primeiras 15 linhas para localizar o cabeçalho
    preview = pd.read_excel(path, header=None, nrows=15)
    
    # Termos que indicam cabeçalho real
    termos_chave = ["CAP", "DAP", "ALTURA", "UA", "PARCELA"]
    
    linha_cabecalho = 0
    for i, row in preview.iterrows():
        celulas = [str(c).upper().strip() for c in row.values]
        if any(termo in celulas for termo in termos_chave):
            linha_cabecalho = i
            break
            
    df = pd.read_excel(path, header=linha_cabecalho)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _carregar_especies(engine) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """
    Carrega espécies do banco para normalização taxonômica.
    
    Args:
        engine: SQLAlchemy engine conectado ao PostgreSQL
        
    Returns:
        Tupla com (mapeamento de espécies, lista de avisos)
    """
    especies: dict[str, dict[str, Any]] = {}
    avisos: list[str] = []
    
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, nome_comum, nome_cientifico FROM especies")
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
    """
    Converte valor para float de forma segura, evitando NaN e None.
    
    SANITIZAÇÃO PARA O BANCO:
    - Converte NaN do Pandas para default
    - Converte None para default
    - Converte strings vazias para default
    - Substitui vírgula por ponto (formato brasileiro)
    - Remove espaços extras
    
    Args:
        value: Valor a converter
        default: Valor padrão se conversão falhar
        
    Returns:
        Float seguro para envio ao banco
    """
    try:
        if pd.isna(value):
            return default
        
        # Sanitização: remove espaços, substitui vírgula por ponto
        str_value = str(value).strip()
        str_value = re.sub(r'\s+', '', str_value)  # Remove todos os espaços
        str_value = str_value.replace(",", ".")
        
        # Verifica se é um valor válido
        if not str_value or str_value.lower() in ["", "nan", "none", "null", "na"]:
            return default
            
        return float(str_value)
    except (ValueError, TypeError):
        return default


def _sanitizar_string(value: Any, default: str = "") -> str:
    """
    Sanitiza valores de string para o banco, evitando None e vazios.
    
    Args:
        value: Valor a sanitizar
        default: Valor padrão se vazio
        
    Returns:
        String segura para o banco
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    return str(value).strip()


def _classe_diametrica(dap: float) -> str:
    """
    Classifica o DAP em classes diamétricas padrão.
    
    Classes:
        I:  < 20 cm
        II: 20-40 cm
        III: 40-60 cm
        IV:  60-80 cm
        V:  > 80 cm
        
    Args:
        dap: Diâmetro a 1,30m em cm
        
    Returns:
        Letra da classe diamétrica
    """
    if dap < 20:
        return "I"
    if dap < 40:
        return "II"
    if dap < 60:
        return "III"
    if dap < 80:
        return "IV"
    return "V"


def _erro_amostral_percent(
    volume_por_parcela: pd.Series, 
    probabilidade: float = 0.90
) -> dict[str, float]:
    """
    Calcula erro amostral para inventário por amostragem.
    
    Fórmula: E% = (t * s / √n) / x̄ * 100
    
    Onde:
    - t = valor crítico da distribuição t de Student
    - s = desvio padrão
    - n = número de parcelas
    - x̄ = média
    
    Args:
        volume_por_parcela: Série com volumes por parcela
        probabilidade: Nível de confiança (padrão 90%)
        
    Returns:
        Dicionário com estatísticas amostrais
    """
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
    
    # Distribuição t de Student para n-1 graus de liberdade
    alpha = 1 - probabilidade
    t_crit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    
    erro_abs = t_crit * erro_padrao
    erro_percent = (erro_abs / media * 100) if media > 0 else 0.0
    
    # Erro admissível de 20% (padrão para inventários florestais)
    erro_admissivel = 0.20
    intensidade_recomendada = (
        ((t_crit**2) * variancia) / ((erro_admissivel * media) ** 2)
        if media > 0 else float(n)
    )
    
    return {
        "media": media,
        "variancia": variancia,
        "desvio_padrao": desvio,
        "erro_amostragem": erro_percent,
        "intensidade_amostral": n,
        "intensidade_recomendada": max(float(n), float(intensidade_recomendada)),
    }


def _formatar_geolocalizacao(x: Optional[float], y: Optional[float]) -> Optional[str]:
    """
    Formata coordenadas para WKT (Well-Known Text) do PostGIS.
    
    Validações:
    - Verifica se ambas coordenadas existem
    - Verifica se estão em range válido (Brasil: lat -33 a 5, lon -73 a -34)
    - Formata como POINT WKT
    
    Args:
        x: Longitude
        y: Latitude
        
    Returns:
        String WKT ou None se inválido
    """
    # Verifica se ambas coordenadas são válidas
    if x is None or y is None:
        return None
    
    # Valida range aproximado do Brasil
    if not (-73 <= x <= -34 and -33 <= y <= 5):
        return None
    
    try:
        return f"SRID=4326;POINT({x} {y})"
    except (ValueError, TypeError):
        return None


def _agrupar_quadros(
    df_calc: pd.DataFrame,
    tipo_inventario: str,
    area_total_projeto: float,
    fc_parcela: float,
) -> dict[str, Any]:
    """
    Agrupa dados em quadros estatísticos (CPRH).
    
    Quadros gerados:
    - Classes Diamétricas: distribuição por classe de DAP
    - Espécies: distribuição por espécie e situação
    - Produtos RCF: estimativas por tipo de produto
    - Fitossociológico: densidade, frequência, dominância, IVI
    
    Args:
        df_calc: DataFrame com registros calculados
        tipo_inventario: Tipo de inventário
        area_total_projeto: Área total em hectares
        fc_parcela: Fator de conversão por hectare
        
    Returns:
        Dicionário com todos os quadros
    """
    # Fator hectare conforme tipo de inventário
    if tipo_inventario == "AMOSTRAGEM":
        fator_ha = fc_parcela
    else:
        fator_ha = 1.0 / max(area_total_projeto, 1.0)

    # --- Quadro de Classes Diamétricas ---
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
        "n_individuos", "area_basal_g03_m2", "area_basal_g13_m2",
        "volume_real_m3", "volume_empilhado_st", "peso_verde_kg", "peso_seco_kg"
    ]:
        quadro_classes_df[f"{coluna}_ha"] = quadro_classes_df[coluna] * fator_ha

    # --- Quadro de Espécies ---
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
    quadro_especies_df["percentual_individuos"] = (
        quadro_especies_df["n_individuos"] / total_individuos
    ) * 100.0
    
    for coluna in ["n_individuos", "area_basal_g13_m2", "volume_real_m3", "volume_empilhado_st"]:
        quadro_especies_df[f"{coluna}_ha"] = quadro_especies_df[coluna] * fator_ha

    # --- Quadro de Produtos RCF ---
    quadro_produtos_df = (
        df_calc.groupby("produto", as_index=False)
        .agg(
            volume_real_m3=("volume_real", "sum"),
            volume_empilhado_st=("volume_st", "sum"),
        )
        .sort_values("produto")
    )
    
    # Fatores de conversão empíricos para produtos florestais
    # Carvão: 70% do volume empilhado (perda por carbonização)
    # Postes: 15% do volume real (seleção de toras)
    quadro_produtos_df["carvao_mdc_estimado"] = quadro_produtos_df["volume_empilhado_st"] * 0.7
    quadro_produtos_df["postes_m3_estimado"] = quadro_produtos_df["volume_real_m3"] * 0.15

    # --- Quadro Fitossociológico (IVI) ---
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
    
    # Densidade absoluta e relativa
    fit_df["densidade_abs"] = fit_df["n_individuos"] * fator_ha
    soma_densidade_abs = max(float(fit_df["densidade_abs"].sum()), 1e-9)
    fit_df["densidade_rel"] = (fit_df["densidade_abs"] / soma_densidade_abs) * 100.0

    # Frequência absoluta e relativa
    fit_df["frequencia_abs"] = (fit_df["parcelas_ocorrencia"] / n_parcelas) * 100.0
    soma_frequencia_abs = max(float(fit_df["frequencia_abs"].sum()), 1e-9)
    fit_df["frequencia_rel"] = (fit_df["frequencia_abs"] / soma_frequencia_abs) * 100.0

    # Dominância absoluta e relativa
    fit_df["dominancia_abs"] = fit_df["area_basal_g13_m2"] * fator_ha
    soma_dominancia_abs = max(float(fit_df["dominancia_abs"].sum()), 1e-9)
    fit_df["dominancia_rel"] = (fit_df["dominancia_abs"] / soma_dominancia_abs) * 100.0

    # Índice de Valor de Importância (IVI)
    # IVI = Densidade Relativa + Frequência Relativa + Dominância Relativa
    fit_df["ivi"] = (
        fit_df["densidade_rel"] + 
        fit_df["frequencia_rel"] + 
        fit_df["dominancia_rel"]
    )
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
    """
    Exporta resultados para JSON e CSV.
    
    Args:
        projeto_id: ID do projeto
        tipo_inventario: Tipo de inventário
        memoria_calculo: Dicionário com fórmulas e amostra
        quadros_cprh: Quadros estatísticos
        
    Returns:
        Dicionário com caminhos dos arquivos exportados
    """
    base_dir = Path(__file__).resolve().parent / "outputs"
    base_dir.mkdir(parents=True, exist_ok=True)
    prefixo = f"{projeto_id}_{tipo_inventario.lower()}"

    # Exporta JSONs
    memoria_path = base_dir / f"{prefixo}_memoria_calculo.json"
    quadros_path = base_dir / f"{prefixo}_quadros_cprh.json"
    
    memoria_path.write_text(
        json.dumps(memoria_calculo, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )
    quadros_path.write_text(
        json.dumps(quadros_cprh, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )

    export_paths: dict[str, str] = {
        "memoria_calculo_json": str(memoria_path),
        "quadros_cprh_json": str(quadros_path),
    }

    # Exporta CSVs
    for nome_quadro, registros in quadros_cprh.items():
        csv_path = base_dir / f"{prefixo}_{nome_quadro}.csv"
        pd.DataFrame(registros).to_csv(csv_path, index=False, encoding="utf-8")
        export_paths[f"{nome_quadro}_csv"] = str(csv_path)

    return export_paths


def processar_inventario(config: ProcessamentoConfig) -> dict[str, Any]:
    """
    Processa inventário florestal a partir de planilha Excel.
    
    FLUXO DE PROCESSAMENTO:
    1. Ler planilha e detectar cabeçalho
    2. Mapear colunas da planilha para nomes canônicos
    3. Para cada linha:
       a. Validar dados críticos (CAP, Altura)
       b. Aplicar fallback de altura (HC → HT)
       c. Calcular métricas dendrométricas
       d. Classificar espécie e situação
       e. Adicionar à lista de inserção
    4. Bulk insert no PostgreSQL
    5. Calcular estatísticas
    6. Gerar quadros CPRH
    7. Exportar resultados
    
    RESILIÊNCIA:
    - Se 1 de 1000 árvores falhar, as 999 restantes são salvas
    - Erros são registrados em lista de avisos
    - Retorno sempre contém status e dados calculados
    
    Args:
        config: Configuração do processamento
        
    Returns:
        Dicionário com resultado estruturado em JSON
    """
    engine = create_engine(config.database_url)
    
    # --- Etapa 1: Leitura da Planilha ---
    df = _ler_planilha(config.caminho_arquivo)
    if df.empty:
        raise ValueError("Planilha vazia: nenhum registro para processar.")

    # --- Etapa 2: Mapeamento de Colunas ---
    especies_map, avisos = _carregar_especies(engine)
    
    col_nome = _resolver_coluna(df, "nome_comum")
    col_cap = _resolver_coluna(df, "cap")
    col_cnb = _resolver_coluna(df, "cnb")
    col_altura_com = _resolver_coluna(df, "altura_comercial")
    col_altura_total = _resolver_coluna(df, "altura_total")
    col_densidade = _resolver_coluna(df, "densidade_madeira")
    col_produto = _resolver_coluna(df, "produto")
    col_x = _resolver_coluna(df, "coordenada_x")
    col_y = _resolver_coluna(df, "coordenada_y")
    col_parcela = _resolver_coluna(df, "parcela")

    # Validação de colunas obrigatórias
    colunas_obrigatorias = {
        "CAP": col_cap,
        "ALTURA": col_altura_com or col_altura_total,  # Aceita qualquer altura
        "PARCELA": col_parcela,
    }

    faltando = [nome for nome, col in colunas_obrigatorias.items() if not col]
    if faltando:
        raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(faltando)}")

    # --- Etapa 3: Processamento das Árvores ---
    fc = 10000.0 / max(config.area_parcela, 1.0)
    arvores_insert: list[dict[str, Any]] = []
    registros_calculo: list[dict[str, Any]] = []
    
    # Contadores para feedback
    total_linhas = len(df)
    linhas_processadas = 0
    linhas_descartadas = 0

    for idx, row in df.iterrows():
        # Extração de dados com sanitização
        nome_comum = _sanitizar_string(row[col_nome]) if col_nome else ""
        cap = _to_float(row[col_cap], 0.0)
        cnb = _to_float(row[col_cnb], cap) if col_cnb else cap
        
        # --- FALLBACK DE ALTURA ---
        # Preferência: altura comercial (HC) → altura total (HT)
        altura_comercial = _to_float(row[col_altura_com], 0.0) if col_altura_com else 0.0
        altura_total = _to_float(row[col_altura_total], 0.0) if col_altura_total else 0.0
        altura = altura_comercial if altura_comercial > 0 else altura_total
        
        densidade = _to_float(row[col_densidade], 0.7) if col_densidade else 0.7
        produto = _sanitizar_string(row[col_produto], "lenha") if col_produto else "lenha"
        
        # Coordenadas com validação
        coord_x = _to_float(row[col_x], None) if col_x else None
        coord_y = _to_float(row[col_y], None) if col_y else None

        # --- VALIDAÇÃO CRÍTICA ---
        # Separa validation errors para debug preciso
        if cap <= 0:
            avisos.append(
                f"Linha {idx + 2}: CAP ausente ou invalido (CAP={cap}); linha ignorada."
            )
            linhas_descartadas += 1
            continue
            
        if altura <= 0:
            avisos.append(
                f"Linha {idx + 2}: ALTURA ausente ou invalida "
                f"(HC={altura_comercial}, HT={altura_total}); linha ignorada."
            )
            linhas_descartadas += 1
            continue

        # --- Cálculos Dendrométricos ---
        # DAP = CAP / π (conversão de circunferência para diâmetro)
        dap = cap / math.pi
        dnb = cnb / math.pi
        
        # Área basal (G) = π * d² / 40000 (converte cm² para m²)
        g_13 = (math.pi * (dap ** 2)) / 40000.0
        g_03 = (math.pi * (dnb ** 2)) / 40000.0
        
        # Volume cilíndrico = G1,3 * altura
        volume_cil = g_13 * altura
        
        # Volume real = Volume cilíndrico * fator de forma
        # Fator de forma 0.7 é média para espécies tropicais
        volume_real = volume_cil * config.fator_forma
        
        # Volume estere (empilhado) = Volume real * fator empilhamento
        volume_st = volume_real * config.fator_empilhamento
        
        # Pesos (verde e seco)
        peso_verde = volume_real * densidade * 1000.0  # kg
        peso_seco = peso_verde * 0.7  # Estimativa: 70% do peso verde

        # --- Normalização de Espécie ---
        especie = especies_map.get(_normalizar_nome_coluna(nome_comum), None)
        if not especie and nome_comum:
            avisos.append(
                f"Linha {idx + 2}: especie '{nome_comum}' nao encontrada; "
                f"classificada como nao identificada."
            )
        
        especie_id = especie["id"] if especie else None
        nome_cientifico = (
            especie["nome_cientifico"] if especie else "Especie Nao Identificada"
        )

        # --- Classificação ---
        classe = _classe_diametrica(dap)
        
        # DMC pode ser baseado em CAP ou DAP conforme configuração
        if config.tipo_referencia_dmc == "CAP":
            valor_referencia = cap
        else:
            valor_referencia = dap
            
        if valor_referencia is None or valor_referencia <= 0:
            avisos.append(f"Linha {idx + 2}: valor de referencia invalido; linha ignorada.")
            continue
            
        situacao = "EXPLORAR" if valor_referencia >= config.dmc else "REMANESCENTE"
        parcela_id = (
            _sanitizar_string(row[col_parcela]) if col_parcela else "P1"
        )

        # --- Geolocalização Segura ---
        localizacao = _formatar_geolocalizacao(coord_x, coord_y)

        # --- Preparação para Bulk Insert ---
        arvores_insert.append({
            "projeto_id": config.projeto_id,
            "especie_id": especie_id,
            "cap": round(cap, 2),
            "altura_comercial": round(altura, 2),
            "volume_m3": round(volume_real, 4),
            "volume_estereo_st": round(volume_st, 4),
            "classe_diametrica": classe,
            "qualidade_fuste": 1,  # Padrão: boa qualidade
            "situacao": situacao,
            "localizacao": localizacao,
        })
        
        # --- Registro para Cálculos ---
        registros_calculo.append({
            "linha_planilha": int(idx + 2),
            "parcela": parcela_id,
            "nome_comum": nome_comum or "Nao informado",
            "nome_cientifico": nome_cientifico,
            "produto": produto,
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
        })
        
        linhas_processadas += 1

    # --- Validação de Resultado ---
    print(f"DEBUG: Total de linhas lidas: {total_linhas}")
    print(f"DEBUG: Linhas processadas: {linhas_processadas}")
    print(f"DEBUG: Linhas descartadas: {linhas_descartadas}")
    print(f"DEBUG: Colunas encontradas: {df.columns.tolist()}")
    
    if not arvores_insert:
        raise ValueError(
            f"Nenhuma arvore valida foi processada. "
            f"Total: {total_linhas}, Descartadas: {linhas_descartadas}"
        )

    # --- Etapa 4: Bulk Insert no Banco ---
    df_calc = pd.DataFrame(registros_calculo)
    volume_por_parcela = df_calc.groupby("parcela", as_index=False)["volume_real"].sum()
    volume_por_parcela_ha = volume_por_parcela["volume_real"] * fc

    # Transação única para garantir atomicidade
    with engine.begin() as conn:
        # Bulk Insert: uma única query para todas as árvores
        # OTIMIZAÇÃO: executemany para performance
        if arvores_insert:
            conn.execute(
                text(
                    """
                    INSERT INTO arvores
                    (projeto_id, especie_id, cap, altura_comercial, volume_m3, 
                     volume_estereo_st, classe_diametrica, qualidade_fuste, situacao, localizacao)
                    VALUES
                    (:projeto_id, :especie_id, :cap, :altura_comercial, :volume_m3, 
                     :volume_estereo_st, :classe_diametrica, :qualidade_fuste, :situacao,
                    CASE WHEN :localizacao IS NULL THEN NULL ELSE ST_GeogFromText(:localizacao) END)
                    """
                ),
                arvores_insert,
            )

        # --- Cálculo de Estatísticas por Tipo de Inventário ---
        if config.tipo_inventario == "AMOSTRAGEM":
            estat = _erro_amostral_percent(
                pd.Series(volume_por_parcela_ha), 
                probabilidade=0.90
            )
        elif config.tipo_inventario == "CENSO_100":
            # Census: não há erro amostral, usa totais diretos
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
        else:  # RCF (Relação Custo-Fertilidade)
            # Calcula totais por produto
            total_lenha = sum(
                r["volume_st"] for r in registros_calculo 
                if str(r["produto"]).lower() in {"lenha", "carvao", "carvão"}
            )
            total_carvao = total_lenha * 0.7
            total_postes = sum(
                r["volume_real"] for r in registros_calculo 
                if str(r["produto"]).lower() == "postes"
            )
            estat = {
                "media": total_lenha,
                "variancia": total_carvao,
                "desvio_padrao": total_postes,
                "erro_amostragem": 0.0,
                "intensidade_amostral": len(arvores_insert),
                "intensidade_recomendada": float(len(arvores_insert)),
            }

        # --- Inserção de Estatísticas ---
        conn.execute(
            text(
                """
                INSERT INTO estatisticas_projeto
                (projeto_id, erro_amostragem, probabilidade, intensidade_amostral, 
                 media_volume_ha, variancia, desvio_padrao)
                VALUES
                (:projeto_id, :erro_amostragem, :probabilidade, :intensidade_amostral, 
                 :media_volume_ha, :variancia, :desvio_padrao)
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

    # --- Etapa 5: Geração de Quadros ---
    quadros = _agrupar_quadros(
        df_calc, 
        config.tipo_inventario, 
        config.area_total_projeto, 
        fc
    )
    
    # --- Etapa 6: Memória de Cálculo ---
    memoria_calculo = {
        "formulas": {
            "dap": "DAP = CAP / pi",
            "dnb": "DNB = CNB / pi",
            "g03": "G0,3 = (pi * DNB^2) / 40000",
            "g13": "G1,3 = (pi * DAP^2) / 40000",
            "volume_cilindrico": "Vcil = G1,3 * H",
            "volume_real": "Vreal = Vcil * fator_forma (0.7)",
            "volume_empilhado": "Vst = Vreal * fator_empilhamento (0.6)",
            "conversao_hectare": "fc = 10000 / area_parcela",
            "erro_amostragem": "E% = (t * s / sqrt(n)) / media * 100",
        },
        "amostra_linhas": df_calc.head(25).to_dict(orient="records"),
    }

    # --- Etapa 7: Exportação ---
    arquivos_exportados = _exportar_resultados(
        projeto_id=config.projeto_id,
        tipo_inventario=config.tipo_inventario,
        memoria_calculo=memoria_calculo,
        quadros_cprh=quadros,
    )

    # --- Retorno Estruturado ---
    return {
        "status": "ok",
        "projeto_id": config.projeto_id,
        "tipo_inventario": config.tipo_inventario,
        "arvores_processadas": len(arvores_insert),
        "arvores_descartadas": linhas_descartadas,
        "erro_amostragem_aprovado": (float(estat["erro_amostragem"]) <= 20.0),
        "estatistica": estat,
        "memoria_calculo": memoria_calculo,
        "quadros_cprh": quadros,
        "arquivos_exportados": arquivos_exportados,
        "avisos": avisos,
    }
