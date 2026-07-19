from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_config_loads_current_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "f2a3b4c5d6e7"
