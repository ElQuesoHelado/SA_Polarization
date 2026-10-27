from __future__ import annotations

import copy
import json
import math
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import analyze
from .kaggle import infer, publish_dataset
from .preprocess import preprocess


def _sample_json(source: Path, destination: Path, fraction: float, seed: int) -> tuple[int, int]:
    document = json.loads(source.read_text(encoding="utf-8"))
    videos = document.get("videos")
    if not isinstance(videos, list):
        raise ValueError(f"{source} no contiene una lista videos compatible con el preprocesador.")

    comment_locations: list[tuple[int, int]] = []
    for video_index, video in enumerate(videos):
        if isinstance(video, dict) and isinstance(video.get("comentarios"), list):
            comment_locations.extend(
                (video_index, comment_index)
                for comment_index, comment in enumerate(video["comentarios"])
                if isinstance(comment, dict)
            )
    if not comment_locations:
        raise ValueError(f"No se encontraron comentarios compatibles en {source}.")

    sample_size = min(len(comment_locations), max(1, math.ceil(len(comment_locations) * fraction)))
    selected = set(random.Random(seed).sample(range(len(comment_locations)), sample_size))
    selected_locations = {comment_locations[index] for index in selected}
    sampled_videos = []
    for video_index, video in enumerate(videos):
        if not isinstance(video, dict):
            continue
        comments = video.get("comentarios")
        if not isinstance(comments, list):
            continue
        sampled_comments = [
            comment for comment_index, comment in enumerate(comments)
            if (video_index, comment_index) in selected_locations
        ]
        if sampled_comments:
            sampled_video = dict(video)
            sampled_video["comentarios"] = sampled_comments
            sampled_videos.append(sampled_video)

    document["videos"] = sampled_videos
    if "cantidad_videos" in document:
        document["cantidad_videos"] = len(sampled_videos)
    destination.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(comment_locations), sample_size


def _prepare_kernel(config: dict[str, Any], run_dir: Path) -> Path:
    root: Path = config["_root"]
    source_dir = root / "kaggle" / "kernel"
    source_metadata = source_dir / "kernel-metadata.json"
    metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
    target = run_dir / "kernel"
    target.mkdir(parents=True)
    shutil.copy2(source_dir / "kernel.py", target / "kernel.py")
    metadata["id"] = config["kaggle"]["kernel_id"]
    metadata["title"] = "SA Polarization Smoke Test Inference"
    metadata["is_private"] = True
    metadata["dataset_sources"] = [config["kaggle"]["dataset_id"]]
    (target / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def run_smoke_test(
    config: dict[str, Any], *, fraction: float | None = None, seed: int | None = None,
    create_dataset: bool = False,
) -> None:
    smoke = config.get("smoke_test", {})
    fraction = smoke.get("fraction", 0.25) if fraction is None else fraction
    seed = smoke.get("seed", 42) if seed is None else seed
    if not 0 < fraction <= 1:
        raise ValueError("fraction debe ser mayor que 0 y menor o igual que 1.")

    root: Path = config["_root"]
    source_dir = Path(smoke.get("source_raw", "raw_data"))
    if not source_dir.is_absolute():
        source_dir = root / source_dir
    source_files = sorted(source_dir.glob("*.json"))
    if not source_files:
        raise FileNotFoundError(f"No se encontraron JSON de YouTube en {source_dir}.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "data" / "smoke-test" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    test_config = copy.deepcopy(config)
    test_config["paths"]["raw"] = run_dir / "raw"
    test_config["paths"]["processed"] = run_dir / "processed"
    test_config["paths"]["outputs"] = run_dir / "outputs"
    test_config["paths"]["raw"].mkdir(parents=True)
    test_config["kaggle"]["dataset_id"] = smoke["dataset_id"]
    test_config["kaggle"]["kernel_id"] = smoke["kernel_id"]
    test_config["kaggle"]["dataset_title"] = smoke.get("dataset_title", "SA Polarization Smoke Test Data")
    test_config["kaggle"]["dataset_dir"] = root / "data" / "smoke-test" / "dataset"
    test_config["kaggle"]["metadata_template_dataset_id"] = config["kaggle"]["dataset_id"]
    test_config["kaggle"]["kernel_dir"] = _prepare_kernel(test_config, run_dir)

    manifest: dict[str, Any] = {"fraction": fraction, "seed": seed, "files": {}}
    for source in source_files:
        original_count, sampled_count = _sample_json(
            source, test_config["paths"]["raw"] / source.name, fraction, seed
        )
        manifest["files"][source.name] = {"comments": original_count, "sampled": sampled_count}
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Subset guardado en {test_config['paths']['raw']} ({fraction:.0%} por archivo; semilla {seed}).")

    preprocess(test_config)
    publish_dataset(
        test_config,
        f"Smoke test {run_id}: {fraction:.0%} por archivo, seed {seed}",
        create=create_dataset,
    )
    infer(test_config)
    analyze(test_config)
    print(f"Prueba completa. Manifiesto y resultados: {run_dir}")
