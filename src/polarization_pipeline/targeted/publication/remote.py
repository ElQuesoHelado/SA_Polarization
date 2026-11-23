"""Private, version-pinned jobs with label-free prediction and training-only labels."""
from __future__ import annotations

import json
import shutil
import tarfile
import time
from pathlib import Path

from ..common import atomic_json, sha256, stamp
from ..remote import KERNEL, _kaggle, start_job, status_job, submit_job, validate_job
from .state import verify, verify_seal, lock


def query_status(settings, arguments):
    """Retry only read-only status queries; submissions and downloads never repeat."""
    if tuple(arguments[:2]) not in (('kernels','status'), ('datasets','status')):
        raise ValueError('Only read-only kernel/dataset status queries may be retried')
    for attempt in range(3):
        try:
            return _kaggle(settings, arguments)
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(30)


def remote_settings(settings, plan):
    return {**settings, "kaggle": {**settings["kaggle"], **plan["kaggle"]}}


def stage(study, task):
    if task not in ("train", "predict"):
        raise ValueError("Solo entrenamiento y predicción diagnóstica; prueba histórica no disponible")
    return study / "kaggle" / ("train" if task == "train" else "infer")


def frozen_execution_package(study):
    """Use the exact training sources even while the local analysis evolves."""
    payload = stage(study, 'train') / 'payload'
    manifest = json.loads((payload / 'payload_manifest.json').read_text())
    archived = stage(study, 'train') / 'dataset/targeted_payload.tar.gz'
    job = json.loads((stage(study, 'train') / 'job_manifest.json').read_text())
    if sha256(archived) != job['payload_sha256']:
        raise ValueError('Payload de entrenamiento alterado')
    # Bind the expanded manifest to the originally published archive, not to itself.
    with tarfile.open(archived) as archive:
        matches = [m for m in archive.getmembers() if m.name == 'payload_manifest.json']
        if len(matches) != 1 or json.loads(archive.extractfile(matches[0]).read()) != manifest:
            raise ValueError('Manifiesto de código congelado incompatible')
    expected = {name: digest for name, digest in manifest.items() if name.startswith('src/')}
    actual = {str(p.relative_to(payload)) for p in (payload / 'src').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if actual != set(expected) or any(sha256(payload / name) != digest for name, digest in expected.items()):
        raise ValueError('Código congelado de entrenamiento alterado')
    return payload / 'src/polarization_pipeline'


def retry(settings, plan, study, task):
    """One explicit retry after acknowledged cancellation; preserve every attempt."""
    if not plan.get('model_extension_protocol') or task != 'train':
        raise ValueError('Reintento limitado al entrenamiento de la ampliación')
    destination = stage(study, task)
    remote = remote_settings(settings, plan)
    with lock(destination / 'retry.lock'):
        job = json.loads((destination / 'job_manifest.json').read_text())
        validate_job(remote, destination, job)
        if not job.get('started') or not job.get('kernel_ref') or (study / 'training').exists():
            raise ValueError('No hay ejecución cancelada reintentable o ya hay resultados')
        attempts = destination / 'attempts'
        if attempts.exists():
            for path in attempts.glob('*/retry.json'):
                if json.loads(path.read_text())['state'] in ('submitting', 'submission_unknown'):
                    raise ValueError('Envío anterior incierto; verificar versión remota antes de reenviar')
        status = _kaggle(remote, ['kernels', 'status', job['kernel_ref']])
        if 'cancel_acknowledged' not in status.lower() and 'cancelled' not in status.lower():
            raise ValueError('Kaggle debe confirmar cancelación; no duplicar una ejecución activa')
        logs = _kaggle(remote, ['kernels', 'logs', job['kernel_ref']]).strip()
        if logs:
            raise ValueError('Hay registros de ejecución; auditar ajustes parciales antes de repetir')
        quota = json.loads(_kaggle(remote, ['quota', '--format', 'json']))
        gpu = next((r for r in quota if r['resource'] == 'GPU'), None)
        if not gpu or float(gpu['remaining'].rstrip('h')) <= 0:
            raise ValueError('Sin cuota GPU disponible')
        frozen_execution_package(study)
        previous = destination / 'attempts' / f"{len(list(attempts.glob('*'))) + 1:04d}"
        previous.mkdir(parents=True, exist_ok=False)
        shutil.copy2(destination / 'job_manifest.json', previous / 'job_manifest.json')
        record = dict(state='submitting', created_at=stamp(), previous_ref=job['kernel_ref'],
                      cancellation_status=status.strip(), empty_logs=True, quota=quota,
                      old_manifest_sha256=sha256(previous / 'job_manifest.json'), production_enabled=False)
        atomic_json(previous / 'retry.json', record)
        # Operational pointer only; the immutable previous manifest is retained above.
        fresh = {k:v for k,v in job.items() if k not in
                 ('kernel_ref', 'kernel_version', 'resolved_kernel_id', 'started_at', 'verified_dataset_version')}
        fresh.update(started=False, retry_of=job['kernel_ref'], retry_archive=str(previous))
        atomic_json(destination / 'job_manifest.json', fresh)
        try:
            start_job(remote, study, 'train')
            current = json.loads((destination / 'job_manifest.json').read_text())
            if not current.get('kernel_ref') or current['kernel_ref'] == job['kernel_ref']:
                raise RuntimeError('Kaggle no confirmó una versión nueva y exacta')
        except Exception:
            atomic_json(previous / 'retry.json', {**record, 'state':'submission_unknown', 'updated_at':stamp()})
            raise
        atomic_json(previous / 'retry.json', {**record, 'state':'submitted', 'updated_at':stamp(),
                                            'new_ref':current['kernel_ref']})
        return current['kernel_ref']


def prepare(settings, plan, parent, study, registry, task):
    from .training import prepare as prepare_training, prediction_pairs, prediction_comments
    verify(study, frozen=task == "predict")
    if task == "train":
        prepare_training(settings, plan, parent, study)
    else:
        verify_seal(study / "training")
        if (study / "prediction_input.csv").exists():
            raise FileExistsError("Entrada de predicción ya preparada; no sobrescribir")
        pairs = prediction_pairs(study, registry)
        if pairs.empty:
            raise ValueError("No hay candidatos para comparar")
        pairs.to_csv(study / "prediction_input.csv", index=False)
        prediction_comments(study)[["comment_id", "post_id"]].to_csv(study / "prediction_scope.csv", index=False)
    destination = stage(study, task)
    destination.mkdir(parents=True, exist_ok=False)
    dataset, kernel = destination / "dataset", destination / "kernel"
    dataset.mkdir(); kernel.mkdir()
    payload_root = destination / "payload"
    payload_root.mkdir()
    package = (frozen_execution_package(study) if task == 'predict' and plan.get('model_extension_protocol')
               else settings["_root"] / "src/polarization_pipeline")
    shutil.copytree(package, payload_root / "src/polarization_pipeline", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    config_dir = payload_root / "config"
    config_dir.mkdir()
    shutil.copy2(settings["_config_path"], config_dir / "targeted.toml")
    shutil.copy2(settings["source_config"], config_dir / "pipeline.toml")
    shutil.copy2(settings["registry"], config_dir / "political_targets.json")
    # Only these explicitly allowlisted data files can reach Kaggle.
    study_root = payload_root / "publication"
    study_root.mkdir()
    if task == "train":
        shutil.copytree(study / "training_input", study_root / "training_input")
    else:
        shutil.copytree(study / "training", study_root / "training")
        shutil.copy2(study / "prediction_input.csv", study_root / "prediction_input.csv")
        shutil.copy2(study / "prediction_scope.csv", study_root / "prediction_scope.csv")
    atomic_json(payload_root / "job.json", dict(task="train" if task == "train" else "infer", publication_task=task))
    files = {str(p.relative_to(payload_root)): sha256(p) for p in payload_root.rglob("*") if p.is_file()}
    atomic_json(payload_root / "payload_manifest.json", files)
    payload = dataset / "targeted_payload.tar.gz"
    with tarfile.open(payload, "w:gz") as archive:
        for path in sorted(payload_root.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(payload_root)), recursive=False)
    code = KERNEL.replace("__EXPECTED_MANIFEST_SHA256__", sha256(payload_root / "payload_manifest.json"))
    code = code.replace('"protobuf>=4"', '"protobuf>=4", "pysentimiento==0.7.3"')
    code = code.replace('"transformers>=4.40,<5"', '"transformers==4.57.6"')
    code = code.replace('["torch", "transformers", "numpy", "pandas"]', '["torch", "transformers", "numpy", "pandas", "pysentimiento", "emoji"]')
    start, end = code.index("def execute_job():"), code.index("\ndef smoke_job():")
    code = code[:start]+'''def execute_job():
    from polarization_pipeline.targeted.publication.training import train_worker, predict_worker
    {"train": train_worker, "predict": predict_worker}[job["publication_task"]](settings, root / "publication")
'''+code[end:]
    code = code.replace('names = ("run/model", "run/predictions.csv", "run/prediction_manifest.json", "smoke.json", "environment.json", "job_failure.json")',
        'names = ("publication/training", "environment.json", "job_failure.json") if job["publication_task"] == "train" else ("publication/predictions", "environment.json", "job_failure.json")')
    (kernel / "kernel.py").write_text(code)
    ids = plan["kaggle"]
    kernel_id = ids["training_kernel_id"] if task == "train" else ids["inference_kernel_id"]
    forbidden = {settings["kaggle"]["dataset_id"], settings["kaggle"]["training_kernel_id"], settings["kaggle"]["inference_kernel_id"],
                 settings["source"]["kaggle"]["dataset_id"], settings["source"]["kaggle"]["kernel_id"]}
    if ids["dataset_id"] in forbidden or kernel_id in forbidden:
        raise ValueError("Recursos de publicación deben ser distintos de los anteriores")
    atomic_json(dataset / "dataset-metadata.json", dict(id=ids["dataset_id"], title="SA Polarization Publication Data", licenses=[dict(name="other")]))
    kernel_title = "SA Polarization Publication " + ("Training" if task == "train" else "Predict")
    if task == "predict" and (study / "scope.json").exists():
        kernel_title += " Benchmark"
    if plan.get('model_extension_protocol'):
        kernel_title = kernel_id.split('/')[1].replace('-', ' ').title()
    atomic_json(kernel / "kernel-metadata.json", dict(id=kernel_id, title=kernel_title, code_file="kernel.py",
        language="python", kernel_type="script", is_private=True, enable_gpu=True, enable_internet=True,
        dataset_sources=[ids["dataset_id"]], competition_sources=[], kernel_sources=[]))
    atomic_json(destination / "job_manifest.json", dict(task="train" if task == "train" else "infer", publication_task=task,
        dataset_id=ids["dataset_id"], kernel_id=kernel_id, payload_sha256=sha256(payload), kernel_sha256=sha256(kernel / "kernel.py"),
        published=False, started=False, created_at=stamp(), production_enabled=False))
    verify(study, frozen=task == "predict")
    return destination


def action(settings, plan, study, task, operation, *, create=False):
    verify(study, frozen=task == "predict")
    remote = remote_settings(settings, plan)
    remote_task = "train" if task == "train" else "infer"
    if operation == "submit":
        return submit_job(remote, study, remote_task, create=create)
    if operation == "start":
        return start_job(remote, study, remote_task)
    if operation == 'retry':
        return retry(settings, plan, study, task)
    if operation == "status":
        return status_job(remote, study, remote_task)
    if operation != "fetch":
        raise ValueError("Operación remota desconocida")
    destination = stage(study, task)
    job = json.loads((destination / "job_manifest.json").read_text())
    if not job.get("started") or not job.get("kernel_ref"):
        raise ValueError("Falta versión exacta del kernel; no descargar última versión por omisión")
    status = _kaggle(remote, ["kernels", "status", job["kernel_ref"]]).lower()
    if "complete" not in status and "error" not in status and "failed" not in status:
        raise ValueError("El trabajo sigue en ejecución")
    download = destination / ("download_"+stamp().replace(":", "").replace(".", ""))
    download.mkdir()
    _kaggle(remote, ["kernels", "output", job["kernel_ref"], "-p", str(download), "-q", "--file-pattern", r"(^|/)targeted_result\.tar\.gz$"])
    matches = list(download.rglob("targeted_result.tar.gz"))
    if len(matches) != 1:
        raise ValueError("Archivo remoto de resultados ausente/duplicado")
    return import_result(study, matches[0], task)


def import_result(study, archive_path, task):
    destination = stage(study, task)
    incoming = destination / ("import_"+stamp().replace(":", "").replace(".", ""))
    incoming.mkdir()
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError("Archivo remoto con rutas duplicadas")
        for member in members:
            path = (incoming / member.name).resolve()
            if not path.is_relative_to(incoming.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError("Ruta remota insegura")
        archive.extractall(incoming, filter="data")
    if (incoming / "job_failure.json").exists():
        raise ValueError(f"Trabajo remoto fallido; artefactos parciales conservados en {incoming}")
    name = "training" if task == "train" else "predictions"
    source = incoming / "publication" / name
    verify_seal(source)
    if (study / name).exists():
        raise FileExistsError("Resultado ya importado; no sobrescribir")
    if task == "train":
        summary = json.loads((source / "comparison.json").read_text())
        expected = json.loads((study / "training_input/plan.json").read_text())
        from .training import validate_plan
        validate_plan(expected)
        if (summary.get("completed_fits") != expected['maximum_fits'] or summary.get("production_enabled") is not False
                or summary.get("training_input_sha256") != sha256(study / "training_input/manifest.json")):
            raise ValueError("Comparación remota incompatible")
        if [m["model_id"] for m in summary.get("models", [])] != [m["id"] for m in expected["models"]]:
            raise ValueError("Faltan modelos de la comparación autorizada")
        for model in expected["models"]:
            folder = source / model["id"] / "model"
            manifest = json.loads((folder / "training_manifest.json").read_text())
            if manifest["model"] != model or [r["seed"] for r in manifest["revisions"]] != expected["model_seeds"]:
                raise ValueError("Modelo/revisiones/semillas remotos incompatibles")
            for seed in expected["model_seeds"]:
                checkpoint = folder / str(seed)
                if not (checkpoint / "config.json").exists() or not (checkpoint / "tokenizer_config.json").exists():
                    raise ValueError("Checkpoint remoto incompleto")
                if not list(checkpoint.glob("*.safetensors")) and not (checkpoint / "pytorch_model.bin").exists():
                    raise ValueError("Faltan pesos del checkpoint remoto")
    else:
        manifest = json.loads((source / "manifest.json").read_text())
        if (manifest["prediction_input_sha256"] != sha256(study / "prediction_input.csv")
                or manifest["prediction_scope_sha256"] != sha256(study / "prediction_scope.csv")
                or manifest["training_sha256"] != sha256(study / "training/manifest.json")):
            raise ValueError("Predicciones para otra muestra")
    pending = study / (name + "_import_pending_" + stamp().replace(":", "").replace(".", ""))
    shutil.copytree(source, pending)
    verify_seal(pending)
    pending.rename(study / name)
    environment = incoming / "environment.json"
    if environment.exists():
        shutil.copy2(environment, destination / "environment.json")
    atomic_json(destination / "import_report.json", dict(archive_sha256=sha256(archive_path), imported_at=stamp(),
        task=task, environment_sha256=sha256(environment) if environment.exists() else None,
        files_verified=len(json.loads((source / "manifest.json").read_text())["files"]), production_enabled=False))
    return study / name
