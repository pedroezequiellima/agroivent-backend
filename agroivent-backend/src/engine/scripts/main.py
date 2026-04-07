import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestrador do motor AgroIvent.")
    parser.add_argument("--arquivo", required=True)
    parser.add_argument("--projeto", required=True)
    args = parser.parse_args()
    print(f"Processamento iniciado para projeto={args.projeto} arquivo={args.arquivo}")


if __name__ == "__main__":
    main()
