"""Prepare isolated private Kaggle jobs; no publication as a side effect of preparation."""
from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path
import hashlib
import io

from .common import atomic_json, sha256, stamp


KERNEL = '''"""Isolated targeted-polarization GPU job."""
import importlib.metadata
import json
import subprocess
import sys
import tarfile
import hashlib
import shutil
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "transformers>=4.40,<5", "sentencepiece>=0.2", "protobuf>=4"], check=True)
root = Path("/tmp/targeted_job")
root.mkdir(exist_ok=False)
def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

# Kaggle Datasets expands uploaded .tar.gz files. Verify the expanded tree;
# also support a backend that preserves the original archive.
manifests = list(Path("/kaggle/input").rglob("payload_manifest.json"))
if not manifests:
    archives = list(Path("/kaggle/input").rglob("targeted_payload.tar.gz"))
    if len(archives) != 1:
        raise RuntimeError("Expected exactly one targeted input payload")
    expanded = Path("/tmp/targeted_expanded_input")
    expanded.mkdir(exist_ok=False)
    with tarfile.open(archives[0]) as archive:
        for member in archive.getmembers():
            destination = (expanded / member.name).resolve()
            if not destination.is_relative_to(expanded.resolve()) or not (member.isfile() or member.isdir()):
                raise RuntimeError("Unsafe archive member")
        archive.extractall(expanded)
    manifests = list(expanded.rglob("payload_manifest.json"))
if len(manifests) != 1 or file_sha(manifests[0]) != "__EXPECTED_MANIFEST_SHA256__":
    raise RuntimeError("Mounted dataset is not the verified published version")
tree = manifests[0].parent
for name, expected in json.loads(manifests[0].read_text()).items():
    source = (tree / name).resolve()
    destination = (root / name).resolve()
    if not source.is_relative_to(tree.resolve()) or not destination.is_relative_to(root.resolve()) or file_sha(source) != expected:
        raise RuntimeError("Input file failed integrity verification")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
sys.path.insert(0, str(root / "src"))
from polarization_pipeline.targeted.common import config, atomic_json
from polarization_pipeline.targeted.learning import train, evaluate, infer_targets, _gpu
settings = config(root / "config" / "targeted.toml")
settings["_root"] = root
settings["registry"] = root / "config" / "political_targets.json"
run = root / "run"
job = json.loads((root / "job.json").read_text())
print("CUDA connectivity", _gpu().cuda.get_device_name(0), flush=True)
def execute_job():
    if job["task"] == "smoke":
        smoke_job()
    elif job["task"] == "train":
        train(settings, run)
    elif job["task"] == "evaluate":
        evaluate(settings, run)
    elif job["task"] == "infer":
        infer_targets(settings, run)
    elif job["task"] in ("validate", "tune"):
        from polarization_pipeline.targeted.development import validate, tune
        {"validate": validate, "tune": tune}[job["task"]](settings, run, job["experiment_id"])
    else:
        raise ValueError("Unsupported job")

def smoke_job():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    tokenizer = AutoTokenizer.from_pretrained(settings["base_model"], use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(settings["base_model"], num_labels=5).cuda()
    with _gpu().no_grad():
        result = model(**{k: v.cuda() for k, v in tokenizer("Actor de prueba", "Texto sintético para comprobar la GPU", return_tensors="pt").items()})
    atomic_json(root / "smoke.json", {"gpu": True, "model_download_verified": True, "logit_shape": list(result.logits.shape), "scientific_results": False})
failure = None
try:
    execute_job()
except Exception as exc:
    failure = exc
    atomic_json(root / "job_failure.json", {"task": job["task"], "exception_type": type(exc).__name__, "scientific_results": False})
atomic_json(root / "environment.json", {name: importlib.metadata.version(name) for name in ["torch", "transformers", "numpy", "pandas"]})
with tarfile.open("/kaggle/working/targeted_result.tar.gz", "w:gz") as archive:
    if job["task"] in ("validate", "tune"):
        from polarization_pipeline.targeted.development import export_experiment
        export_path = export_experiment(settings, run, job["experiment_id"], job["task"])
        export = json.loads(export_path.read_text())
        for name in export["files"]:
            path = export_path.parent / name
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
        archive.add(export_path, arcname=str(export_path.relative_to(root)), recursive=False)
        names = ("environment.json", "job_failure.json")
    else:
        names = ("run/model", "run/predictions.csv", "run/prediction_manifest.json", "smoke.json", "environment.json", "job_failure.json")
    for name in names:
        path = root / name
        if path.exists():
            archive.add(path, arcname=name)
if failure is not None:
    raise failure
print("TARGETED_JOB_COMPLETE", job["task"], flush=True)
'''


def job_stage(run: Path, task: str, experiment_id: str | None = None) -> Path:
    if task in ("validate", "tune"):
        from .development import experiment_directory
        experiment_directory(run, experiment_id)
        return run / "kaggle" / experiment_id / task
    if experiment_id is not None:
        raise ValueError("experiment-id solo se usa para validate/tune; no redirigir la prueba final")
    return run / "kaggle" / task


def prepare_job(settings: dict, run: Path, task: str, *, experiment_id: str | None = None,
                training_config: Path = Path("config/targeted_training.toml")) -> Path:
    if task not in ("train", "evaluate", "infer", "smoke", "validate", "tune"):
        raise ValueError("Tarea remota no soportada")
    stage = job_stage(run, task, experiment_id)
    development = task in ("validate", "tune")
    experiment = None
    if development:
        from .development import freeze_experiment
        if stage.exists():
            raise FileExistsError(stage)
        training_config = training_config if training_config.is_absolute() else settings["_root"] / training_config
        experiment = freeze_experiment(settings, run, experiment_id, training_config)
        if task == "tune" and not (experiment / "baseline/manifest.json").exists():
            raise ValueError("Primero ejecutar e importar validate")
    if task == "train":
        from .annotations import training_pairs
        training_pairs(settings, run)
    if task in ("evaluate", "infer") and not (run / "model" / "training_manifest.json").exists():
        raise ValueError("Primero entrenar e importar los checkpoints")
    if task == "evaluate" and (run / "model" / "test_opened.json").exists():
        raise ValueError("La prueba final ya fue abierta")
    if task == "evaluate":
        from .learning import require_test_calibration
        require_test_calibration(settings, run)
    if task == "infer":
        from .registry import candidates
        evaluation = json.loads((run / "model" / "evaluation.json").read_text())
        if evaluation.get("status") != "passed":
            raise ValueError("Primero superar e importar la evaluación humana final")
        if evaluation.get("gold_sha256") != sha256(run / "annotations/gold.csv") or evaluation.get("quality_criteria") != settings["quality"]:
            raise ValueError("Anotaciones o criterios cambiaron después de la prueba")
        candidates(settings, run)
    stage.mkdir(parents=True, exist_ok=False)
    dataset = stage / "dataset"
    kernel = stage / "kernel"
    dataset.mkdir()
    kernel.mkdir()
    remote = settings["kaggle"]
    dataset_id = remote["smoke_dataset_id"] if task == "smoke" else remote["dataset_id"]
    kernel_id = remote["smoke_kernel_id"] if task == "smoke" else remote["training_kernel_id"] if task == "train" or development else remote["inference_kernel_id"]
    forbidden = {settings["source"]["kaggle"]["dataset_id"], settings["source"]["kaggle"]["kernel_id"]}
    if dataset_id in forbidden or kernel_id in forbidden:
        raise ValueError("Los recursos dirigidos no pueden usar IDs productivos históricos")
    atomic_json(dataset / "dataset-metadata.json", {"id": dataset_id, "title": "SA Polarization Targeted " + ("Smoke" if task == "smoke" else "Private Study"), "licenses": [{"name": "other"}]})
    source = settings["_root"] / "src" / "polarization_pipeline"
    payload = dataset / "targeted_payload.tar.gz"
    payload_files = {}
    with tarfile.open(payload, "w:gz") as archive:
        def add_bytes(data, name):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
            payload_files[name] = hashlib.sha256(data).hexdigest()
        def add_path(path, name):
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        add_path(child, f"{name}/{child.relative_to(path).as_posix()}")
            else:
                archive.add(path, arcname=name, recursive=False)
                payload_files[name] = sha256(path)
        for path in sorted((source / "targeted").glob("*.py")):
            add_path(path, f"src/polarization_pipeline/targeted/{path.name}")
        add_path(source / "__init__.py", "src/polarization_pipeline/__init__.py")
        add_path(settings["_config_path"], "config/targeted.toml")
        add_path(settings["source_config"], "config/pipeline.toml")
        add_path(settings["registry"], "config/political_targets.json")
        add_bytes(json.dumps({"task": task, "experiment_id": experiment_id}).encode(), "job.json")
        if task == "train" or development:
            from .common import read_csv
            original = json.loads((run / "annotations/manifest.json").read_text())
            ai_development = development and json.loads((experiment / "plan.json").read_text()).get("protocol") == "targeted-ai-augmentation-v1"
            refinement_development = development and json.loads((experiment / "plan.json").read_text()).get("protocol") == "targeted-human-refinement-v1"
            gold = read_csv(experiment / "human_development.csv") if ai_development or refinement_development else read_csv(run / "annotations/gold.csv")
            if refinement_development:
                from .refinement import verify
                _, paired = verify(settings, run, experiment)
            elif ai_development:
                from .ai_augmentation import verify
                _, paired = verify(settings, run, experiment)
            elif development:
                from .development import development_data
                _, paired = development_data(settings, run)
            else:
                paired = read_csv(run / "training_pairs.csv")
            training_gold = gold.loc[gold.split.ne("test")].to_csv(index=False).encode()
            training_paired = paired.loc[paired.split.ne("test")].to_csv(index=False).encode()
            remote_manifest = {**original, "study_gold_sha256": original["gold_sha256"], "gold_sha256": hashlib.sha256(training_gold).hexdigest()}
            if original.get("annotation_protocol") == "ai_assisted_single_human_v1":
                receipt = {"protocol": original["annotation_protocol"], "gold_sha256": remote_manifest["gold_sha256"],
                    "study_gold_sha256": original["gold_sha256"], "source_review_report_sha256": original["assisted_report_sha256"],
                    "limitation": original["annotation_limitation"], "test_labels_withheld": True}
                receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
                remote_manifest["assisted_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
                add_bytes(receipt_bytes, "run/annotations/assisted_training_receipt.json")
            add_bytes(training_gold, "run/annotations/gold.csv")
            add_bytes(training_paired, "run/training_pairs.csv")
            add_bytes(json.dumps(remote_manifest, ensure_ascii=False, indent=2).encode(), "run/annotations/manifest.json")
            if not development:
                add_path(run / "corpus_main.csv", "run/corpus_main.csv")
            else:
                for name in ("source.json", "plan.json"):
                    add_path(experiment / name, f"run/experiments/{experiment_id}/{name}")
                if ai_development:
                    from .ai_augmentation import INPUTS
                    for name in INPUTS:
                        add_path(experiment / name, f"run/experiments/{experiment_id}/{name}")
                if refinement_development:
                    from .refinement import INPUTS
                    for name in (*INPUTS, "warmstart", "controls"):
                        add_path(experiment / name, f"run/experiments/{experiment_id}/{name}")
                if task == "validate":
                    # Only verified checkpoint files; no stale pre-test report or human forms.
                    model = run / "model"
                    m = json.loads((model / "training_manifest.json").read_text())
                    add_path(model / "training_manifest.json", "run/model/training_manifest.json")
                    for name, digest in m["checkpoint_hashes"].items():
                        path = (model / name).resolve()
                        if not path.is_relative_to(model.resolve()) or sha256(path) != digest:
                            raise ValueError("Checkpoint de referencia alterado")
                        add_path(path, f"run/model/{name}")
                else:
                    add_path(experiment / "baseline", f"run/experiments/{experiment_id}/baseline")
                    if (experiment / "reference_beto").exists():
                        add_path(experiment / "reference_beto", f"run/experiments/{experiment_id}/reference_beto")
        elif task != "smoke":
            names = ["annotations/manifest.json", "annotations/gold.csv", "training_pairs.csv", "corpus_main.csv"] if task == "evaluate" else ["corpus_main.csv", "corpus_panel.csv", "candidates.csv"]
            if task in ("evaluate", "infer"):
                names.append("model")
            for name in names:
                path = run / name
                if path.exists():
                    add_path(path, f"run/{name}")
        manifest_data = (json.dumps(payload_files, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
        member = tarfile.TarInfo("payload_manifest.json")
        member.size = len(manifest_data)
        archive.addfile(member, io.BytesIO(manifest_data))
    manifest_digest = hashlib.sha256(manifest_data).hexdigest()
    (kernel / "kernel.py").write_text(KERNEL.replace("__EXPECTED_MANIFEST_SHA256__", manifest_digest), encoding="utf-8")
    atomic_json(kernel / "kernel-metadata.json", {"id": kernel_id, "title": kernel_id.split("/")[1].replace("-", " ").title(),
        "code_file": "kernel.py", "language": "python", "kernel_type": "script", "is_private": True,
        "enable_gpu": True, "enable_internet": True, "dataset_sources": [dataset_id], "competition_sources": [], "kernel_sources": []})
    atomic_json(stage / "job_manifest.json", {"created_at": stamp(), "task": task, "experiment_id": experiment_id, "dataset_id": dataset_id, "kernel_id": kernel_id,
                "payload_sha256": sha256(payload), "payload_manifest_sha256": manifest_digest,
                "kernel_sha256": sha256(kernel / "kernel.py"), "published": False})
    (stage / "README.md").write_text(
        "# Ejecución privada preparada\n\n"
        "1. Crear el dataset privado con `kaggle datasets create -p dataset -r skip`, o publicar "
        "otra versión con `kaggle datasets version -p dataset -m targeted -r skip`. No usar --public.\n"
        "2. Esperar la nueva versión ready y comprobar que contiene el payload SHA del manifiesto; "
        "registrar el número de versión. No hacer push inmediatamente después de version.\n"
        "3. Confirmar GPU e Internet efectivos en Kaggle antes de `kaggle kernels push -p kernel`. "
        "La descarga del modelo en el log confirma conectividad; enable_internet solo no basta.\n"
        "4. Consultar estado y descargar outputs cuando COMPLETE. Importar targeted_result.tar.gz con "
        "`sa-polarization targeted kaggle-import --run-id ... --archive ...`.\n"
        "5. No reutilizar una prueba final abierta ni publicar resultados antes de validar el modelo.\n", encoding="utf-8")
    return stage


def import_job(settings: dict, run: Path, archive_path: Path) -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="targeted-import-") as temp:
        destination = Path(temp)
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                path = (destination / member.name).resolve()
                if not path.is_relative_to(destination.resolve()) or not (member.isfile() or member.isdir()):
                    raise ValueError("Archivo remoto inseguro")
            archive.extractall(destination)
        incoming = destination / "run"
        if not incoming.exists():
            raise ValueError("Salida sin artefactos de estudio (smoke no se importa a producción)")
        if (incoming / "experiments").exists():
            import_experiment(settings, run, incoming, archive_path)
            return
        model = incoming / "model"
        if model.exists():
            received = json.loads((model / "training_manifest.json").read_text())
            gold = run / "annotations" / "gold.csv"
            if not gold.exists() or received["gold_sha256"] != sha256(gold) or received["registry_sha256"] != sha256(settings["registry"]):
                raise ValueError("El resultado remoto no corresponde a las anotaciones/registro de esta ejecución")
        prediction_manifest = incoming / "prediction_manifest.json"
        if prediction_manifest.exists():
            received = json.loads(prediction_manifest.read_text())
            if received["corpus_main_sha256"] != sha256(run / "corpus_main.csv") or received["predictions_sha256"] != sha256(incoming / "predictions.csv"):
                raise ValueError("Predicciones remotas ajenas o alteradas")
        for name in ("predictions.csv", "prediction_manifest.json"):
            if (incoming / name).exists() and (run / name).exists():
                raise FileExistsError(run / name)
        if model.exists():
            old = run / "model"
            if old.exists():
                old_training = sha256(old / "training_manifest.json")
                new_training = sha256(model / "training_manifest.json")
                if old_training != new_training:
                    raise ValueError("Los checkpoints recibidos corresponden a otro entrenamiento")
                for path in model.rglob("*"):
                    if path.is_file():
                        target = old / path.relative_to(model)
                        if target.exists() and sha256(target) != sha256(path):
                            raise FileExistsError(f"Conflicto remoto: {target.name}")
                shutil.copytree(model, old, dirs_exist_ok=True)
            else:
                shutil.copytree(model, old)
        for name in ("predictions.csv", "prediction_manifest.json"):
            source = incoming / name
            if source.exists():
                target = run / name
                if target.exists():
                    raise FileExistsError(target)
                shutil.copy2(source, target)
        atomic_json(run / "remote_import.json", {"imported_at": stamp(), "archive_sha256": sha256(archive_path)})


def import_experiment(settings: dict, run: Path, incoming: Path, archive_path: Path) -> None:
    from .development import experiment_directory, verify_source
    roots = list((incoming / "experiments").iterdir())
    if len(roots) != 1 or any(path.name != "experiments" for path in incoming.iterdir()):
        raise ValueError("Salida de desarrollo mezclada con artefactos canónicos")
    root = roots[0]
    target = experiment_directory(run, root.name)
    verify_source(settings, run, target)
    exports = list(root.glob("export_*.json"))
    if len(exports) != 1:
        raise ValueError("Salida sin manifiesto único de desarrollo")
    export = json.loads(exports[0].read_text())
    if export.get("experiment_id") != root.name or export.get("task") not in ("validate", "tune") or export.get("final_test_evaluated") is not False:
        raise ValueError("Identidad de salida de desarrollo inválida")
    if export["source"] != json.loads((target / "source.json").read_text()):
        raise ValueError("Procedencia distinta del experimento congelado")
    for name, digest in export["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path) != digest:
            raise ValueError("Artefacto de desarrollo alterado")
    expected = set(export["files"]) | {exports[0].name}
    if {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} != expected:
        raise ValueError("Artefactos ajenos al manifiesto de desarrollo")
    for manifest_path in root.glob("finalists/*/model/training_manifest.json"):
        manifest = json.loads(manifest_path.read_text())
        if manifest["gold_sha256"] != export["source"]["study_gold_sha256"] or manifest["registry_sha256"] != sha256(settings["registry"]):
            raise ValueError("Finalista ajeno al estudio")
        for name, digest in manifest["checkpoint_hashes"].items():
            path = (manifest_path.parent / name).resolve()
            if not path.is_relative_to(manifest_path.parent.resolve()) or sha256(path) != digest:
                raise ValueError("Checkpoint finalista alterado")
    for name in expected:
        source, destination = root / name, target / name
        if destination.exists() and sha256(destination) != sha256(source):
            raise FileExistsError(f"No sobrescribir artefactos del experimento: {name}")
    for name in expected:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(root / name, destination)
    atomic_json(target / f"import_{export['task']}.json", {"imported_at": stamp(), "archive_sha256": sha256(archive_path), "final_test_evaluated": False})
    if export["task"] == "tune" and (target / "selection.json").exists():
        # AI augmentation already exports its complete report. Preserve the sealed
        # bytes: local NumPy/matplotlib versions can otherwise change JSON/PNG.
        if json.loads((target / "plan.json").read_text()).get("protocol") not in ("targeted-ai-augmentation-v1", "targeted-human-refinement-v1"):
            from .development import render_comparison
            render_comparison(target)


def _kaggle(settings: dict, arguments: list[str]) -> str:
    """Use the existing credential environment without logging credentials or HTTP bodies."""
    import os
    import subprocess
    import sys
    from dotenv import load_dotenv
    from ..kaggle import _env_for_kaggle
    load_dotenv(settings["_root"] / ".env")
    executable = Path(sys.executable).with_name("kaggle")
    if not executable.exists():
        raise RuntimeError("Instala el extra kaggle")
    completed = subprocess.run([str(executable), *arguments], env=_env_for_kaggle(settings), capture_output=True, text=True)
    if completed.returncode:
        # Do not echo request headers, config files, or potential secrets in third-party errors.
        import re
        error = completed.stderr + completed.stdout
        statuses = sorted(set(re.findall(r"\b(?:400|401|403|404|409|429|500|502|503)\b", error)))
        categories = [word for word in ("slug", "title", "quota", "permission", "gpu", "accelerator", "authentication", "unauthorized", "forbidden", "dataset", "not found", "metadata", "code_file", "TypeError", "AttributeError") if word.lower() in error.lower()]
        atomic_json(settings["workspace"] / "last_kaggle_error.json", {"operation": arguments[:2], "exit_code": completed.returncode,
                    "http_statuses": statuses, "categories": categories})
        raise RuntimeError(f"Kaggle rechazó {arguments[0]} {arguments[1]} (código {completed.returncode}; HTTP {','.join(statuses) or 'sin estado'}; categorías {','.join(categories) or 'sin categoría'}). No se registró el cuerpo HTTP.")
    return completed.stdout


def validate_job(settings: dict, stage: Path, job: dict) -> None:
    kernel = json.loads((stage / "kernel/kernel-metadata.json").read_text())
    dataset = json.loads((stage / "dataset/dataset-metadata.json").read_text())
    if kernel.get("id") != job["kernel_id"] or dataset.get("id") != job["dataset_id"] or kernel.get("is_private") is not True:
        raise ValueError("Metadatos de identidad/privacidad incompatibles con el trabajo preparado")
    if kernel.get("dataset_sources") != [job["dataset_id"]] or kernel.get("enable_gpu") is not True or kernel.get("enable_internet") is not True:
        raise ValueError("El kernel requiere únicamente su dataset dirigido, GPU e Internet")
    legacy = settings["source"]["kaggle"]
    if job["dataset_id"] == legacy["dataset_id"] or job["kernel_id"] == legacy["kernel_id"]:
        raise ValueError("Prohibido reutilizar recursos históricos")
    if sha256(stage / "kernel/kernel.py") != job["kernel_sha256"] or sha256(stage / "dataset/targeted_payload.tar.gz") != job["payload_sha256"]:
        raise ValueError("Código o payload alterado después de preparar")


def submit_job(settings: dict, run: Path, task: str, *, create: bool = False, experiment_id: str | None = None) -> None:
    stage = job_stage(run, task, experiment_id)
    job = json.loads((stage / "job_manifest.json").read_text())
    validate_job(settings, stage, job)
    if job.get("published"):
        raise ValueError("Este payload ya fue publicado; usa kaggle-start o kaggle-status")
    if sha256(stage / "dataset" / "targeted_payload.tar.gz") != job["payload_sha256"] or sha256(stage / "kernel" / "kernel.py") != job["kernel_sha256"]:
        raise ValueError("Payload/kernel cambiaron después de preparar la ejecución")
    if create:
        previous = 0
        _kaggle(settings, ["datasets", "create", "-p", str(stage / "dataset"), "-t", "-r", "skip"])
    else:
        status = json.loads(_kaggle(settings, ["datasets", "status", job["dataset_id"], "--format", "json"]))
        previous = int(status["current_version_number"])
        if str(status["status"]).lower() != "ready":
            raise ValueError("Ya hay una publicación en curso; no crear otra versión")
        _kaggle(settings, ["datasets", "version", "-p", str(stage / "dataset"), "-m", f"Targeted {task}: {run.name}", "-t", "-r", "skip"])
    job.update(published=True, expected_version=previous + 1, published_at=stamp())
    atomic_json(stage / "job_manifest.json", job)
    print(f"Dataset privado enviado; esperar versión {job['expected_version']} ready antes de kaggle-start.")


def start_job(settings: dict, run: Path, task: str, *, experiment_id: str | None = None) -> None:
    stage = job_stage(run, task, experiment_id)
    job = json.loads((stage / "job_manifest.json").read_text())
    validate_job(settings, stage, job)
    if not job.get("published") or job.get("started"):
        raise ValueError("El dataset debe publicarse y el trabajo no debe estar ya iniciado")
    status = json.loads(_kaggle(settings, ["datasets", "status", job["dataset_id"], "--format", "json"]))
    if str(status["status"]).lower() != "ready" or int(status["current_version_number"]) != job["expected_version"]:
        raise ValueError("La versión esperada todavía no está ready o fue sustituida; no se envió el kernel")
    if sha256(stage / "kernel" / "kernel.py") != job["kernel_sha256"]:
        raise ValueError("Kernel modificado después de preparar")
    response = _kaggle(settings, ["kernels", "push", "-p", str(stage / "kernel")])
    import re
    version = re.search(r"Kernel version (\d+)", response)
    if version:
        # Kaggle may canonicalize the slug from the title when creating a
        # notebook. Pin the returned URL, never assume the requested slug won.
        canonical = re.search(r"https://(?:www\.)?kaggle\.com/(?:code/)?([A-Za-z0-9_-]+/[A-Za-z0-9_-]+)", response)
        actual_id = canonical.group(1) if canonical else job["kernel_id"]
        job["kernel_version"] = int(version[1])
        job["resolved_kernel_id"] = actual_id
        job["kernel_ref"] = actual_id + "/" + version[1]
    job.update(started=True, started_at=stamp(), verified_dataset_version=int(status["current_version_number"]))
    atomic_json(stage / "job_manifest.json", job)
    print("Kernel GPU privado enviado. El kernel comprobará el SHA del input antes de ejecutar.")


def status_job(settings: dict, run: Path, task: str, *, list_files: bool = False, experiment_id: str | None = None) -> None:
    stage = job_stage(run, task, experiment_id)
    job = json.loads((stage / "job_manifest.json").read_text())
    dataset_status = _kaggle(settings, ["datasets", "status", job["dataset_id"], "--format", "json"])
    print(dataset_status.strip())
    if job.get("started"):
        print(_kaggle(settings, ["kernels", "status", job.get("kernel_ref", job["kernel_id"])]).strip())
    if list_files:
        print(_kaggle(settings, ["datasets", "files", "-d", job["dataset_id"], "--csv"]).strip())


def fetch_job(settings: dict, run: Path, task: str, *, experiment_id: str | None = None) -> None:
    stage = job_stage(run, task, experiment_id)
    job = json.loads((stage / "job_manifest.json").read_text())
    status = _kaggle(settings, ["kernels", "status", job.get("kernel_ref", job["kernel_id"])]).lower()
    if not any(value in status for value in ("complete", "error", "failed")):
        raise ValueError("El kernel aún no está COMPLETE; revisar estado/log si falló")
    destination = stage / "download"
    destination.mkdir(exist_ok=False)
    _kaggle(settings, ["kernels", "output", job.get("kernel_ref", job["kernel_id"]), "-p", str(destination), "-q",
                       "--file-pattern", r"(^|/)targeted_result\.tar\.gz$"])
    matches = list(destination.rglob("targeted_result.tar.gz"))
    if len(matches) != 1:
        raise ValueError("La salida no contiene exactamente un archivo dirigido")
    if task != "smoke":
        import_job(settings, run, matches[0])
    else:
        with tarfile.open(matches[0]) as archive:
            member = archive.extractfile("smoke.json")
            if member is None:
                raise ValueError("Smoke sin evidencia GPU")
            report = json.load(member)
        if not report.get("gpu") or not report.get("model_download_verified") or report.get("scientific_results") or report.get("logit_shape") != [1, 5]:
            raise ValueError("Smoke remoto inválido")
        atomic_json(stage / "smoke_verified.json", report)
    job.update(downloaded_at=stamp(), result_sha256=sha256(matches[0]))
    atomic_json(stage / "job_manifest.json", job)
    print("Resultados remotos descargados y verificados.")
