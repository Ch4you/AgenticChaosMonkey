from agent_chaos_sdk.config_loader import ReplayConfig, DEFAULT_REPLAY_IGNORE_PATHS


def test_replay_config_defaults_include_common_volatile_fields() -> None:
    config = ReplayConfig()
    for path in DEFAULT_REPLAY_IGNORE_PATHS:
        assert path in config.ignore_paths
