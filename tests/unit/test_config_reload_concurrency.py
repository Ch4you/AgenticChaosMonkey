import threading
from pathlib import Path

from agent_chaos_sdk.proxy.addon import ChaosProxyAddon


def _write_config(path: Path, experiment_id: str) -> None:
    contents = (
        f"experiment_id: {experiment_id}\n"
        "strategies: []\n"
    )
    path.write_text(contents, encoding="utf-8")


def test_config_reload_thread_safety(tmp_path) -> None:
    config_path = tmp_path / "chaos_config.yaml"
    _write_config(config_path, "exp-a")

    addon = ChaosProxyAddon(config_path=str(config_path))

    errors = []

    def reloader() -> None:
        try:
            for _ in range(50):
                addon._reload_config()
        except Exception as exc:  # noqa: BLE001 - test collects exceptions
            errors.append(exc)

    def writer() -> None:
        try:
            for i in range(10):
                _write_config(config_path, f"exp-{i}")
                addon._reload_config()
        except Exception as exc:  # noqa: BLE001 - test collects exceptions
            errors.append(exc)

    threads = [threading.Thread(target=reloader) for _ in range(4)]
    threads.append(threading.Thread(target=writer))

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    addon.done()
    assert not errors
