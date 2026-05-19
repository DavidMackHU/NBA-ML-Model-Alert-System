def test_hello_world() -> None:
    assert 1 + 1 == 2


def test_src_packages_importable() -> None:
    import src.ingestion
    import src.features
    import src.models
    import src.edge
    import src.alerts
    import src.backtest
    import src.db
    import src.config
    import src.api  # noqa: F401
