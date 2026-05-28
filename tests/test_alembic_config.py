from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_config_loads_current_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "b7a4c2d9e101"
