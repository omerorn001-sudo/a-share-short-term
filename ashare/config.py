from pathlib import Path
import copy
import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path=None, overrides=None):
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg = copy.deepcopy(cfg)
    for key, val in (overrides or {}).items():  # "exit.stop_loss": 0.05
        node = cfg
        *parents, leaf = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = val
    return cfg
