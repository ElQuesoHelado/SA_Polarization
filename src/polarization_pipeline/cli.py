from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .analysis import analyze
from .config import DEFAULT_CONFIG, load_config
from .kaggle import infer, pull_dataset, publish_dataset
from .preprocess import preprocess
from .smoke_test import run_smoke_test
from .youtube import collect


def _command(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Ruta al pipeline.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sa-polarization", description="Pipeline local + Kaggle GPU para SA Polarization")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("collect", "Recolecta comentarios de canales y periodos configurados"),
        ("preprocess", "Normaliza los JSON raw a un CSV"),
        ("prepare-data", "Recolecta datos de YouTube y los preprocesa localmente"),
        ("infer-results", "Publica los datos, ejecuta inferencia y genera resultados"),
        ("data-pull", "Descarga JSON y CSV desde el dataset Kaggle"),
        ("infer", "Publica y ejecuta el kernel GPU en Kaggle, y descarga sus resultados"),
        ("analyze", "Calcula métricas y genera CSV y gráficas localmente"),
        ("smoke-test", "Prueba el pipeline con un subset y recursos Kaggle aislados"),
    ):
        sub = commands.add_parser(name, help=help_text)
        _command(sub)
    publish = commands.add_parser("data-publish", help="Publica una nueva versión del dataset Kaggle")
    _command(publish)
    publish.add_argument("--message", required=True, help="Descripción de la versión de datos")
    create = commands.add_parser("data-create", help="Crea el dataset Kaggle privado por primera vez")
    _command(create)
    infer_results = commands.choices["infer-results"]
    infer_results.add_argument("--message", default="Prepared data for inference", help="Descripción de la versión de datos")
    full = commands.add_parser("full-pipeline", help="Ejecuta ambas etapas principales en orden")
    _command(full)
    full.add_argument("--message", default="Full pipeline", help="Descripción de la versión de datos")
    smoke = commands.choices["smoke-test"]
    smoke.add_argument("--fraction", type=float, help="Fracción de comentarios por archivo (por defecto 0.25)")
    smoke.add_argument("--seed", type=int, help="Semilla de muestreo reproducible")
    smoke.add_argument("--create-dataset", action="store_true", help="Crear el dataset Kaggle privado en la primera ejecución")
    return parser


def run_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if args.command == "collect":
        collect(config)
    elif args.command == "preprocess":
        preprocess(config)
    elif args.command == "data-pull":
        pull_dataset(config)
    elif args.command == "data-publish":
        publish_dataset(config, args.message)
    elif args.command == "data-create":
        publish_dataset(config, "Initial dataset", create=True)
    elif args.command == "infer":
        infer(config)
    elif args.command == "analyze":
        analyze(config)
    elif args.command == "smoke-test":
        run_smoke_test(
            config,
            fraction=args.fraction,
            seed=args.seed,
            create_dataset=args.create_dataset,
        )
    elif args.command == "prepare-data":
        collect(config)
        preprocess(config)
    elif args.command == "infer-results":
        publish_dataset(config, args.message)
        infer(config)
        analyze(config)
    elif args.command == "full-pipeline":
        collect(config)
        preprocess(config)
        publish_dataset(config, args.message)
        infer(config)
        analyze(config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_command(args)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, TimeoutError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
