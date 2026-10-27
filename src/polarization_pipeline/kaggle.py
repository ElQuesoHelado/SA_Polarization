from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


def _env_for_kaggle(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    # Kaggle CLI creates this directory during import; keep it in ignored data.
    env.setdefault("KAGGLE_CONFIG_DIR", str(config["_root"] / "data" / ".kaggle-config"))
    # Kaggle CLI accepts either the newer token or username/key pair.
    if env.get("KAGGLE_API_TOKEN"):
        return env
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        return env
    raise ValueError("Configura KAGGLE_API_TOKEN o KAGGLE_USERNAME y KAGGLE_KEY en .env.")


def _run(args: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> str:
    venv_executable = Path(sys.executable).with_name("kaggle")
    executable = str(venv_executable) if venv_executable.is_file() else shutil.which("kaggle")
    if not executable:
        raise RuntimeError("No se encontró el comando `kaggle`; instala el extra con `pip install -e '.[kaggle]'`.")
    command = [executable, *args]
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError(f"Comando Kaggle falló ({completed.returncode}): {' '.join(args)}")
    return completed.stdout.strip()


def pull_dataset(config: dict[str, Any]) -> None:
    env = _env_for_kaggle(config)
    dataset_id = config["kaggle"]["dataset_id"]
    with tempfile.TemporaryDirectory(prefix="sa-polarization-data-") as temp:
        download_dir = Path(temp)
        _run(["datasets", "download", "-d", dataset_id, "-p", str(download_dir), "--unzip"], env=env)
        raw_target = config["paths"]["raw"]
        processed_target = config["paths"]["processed"]
        incoming = {"raw": [], "processed": []}
        ignored = []
        for source in download_dir.rglob("*"):
            if not source.is_file() or source.name == "dataset-metadata.json":
                continue
            suffix = source.suffix.lower()
            if suffix == ".json":
                incoming["raw"].append(source)
            elif suffix == ".csv":
                incoming["processed"].append(source)
            else:
                ignored.append(source.relative_to(download_dir))
        if not any(incoming.values()):
            raise ValueError(f"El dataset {dataset_id} no contiene archivos JSON ni CSV.")
        counts = Counter(path.name for files in incoming.values() for path in files)
        duplicate_names = {name for name, count in counts.items() if count > 1}
        if duplicate_names:
            raise ValueError(f"Hay nombres de archivo duplicados en el dataset: {', '.join(sorted(duplicate_names))}.")
        conflicts = [str(target) for name, target in (("raw", raw_target), ("processed", processed_target)) if incoming[name] and target.exists()]
        if conflicts:
            raise FileExistsError(f"Ya existen destinos locales: {', '.join(conflicts)}. No se copiaron datos.")
        for name, target in (("raw", raw_target), ("processed", processed_target)):
            files = incoming[name]
            if not files:
                print(f"[AVISO] El dataset no contiene archivos para {name}/")
                continue
            target.mkdir(parents=True, exist_ok=True)
            for source in files:
                destination = target / source.name
                if destination.exists():
                    raise FileExistsError(f"Dos archivos descargados comparten el nombre {source.name}; no se sobrescribieron.")
                shutil.copy2(source, destination)
        if ignored:
            print(f"Se omitieron {len(ignored)} archivos no compatibles.")


def _kaggle_directory(config: dict[str, Any], name: str, default: str) -> Path:
    path = Path(config["kaggle"].get(name, default))
    return path if path.is_absolute() else Path(config["_root"]) / path


def _ensure_dataset_metadata(config: dict[str, Any], env: dict[str, str], *, create: bool = False) -> Path:
    metadata = _kaggle_directory(config, "dataset_dir", "kaggle/dataset") / "dataset-metadata.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    if not metadata.is_file():
        dataset_id = config["kaggle"]["dataset_id"]
        if create:
            template_id = config["kaggle"].get("metadata_template_dataset_id")
            if not template_id:
                raise ValueError("Configura metadata_template_dataset_id para crear el dataset aislado.")
            with tempfile.TemporaryDirectory(prefix="sa-polarization-metadata-") as temp:
                _run(["datasets", "metadata", template_id, "-p", temp], env=env)
                template_path = Path(temp) / "dataset-metadata.json"
                import json
                template = json.loads(template_path.read_text(encoding="utf-8"))
            licenses = template.get("licenses") or template.get("info", {}).get("licenses")
            if not isinstance(licenses, list) or len(licenses) != 1:
                raise ValueError(f"No se pudo derivar una licencia única de la metadata de {template_id}.")
            template["id"] = dataset_id
            template["title"] = config["kaggle"].get("dataset_title", template.get("title", dataset_id))
            template["licenses"] = licenses
            metadata.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            print(f"Descargando metadata de {dataset_id}.")
            _run(["datasets", "metadata", dataset_id, "-p", str(metadata.parent)], env=env)
    return metadata


def _prepare_dataset(config: dict[str, Any], stage: Path, env: dict[str, str], *, create: bool = False) -> None:
    metadata = _ensure_dataset_metadata(config, env, create=create)
    processed_file = config["paths"]["processed"] / config["preprocess"]["comments_file"]
    if not processed_file.is_file():
        raise FileNotFoundError(f"No existe {processed_file}; ejecuta preprocess antes de publicar.")
    import json
    dataset_metadata = json.loads(metadata.read_text(encoding="utf-8"))
    metadata_id = dataset_metadata.get("id")
    if metadata_id is None and isinstance(dataset_metadata.get("info"), dict):
        info = dataset_metadata["info"]
        metadata_id = f"{info.get('ownerUser', '')}/{info.get('datasetSlug', '')}".strip("/")
    if metadata_id != config["kaggle"]["dataset_id"]:
        raise ValueError(f"El id de dataset-metadata.json debe ser {config['kaggle']['dataset_id']}")
    stage.mkdir(parents=True, exist_ok=True)
    dataset_metadata["id"] = config["kaggle"]["dataset_id"]
    (stage / "dataset-metadata.json").write_text(
        json.dumps(dataset_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    names: set[str] = set()
    count = 0
    for source_dir in (config["paths"]["raw"], config["paths"]["processed"]):
        if not source_dir.exists():
            continue
        for source in source_dir.rglob("*"):
            if not source.is_file() or source.suffix.lower() not in {".json", ".csv"}:
                continue
            if source.name in names:
                raise ValueError(f"No se puede publicar en raíz: nombre de archivo duplicado {source.name}.")
            names.add(source.name)
            shutil.copy2(source, stage / source.name)
            count += 1
    if count == 0:
        raise FileNotFoundError("No se encontraron archivos JSON ni CSV para publicar.")


def publish_dataset(config: dict[str, Any], message: str, *, create: bool = False) -> None:
    env = _env_for_kaggle(config)
    with tempfile.TemporaryDirectory(prefix="sa-polarization-upload-") as temp:
        stage = Path(temp)
        _prepare_dataset(config, stage, env, create=create)
        print(f"Se {'creará' if create else 'publicará una versión de'} {config['kaggle']['dataset_id']} (privado por defecto).")
        if create:
            _run(["datasets", "create", "-p", str(stage), "-t", "-r", "skip"], env=env)
        else:
            _run(["datasets", "version", "-p", str(stage), "-m", message, "-t", "-r", "skip"], env=env)


def infer(config: dict[str, Any]) -> None:
    env = _env_for_kaggle(config)
    root: Path = config["_root"]
    kernel_dir = _kaggle_directory(config, "kernel_dir", "kaggle/kernel")
    metadata_path = kernel_dir / "kernel-metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Falta {metadata_path}; inicializa un kernel Kaggle y configura su metadata.")
    expected_id = config["kaggle"]["kernel_id"]
    import json
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("id") != expected_id:
        raise ValueError(f"kernel-metadata.json id debe coincidir con config: {expected_id}")
    if metadata.get("code_file") != "kernel.py":
        raise ValueError("kernel-metadata.json debe apuntar a kernel.py")
    if not metadata.get("enable_gpu"):
        raise ValueError("El kernel debe tener enable_gpu=true")
    if config["kaggle"]["dataset_id"] not in metadata.get("dataset_sources", []):
        raise ValueError("Agrega el dataset configurado a dataset_sources en kernel-metadata.json")
    kernel_source = (kernel_dir / "kernel.py").read_text(encoding="utf-8")
    if f'MODEL_ID = "{config["model"]["id"]}"' not in kernel_source:
        raise ValueError("El modelo configurado en pipeline.toml debe coincidir con MODEL_ID en kaggle/kernel/kernel.py")
    if f'BATCH_SIZE = {config["model"]["batch_size"]}' not in kernel_source:
        raise ValueError("batch_size en pipeline.toml debe coincidir con BATCH_SIZE en kaggle/kernel/kernel.py")
    print(f"Se enviará el kernel {expected_id} para ejecución GPU en Kaggle.")
    _run(["kernels", "push", "-p", str(kernel_dir)], env=env)
    # The push command may return while Kaggle is still running the version.
    deadline = time.monotonic() + config["kaggle"].get("timeout_seconds", 10800) + 600
    while time.monotonic() < deadline:
        status = _run(["kernels", "status", expected_id], env=env).lower()
        if "complete" in status:
            break
        if "error" in status or "failed" in status:
            raise RuntimeError(f"El kernel terminó con error: {status}")
        time.sleep(20)
    else:
        raise TimeoutError(f"Tiempo agotado esperando al kernel {expected_id}")
    output_dir: Path = config["paths"]["outputs"]
    output_dir.mkdir(parents=True, exist_ok=True)
    _run(["kernels", "output", expected_id, "-p", str(output_dir), "-o"], env=env)
    expected_output = output_dir / "datos_clasificados.csv"
    if not expected_output.is_file():
        raise FileNotFoundError(f"Kaggle no devolvió {expected_output}; revisa los logs del kernel.")
