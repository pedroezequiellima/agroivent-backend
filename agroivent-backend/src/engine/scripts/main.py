import argparse
import json
import os

from processor import ProcessamentoConfig, processar_inventario

def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestrador do motor AgroIvent.")
    parser.add_argument("--arquivo", required=True)
    parser.add_argument("--projeto", required=True)
    parser.add_argument(
        "--tipo_inventario",
        required=True,
        choices=["CENSO_100", "AMOSTRAGEM", "RCF"],
    )
    parser.add_argument("--fator_forma", required=True, type=float)
    parser.add_argument("--fator_empilhamento", required=True, type=float)
    parser.add_argument("--area_total_projeto", required=True, type=float)
    parser.add_argument("--area_parcela", required=True, type=float)
    parser.add_argument("--dmc", required=True, type=float)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Variavel DATABASE_URL nao definida para processamento.")

    config = ProcessamentoConfig(
        projeto_id=args.projeto,
        caminho_arquivo=args.arquivo,
        tipo_inventario=args.tipo_inventario,
        fator_forma=args.fator_forma,
        fator_empilhamento=args.fator_empilhamento,
        area_total_projeto=args.area_total_projeto,
        area_parcela=args.area_parcela,
        dmc=args.dmc,
        database_url=database_url,
    )
    resultado = processar_inventario(config)
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
