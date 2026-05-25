"""
Testes para o CLI command flask amazon-daily-sync (app/commands.py).

AmazonConnection usa schema="public" (PostgreSQL-only) — a query ao BD
é isolada em _fetch_all_amazon_connections(), patchada nos testes.
"""
from unittest.mock import MagicMock, patch

MODULE = "app.commands"
FETCH_FN = f"{MODULE}._fetch_all_amazon_connections"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_conn(user_id=1, conn_id=10, marketplace_id="A2Q3Y263D00KWC"):
    c = MagicMock()
    c.user_id = user_id
    c.id = conn_id
    c.marketplace_id = marketplace_id
    return c


def _get_command(app):
    return app.cli.commands["amazon-daily-sync"]


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestAmazonDailySync:

    def test_no_connections_prints_zero_jobs(self, app, db):
        """Sem AmazonConnection no banco → mensagem de 0 jobs, nenhum enqueue."""
        from click.testing import CliRunner
        cmd = _get_command(app)
        runner = CliRunner()

        with patch(FETCH_FN, return_value=[]):
            with app.app_context():
                result = runner.invoke(cmd, [])

        assert result.exit_code == 0
        assert "0 jobs" in result.output

    def test_enqueues_one_job_per_connection(self, app, db):
        """Duas conexões → enqueue chamado exatamente 2 vezes."""
        from click.testing import CliRunner
        cmd = _get_command(app)
        runner = CliRunner()

        conns = [_fake_conn(user_id=1, conn_id=10), _fake_conn(user_id=2, conn_id=20)]
        mock_job = MagicMock()
        mock_job.id = "fake-job-id"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with patch(FETCH_FN, return_value=conns):
            with app.app_context():
                app.extensions["rq_queue"] = mock_queue
                result = runner.invoke(cmd, [])

        assert result.exit_code == 0
        assert mock_queue.enqueue.call_count == 2
        assert "2 job(s) enfileirado(s)" in result.output

    def test_dry_run_does_not_enqueue(self, app, db):
        """--dry-run lista conexões sem enfileirar nenhum job."""
        from click.testing import CliRunner
        cmd = _get_command(app)
        runner = CliRunner()

        conns = [_fake_conn(user_id=1, conn_id=10)]
        mock_queue = MagicMock()

        with patch(FETCH_FN, return_value=conns):
            with app.app_context():
                app.extensions["rq_queue"] = mock_queue
                result = runner.invoke(cmd, ["--dry-run"])

        assert result.exit_code == 0
        assert "dry-run" in result.output
        assert "user_id=1" in result.output
        mock_queue.enqueue.assert_not_called()

    def test_dry_run_no_connections(self, app, db):
        """--dry-run sem conexões não quebra."""
        from click.testing import CliRunner
        cmd = _get_command(app)
        runner = CliRunner()

        with patch(FETCH_FN, return_value=[]):
            with app.app_context():
                result = runner.invoke(cmd, ["--dry-run"])

        assert result.exit_code == 0
        assert "0 jobs" in result.output

    def test_enqueue_uses_days_option(self, app, db):
        """--days N é passado para job_sync_full como terceiro argumento."""
        from click.testing import CliRunner
        cmd = _get_command(app)
        runner = CliRunner()

        conns = [_fake_conn(user_id=1, conn_id=10)]
        mock_job = MagicMock()
        mock_job.id = "jid"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with patch(FETCH_FN, return_value=conns):
            with app.app_context():
                app.extensions["rq_queue"] = mock_queue
                result = runner.invoke(cmd, ["--days", "7"])

        assert result.exit_code == 0
        call_args = mock_queue.enqueue.call_args
        # enqueue(job_sync_full, user_id, conn_id, days, job_timeout=...)
        assert call_args[0][3] == 7
