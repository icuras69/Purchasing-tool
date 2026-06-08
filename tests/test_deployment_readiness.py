from pathlib import Path

from scripts.check_deployment_secrets import format_findings, scan_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fastapi_app_imports_for_deployment():
    from app.main import app

    assert app.title == "Purchasing AI"


def test_render_blueprint_is_valid_yaml_with_safe_staging_defaults():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "\t" not in blueprint
    assert "databases:" in blueprint
    assert "name: purchasing-ai-staging-db" in blueprint
    assert "plan: basic-256mb" in blueprint
    assert "name: purchasing-ai-api" in blueprint
    assert "runtime: python" in blueprint
    assert "autoDeployTrigger: 'off'" in blueprint
    assert "preDeployCommand: python -m alembic upgrade head" in blueprint
    assert "startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "key: ORDERPRO_SYNC_ENABLED" in blueprint
    assert "value: false" in blueprint
    assert "key: LLM_PROVIDER" in blueprint
    assert "value: mock" in blueprint
    assert "key: ENABLE_REAL_LLM" in blueprint
    assert "key: ORDERPRO_API_TOKEN" in blueprint
    assert "sync: false" in blueprint
    assert "name: purchasing-ai-frontend" in blueprint
    assert "runtime: static" in blueprint
    assert "rootDir: frontend" in blueprint
    assert "staticPublishPath: ./dist" in blueprint
    assert "key: VITE_API_BASE_URL" in blueprint
    assert "source: /*" in blueprint
    assert "destination: /index.html" in blueprint


def test_requirements_deploy_is_utf8_and_excludes_dev_or_gpu_dependencies():
    deploy_requirements = (PROJECT_ROOT / "requirements-deploy.txt").read_text(encoding="utf-8")
    normalized = deploy_requirements.lower()

    assert "fastapi==" in normalized
    assert "sqlalchemy==" in normalized
    assert "alembic==" in normalized
    assert "psycopg2-binary==" in normalized
    assert "uvicorn==" in normalized
    assert "httpx==" in normalized
    assert "pytest" not in normalized
    assert "jupyter" not in normalized
    assert "torch" not in normalized
    assert "pandas" not in normalized


def test_python_version_prefers_stable_render_compatible_runtime():
    assert (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.8"


def test_secret_scanner_detects_env_files_tokens_and_database_dumps(tmp_path):
    (tmp_path / ".env").write_text("ORDERPRO_API_TOKEN=op_secret_token_value_123456\n", encoding="utf-8")
    (tmp_path / "backup.dump").write_text("not actually a dump", encoding="utf-8")
    (tmp_path / "config.py").write_text(
        "DATABASE_URL='postgresql://user:secret_password@db.example.com/app'\n",
        encoding="utf-8",
    )

    findings = scan_path(tmp_path)
    rendered = format_findings(findings)

    assert ".env - env file must not be committed" in rendered
    assert "backup.dump - database dump/export file must not be committed" in rendered
    assert "PostgreSQL URL with password" in rendered
    assert "secret_password" not in rendered
    assert "op_secret_token_value" not in rendered


def test_secret_scanner_allows_example_env_files(tmp_path):
    (tmp_path / ".env.example").write_text("ORDERPRO_API_TOKEN=\nOPENAI_API_KEY=\n", encoding="utf-8")

    assert scan_path(tmp_path) == []
