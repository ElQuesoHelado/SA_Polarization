from __future__ import annotations

import json
from pathlib import Path

from .state import load


def add_parser(actions):
    parser = actions.add_parser("publication", help="Estudio ampliado aislado: datos, cohorte y cuatro modelos")
    commands = parser.add_subparsers(dest="publication_command", required=True)
    for name in ("prepare", "prepare-local", "advance", "runtime-status", "start-services", "annotation-batch", "audit-capture", "collect", "status", "freeze", "next", "benchmark-init", "proposals", "review",
                 "reference-close", "enable-assisted-review", "enable-affinity-screening", "enable-fixed-scope", "screening-audit", "screening-status", "screening-batch", "annotation-progress", "train", "training-report", "diagnose-development", "evaluation-preflight", "measurement-preflight", "predict", "remote", "benchmark", "analyze"):
        sub = commands.add_parser(name)
        sub.add_argument("--config", default="config/targeted_publication.toml")
    commands.choices['enable-fixed-scope'].add_argument('--screened-users',type=int,default=300)
    commands.choices['enable-fixed-scope'].add_argument('--initial-report-users',type=int,default=200)
    commands.choices['analyze'].add_argument('--screened-users',type=int)
    for name in ('predict','remote','benchmark'):
        commands.choices[name].add_argument('--scope',choices=['all','benchmark'],default='all')
    for name in ('screening-status','screening-batch'):
        commands.choices[name].add_argument('--sample',required=True)
        commands.choices[name].add_argument('--stage',choices=['provisional','final'],default='provisional')
    commands.choices['screening-audit'].add_argument('--samples',nargs='+',required=True)
    commands.choices['screening-batch'].add_argument('--limit',type=int,default=50)
    commands.choices["start-services"].add_argument("--daily-api-budget", type=int, default=9000)
    commands.choices["annotation-batch"].add_argument("--sample", required=True)
    commands.choices["annotation-batch"].add_argument("--batch-number", type=int, default=1)
    commands.choices["review"].add_argument("--batch-number", type=int)
    commands.choices["collect"].add_argument("--max-videos", type=int)
    commands.choices["advance"].add_argument("--watch", action="store_true",
        help="Esperar al recolector/cuota y preparar las muestras al cerrar la captura")
    commands.choices["advance"].add_argument("--daily-api-budget", type=int)
    commands.choices["prepare-local"].add_argument("--watch", action="store_true",
        help="Actualizar la preparación local cada 60 segundos hasta congelar el snapshot")
    commands.choices["collect"].add_argument("--daily-api-budget", type=int,
        help="Presupuesto compartido por día del Pacífico, solo para esta ejecución")
    for name in ("proposals", "review", "reference-close", "enable-assisted-review"):
        commands.choices[name].add_argument("--sample", required=True, help="benchmark o cohort_0001, ...")
    commands.choices["proposals"].add_argument("--batch", required=True, type=Path)
    for name in ("next", "benchmark", "analyze"):
        commands.choices[name].add_argument("--stage", choices=["provisional", "final"], default="provisional")
    remote = commands.choices["remote"]
    remote.add_argument("--task", choices=["train", "predict"], required=True)
    remote.add_argument("--operation", choices=["submit", "start", "status", "fetch"], required=True)
    remote.add_argument("--create-dataset", action="store_true")


def run(args):
    from . import annotations, data, analysis, benchmark, remote
    settings, plan, parent, study, registry = load(args.config)
    action = args.publication_command
    if getattr(args,'scope','all') == 'benchmark':
        if action == 'remote' and args.task != 'predict':
            raise ValueError('scope benchmark solo permite predicción')
        from .prediction_scope import benchmark_view
        study,plan=benchmark_view(study,plan,create=action=='predict')
    if action == 'enable-fixed-scope':
        from .fixed_scope import enable
        result=enable(study,args.screened_users,args.initial_report_users)
    elif action == 'enable-affinity-screening':
        from .screening import enable
        result=enable(settings,study,registry)
    elif action == 'screening-audit':
        from .screening import audit
        result=audit(settings,study,registry,args.samples)
    elif action == 'screening-status':
        from .screening import inspect
        result=inspect(settings,study,registry,args.sample,args.stage,persist=True)[0]
    elif action == 'screening-batch':
        from .screening import export
        result=export(settings,study,registry,args.sample,args.stage,args.limit)
    elif action == "prepare":
        from ..common import ROOT
        config_path = Path(args.config)
        config_path = config_path if config_path.is_absolute() else ROOT / config_path
        result = data.prepare(settings, plan, parent, study, registry, config_path)
    elif action == "status":
        result = data.status(settings, study)
    elif action == "prepare-local":
        from .local_preparation import run as prepare_local
        result = prepare_local(settings, plan, study, registry, watch=args.watch)
    elif action == "advance":
        from .advance import run as advance
        result = advance(settings, plan, parent, study, registry,
                         daily_api_budget=args.daily_api_budget, watch=args.watch)
    elif action == "runtime-status":
        from .runtime import status
        result = status(settings, study)
    elif action == "start-services":
        from .runtime import start_services
        result = start_services(settings, study, args.config, args.daily_api_budget)
    elif action == "annotation-batch":
        from .batches import export
        result = export(study, args.sample, args.batch_number)
    elif action == "audit-capture":
        from .capture_audit import run as audit
        result = audit(settings, plan, study, registry)
    elif action == "collect":
        if args.max_videos is not None and args.max_videos < 1:
            raise ValueError("max-videos debe ser positivo")
        result = data.collect(settings, plan, study, max_videos=args.max_videos, daily_api_budget=args.daily_api_budget)
    elif action == "freeze":
        result = data.freeze(settings, plan, parent, study, registry)
    elif action == "next":
        result = annotations.next_batch(settings, plan, study, registry, stage=args.stage)
    elif action == "benchmark-init":
        result = annotations.init_benchmark(study)
    elif action == "proposals":
        result = annotations.import_proposals(study, args.sample, json.loads(args.batch.read_text()), registry)
    elif action == "review":
        result = annotations.review(study, args.sample, registry, batch_number=args.batch_number)
    elif action == "enable-assisted-review":
        result = annotations.enable_assisted_review(study, args.sample)
    elif action == "annotation-progress":
        from .proposal_progress import report
        result = report(settings, plan, study, registry)
    elif action == "reference-close":
        result = annotations.close_reference(study, args.sample, registry)
    elif action in ("train", "predict"):
        result = remote.prepare(settings, plan, parent, study, registry, action)
    elif action == "training-report":
        from .training_report import report
        result = report(settings, study)
    elif action == "diagnose-development":
        from .development_diagnostics import diagnose
        result = diagnose(settings, plan, parent, study, registry)
    elif action == "evaluation-preflight":
        from .evaluation_preflight import preflight
        result = preflight(settings, plan, study, registry)
    elif action == "measurement-preflight":
        from .measurement import preflight
        result = preflight(settings, plan, study, registry)
    elif action == "remote":
        result = remote.action(settings, plan, study, args.task, args.operation, create=args.create_dataset)
    elif action == "benchmark":
        result = benchmark.compare(settings, plan, study, registry, stage=args.stage)
    else:
        result = analysis.analyze(settings, plan, study, registry, stage=args.stage,screened_users=args.screened_users)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str) if isinstance(result, dict) else result)
