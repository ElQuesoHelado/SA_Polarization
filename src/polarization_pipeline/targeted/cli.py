from __future__ import annotations

import argparse
from pathlib import Path

from .common import config, run_directory


def add_parser(commands) -> None:
    parser = commands.add_parser("targeted", help="Estudio separado de polarización mediante valoración dirigida")
    actions = parser.add_subparsers(dest="targeted_command", required=True)
    from .publication.cli import add_parser as add_publication_parser
    add_publication_parser(actions)
    for name, help_text in (
        ("audit", "Auditoría local; no llama a YouTube ni Kaggle"),
        ("diagnose-data", "Audita suficiencia de datos y errores de desarrollo sin abrir prueba"),
        ("design-user-validation", "Dimensiona y prepara una cohorte sin anotar ni calcular AP"),
        ("cohort-annotation-init", "Fija un piloto por usuarios completos y su formulario humano"),
        ("cohort-proposals", "Importa propuestas IA del piloto sin confirmar humanos"),
        ("cohort-review", "Revisa humanamente propuestas del piloto por usuario"),
        ("cohort-reference-import", "Comprueba o cierra la referencia humana del piloto"),
        ("blend-development", "Combina probabilidades de desarrollo existentes sin entrenar ni abrir prueba"),
        ("ai-augment-export", "Congela una ampliación IA solo para entrenamiento"),
        ("ai-augment-import", "Importa etiquetas IA auxiliares sin confirmación humana"),
        ("collect-context", "Verifica metadatos y captura panel mediante YouTube API"),
        ("targets", "Genera candidatos y cola de revisión de actores"),
        ("annotation-export", "Exporta muestra y dos formularios ciegos para humanos"),
        ("annotation-revise", "Crea otra muestra y reutiliza revisiones compatibles sin alterar el origen"),
        ("annotation-import", "Valida revisiones, acuerdo y adjudicación"),
        ("annotate", "Formulario de anotación humana en terminal, con guardado por comentario"),
        ("assisted-init", "Inicia protocolo de un humano asistido por IA, conserva formularios anteriores"),
        ("assisted-proposals", "Importa un lote de propuestas IA sin confirmar revisiones humanas"),
        ("assisted-review", "Revisa, acepta o corrige propuestas IA comentario por comentario"),
        ("assisted-import", "Valida confirmaciones humanas asistidas; no calcula acuerdo entre humanos"),
        ("train", "Entrena en el entorno GPU tras adjudicación humana"),
        ("validate", "Diagnostica el modelo existente solo sobre validación"),
        ("tune", "Compara modelos en un experimento de desarrollo acotado"),
        ("evaluate", "Abre una única vez la prueba humana final"),
        ("infer", "Infiere objetivos tras superar validación"),
        ("analyze", "Produce contrastes dirigidos y actualiza contexto de producción"),
        ("analyze-activity", "Contrasta participación entre fuentes sin usar un clasificador afectivo"),
        ("kaggle-prepare", "Prepara archivos privados sin publicarlos"),
        ("kaggle-import", "Importa resultados de un kernel dirigido"),
        ("kaggle-submit", "Publica un payload en un dataset Kaggle privado aislado"),
        ("kaggle-start", "Inicia GPU tras confirmar la versión esperada ready"),
        ("kaggle-status", "Consulta dataset y kernel dirigidos"),
        ("kaggle-fetch", "Descarga y verifica la salida del trabajo dirigido"),
    ):
        sub = actions.add_parser(name, help=help_text)
        sub.add_argument("--config", default="config/targeted.toml")
        sub.add_argument("--run-id", required=True)
    actions.choices["collect-context"].add_argument("--metadata-only", action="store_true")
    actions.choices["diagnose-data"].add_argument("--diagnostic-id", required=True)
    actions.choices["design-user-validation"].add_argument("--cohort-id", required=True)
    actions.choices["design-user-validation"].add_argument("--users", type=int, default=100)
    actions.choices["design-user-validation"].add_argument("--seed", type=int, default=57)
    for name in ("cohort-annotation-init", "cohort-proposals", "cohort-review", "cohort-reference-import"):
        actions.choices[name].add_argument("--cohort-id", required=True)
    actions.choices["cohort-annotation-init"].add_argument("--pilot-users", type=int, default=25)
    actions.choices["cohort-proposals"].add_argument("--batch", type=Path, required=True)
    actions.choices["cohort-reference-import"].add_argument("--check-only", action="store_true")
    actions.choices["blend-development"].add_argument("--experiment-id", required=True)
    actions.choices["blend-development"].add_argument("--training-config", type=Path, default=Path("config/targeted_ensemble.toml"))
    for name in ("ai-augment-export", "ai-augment-import"):
        actions.choices[name].add_argument("--experiment-id", required=True)
    actions.choices["ai-augment-export"].add_argument("--training-config", type=Path, default=Path("config/targeted_ai_augmentation.toml"))
    actions.choices["ai-augment-import"].add_argument("--batch", type=Path, required=True)
    actions.choices["targets"].add_argument("--ner", action="store_true", help="Descubre PER/ORG con modelo local; nunca asigna bloques automáticamente")
    actions.choices["annotation-import"].add_argument("--pilot-only", action="store_true")
    actions.choices["annotation-export"].add_argument("--refresh-unreviewed", action="store_true", help="Regenera tras cambiar el registro solo si nadie anotó aún; conserva los formularios anteriores")
    actions.choices["annotation-revise"].add_argument("--from-run", required=True)
    actions.choices["annotation-revise"].add_argument("--source-config", default="config/targeted.toml")
    actions.choices["annotate"].add_argument("--reviewer", type=int, choices=[1, 2], required=True)
    actions.choices["annotate"].add_argument("--pilot-only", action="store_true")
    actions.choices["assisted-proposals"].add_argument("--batch", type=Path, required=True)
    for name in ("assisted-review", "assisted-import"):
        actions.choices[name].add_argument("--pilot-only", action="store_true")
    actions.choices["assisted-import"].add_argument("--check-only", action="store_true", help="Diagnóstico sin escribir ni abrir la prueba final")
    actions.choices["kaggle-prepare"].add_argument("--task", choices=["train", "evaluate", "infer", "smoke", "validate", "tune"], required=True)
    actions.choices["kaggle-import"].add_argument("--archive", type=Path, required=True)
    for name in ("kaggle-submit", "kaggle-start", "kaggle-status", "kaggle-fetch"):
        actions.choices[name].add_argument("--task", choices=["train", "evaluate", "infer", "smoke", "validate", "tune"], required=True)
    for name in ("validate", "tune", "kaggle-prepare", "kaggle-submit", "kaggle-start", "kaggle-status", "kaggle-fetch"):
        actions.choices[name].add_argument("--experiment-id", required=name in ("validate", "tune"))
    actions.choices["kaggle-prepare"].add_argument("--training-config", type=Path, default=Path("config/targeted_training.toml"))
    actions.choices["kaggle-submit"].add_argument("--create-dataset", action="store_true")
    actions.choices["kaggle-status"].add_argument("--files", action="store_true")


def run_command(args: argparse.Namespace) -> None:
    if args.targeted_command == "publication":
        from .publication.cli import run
        run(args)
        return
    settings = config(args.config)
    action = args.targeted_command
    if action == "audit":
        from .corpus import audit
        print(audit(settings, args.run_id))
        return
    if action == "annotation-revise":
        import json
        from .revision import revise
        source_settings = config(args.source_config)
        source = run_directory(source_settings, args.from_run)
        if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.run_id):
            raise ValueError("run-id inválido")
        print(json.dumps(revise(settings, settings["workspace"] / args.run_id, source, source_settings), ensure_ascii=False, indent=2))
        return
    run = run_directory(settings, args.run_id)
    if action == "blend-development":
        from .blending import prepare, execute
        root = prepare(settings, run, args.experiment_id, args.training_config)
        print(execute(settings, run, root))
    elif action == "ai-augment-export":
        from .ai_augmentation import export_sample
        print(export_sample(settings, run, args.experiment_id, args.training_config))
    elif action == "ai-augment-import":
        import json
        from .ai_augmentation import import_annotations
        from .development import experiment_directory
        print(import_annotations(experiment_directory(run, args.experiment_id), json.loads(args.batch.read_text())))
    elif action == "diagnose-data":
        from .diagnostics import diagnose_data
        print(diagnose_data(settings, run, args.diagnostic_id))
    elif action == "design-user-validation":
        from .cohort import design_user_validation
        print(design_user_validation(settings, run, args.cohort_id, users=args.users, seed=args.seed))
    elif action.startswith("cohort-"):
        import json
        from .cohort_annotations import initialize, import_proposals, review, import_reference
        if action == "cohort-annotation-init":
            print(initialize(settings, run, args.cohort_id, pilot_users=args.pilot_users))
        elif action == "cohort-proposals":
            print(import_proposals(settings, run, args.cohort_id, json.loads(args.batch.read_text())))
        elif action == "cohort-review":
            review(settings, run, args.cohort_id)
        else:
            print(json.dumps(import_reference(settings, run, args.cohort_id, check_only=args.check_only), ensure_ascii=False, indent=2))
    elif action == "collect-context":
        from .collection import collect_context
        collect_context(settings, run, metadata_only=args.metadata_only)
    elif action == "targets":
        from .registry import discover
        discover(settings, run, use_ner=args.ner)
    elif action == "annotation-export":
        from .annotations import export_annotations
        print(export_annotations(settings, run, refresh_unreviewed=args.refresh_unreviewed))
    elif action == "annotation-import":
        from .annotations import import_annotations
        import_annotations(settings, run, pilot_only=args.pilot_only)
    elif action == "annotate":
        from .review import annotate
        annotate(settings, run, args.reviewer, pilot_only=args.pilot_only)
    elif action.startswith("assisted-"):
        from .assisted import initialize, import_proposals, import_review
        from .review import assisted_review
        if action == "assisted-init":
            print(initialize(settings, run))
        elif action == "assisted-proposals":
            import_proposals(settings, run, args.batch)
        elif action == "assisted-review":
            assisted_review(settings, run, pilot_only=args.pilot_only)
        elif action == "assisted-import":
            if args.check_only:
                import json
                from .assisted import check_review
                print(json.dumps(check_review(settings, run), ensure_ascii=False, indent=2))
            else:
                import_review(settings, run, pilot_only=args.pilot_only)
    elif action in ("train", "evaluate", "infer"):
        from .learning import train, evaluate, infer_targets
        {"train": train, "evaluate": evaluate, "infer": infer_targets}[action](settings, run)
    elif action in ("validate", "tune"):
        from .development import validate, tune
        {"validate": validate, "tune": tune}[action](settings, run, args.experiment_id)
    elif action == "analyze":
        from .metrics import analyze_targeted
        print(analyze_targeted(settings, run))
    elif action == "analyze-activity":
        from .metrics import analyze_activity
        print(analyze_activity(settings, run))
    elif action == "kaggle-prepare":
        from .remote import prepare_job
        print(prepare_job(settings, run, args.task, experiment_id=args.experiment_id, training_config=args.training_config))
    elif action == "kaggle-import":
        from .remote import import_job
        import_job(settings, run, args.archive)
    elif action == "kaggle-submit":
        from .remote import submit_job
        submit_job(settings, run, args.task, create=args.create_dataset, experiment_id=args.experiment_id)
    elif action in ("kaggle-start", "kaggle-status", "kaggle-fetch"):
        from .remote import start_job, status_job, fetch_job
        if action == "kaggle-status":
            status_job(settings, run, args.task, list_files=args.files, experiment_id=args.experiment_id)
        else:
            {"kaggle-start": start_job, "kaggle-fetch": fetch_job}[action](settings, run, args.task, experiment_id=args.experiment_id)
