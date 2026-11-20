"""User services and live process leases; recorded phases are never liveness."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from ..common import atomic_json, stamp
from .state import verify


def lease_active(path):
    try:
        with path.open('r') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
    except FileNotFoundError:
        pass
    return False


@contextmanager
def heartbeat(study):
    stop = threading.Event()
    path = study / 'advancement_heartbeat.json'
    started = stamp()
    def write(running=True):
        atomic_json(path, dict(pid=os.getpid(), started_at=started, heartbeat_at=stamp(), running=running))
    def beat():
        while not stop.wait(30):
            write()
    write()
    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        write(False)


def status(settings, study):
    verify(study)
    out = settings['outputs'] / study.name
    def stored(path):
        return json.loads(path.read_text()) if path.exists() else None
    return dict(read_only=True,
        controller_active=lease_active(study / 'advancement.lock'),
        collector_active=lease_active(settings['workspace'] / 'publication_collection.lock'),
        preparer_active=lease_active(study / 'local_preparation.lock'),
        recorded_controller_state=stored(out / 'advancement/state.json'),
        controller_heartbeat=stored(study / 'advancement_heartbeat.json'),
        snapshot_frozen=(study / 'freeze.json').exists())


def unit_name(study, role):
    return 'sa-polarization-' + hashlib.sha256(str(study.resolve()).encode()).hexdigest()[:12] + '-' + role


def start_services(settings, study, config_path, budget):
    verify(study)
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError('daily-api-budget debe ser positivo')
    config_path = Path(config_path)
    config_path = config_path if config_path.is_absolute() else settings['_root'] / config_path
    root = settings['_root']
    logs = settings['outputs'] / study.name / 'runtime_logs'
    logs.mkdir(parents=True, exist_ok=True)
    live = status(settings, study)
    started = {}
    for role, command, active in (
        ('advance', ['advance', '--watch', '--daily-api-budget', str(budget)], live['controller_active']),
        ('prepare', ['prepare-local', '--watch'], live['preparer_active'])):
        if role == 'prepare' and live['snapshot_frozen']:
            started[role] = 'snapshot_frozen'
            continue
        unit = unit_name(study, role)
        query = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '--value'], capture_output=True, text=True)
        if query.returncode == 0 and query.stdout.strip() in {'active', 'activating'}:
            started[role] = 'already_active'
            continue
        if active:
            raise RuntimeError('Hay un proceso externo activo; no se iniciará un duplicado')
        args = ['systemd-run', '--user', '--collect', '--unit=' + unit,
            '--property=Type=exec', '--property=Restart=no', '--working-directory=' + str(root),
            '--property=StandardOutput=append:' + str(logs / (role + '.log')),
            '--property=StandardError=append:' + str(logs / (role + '.log')),
            sys.executable, '-c', 'from polarization_pipeline.cli import main; main()', 'targeted', 'publication',
            *command, '--config', str(config_path)]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('No se pudo iniciar el servicio de usuario; comprobar systemd --user')
        started[role] = unit
    return dict(services=started, logs=str(logs), restart_after_reboot=False)
