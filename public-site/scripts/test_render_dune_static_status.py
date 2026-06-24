#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import tempfile
import textwrap
import time
import unittest


SCRIPT = pathlib.Path(__file__).with_name("render-dune-static-status.sh")


class StaticStatusRenderTest(unittest.TestCase):
    def render_status(self, restart_state):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dune_root = root / "dune"
            static_dir = root / "static"
            bin_dir = root / "bin"
            status_file = static_dir / "status.html"
            index_file = static_dir / "index.html"
            restart_state_file = dune_root / "backups" / "admin-panel" / "restart-jobs.json"
            scripts_dir = dune_root / "scripts"
            scripts_dir.mkdir(parents=True)
            static_dir.mkdir()
            bin_dir.mkdir()
            restart_state_file.parent.mkdir(parents=True)
            restart_state_file.write_text(json.dumps(restart_state), encoding="utf-8")
            index_file.write_text(
                "<html><body><!-- STATUS_BEGIN --><div id=\"server-status\"></div><!-- STATUS_END --></body></html>",
                encoding="utf-8",
            )
            (dune_root / ".env").write_text("DUNE_WORLD_PARTITION_COUNT=31\n", encoding="utf-8")
            status_sh = scripts_dir / "status.sh"
            status_sh.write_text(
                "#!/bin/sh\n"
                "echo 'current_ready_alive=31 current_alive_active=31 active_servers=31 partitions=31 game_sg_connections=31 admin_sg_connections=1'\n",
                encoding="utf-8",
            )
            status_sh.chmod(0o755)
            fake_docker = bin_dir / "docker"
            fake_docker.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import sys
                    if sys.argv[1] == "ps":
                        for service in ("survival", "deep-desert", "deep-desert-pvp"):
                            print(f"id-{service}\\t{service}")
                    elif sys.argv[1] == "inspect":
                        print(json.dumps([{
                            "State": {"Status": "running", "StartedAt": "2026-06-22T16:00:00Z"},
                            "RestartCount": 0,
                        }]))
                    else:
                        raise SystemExit(2)
                    """
                ),
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "DUNE_ROOT": str(dune_root),
                "INDEX_FILE": str(index_file),
                "STATUS_FILE": str(status_file),
                "STATIC_DIR": str(static_dir),
                "SOURCE_INDEX_FILE": str(root / "missing-source-index.html"),
                "CONFIGURE_SCRIPT": str(root / "missing-configure.sh"),
                "DRIFT_CHECK_SCRIPT": str(root / "missing-drift.sh"),
                "DUNE_PUBLIC_RESTART_STATE_FILE": str(restart_state_file),
            }
            subprocess.run([str(SCRIPT)], env=env, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return status_file.read_text(encoding="utf-8")

    def test_elapsed_time_uses_completed_maintenance_job(self):
        executed_at = time.time() - 3600
        html = self.render_status({
            "jobs": [{
                "id": "daily",
                "status": "executed",
                "action": "restart",
                "execute": True,
                "target": "all",
                "targetLabel": "All services",
                "backup": True,
                "executedAt": executed_at,
            }]
        })

        self.assertIn("Since maintenance", html)
        self.assertIn("<strong>Last maintenance</strong>", html)
        self.assertIn("<strong>Backup</strong> requested", html)
        self.assertIn("Most recent container restart", html)

    def test_elapsed_time_uses_failed_maintenance_attempt(self):
        executed_at = time.time() - 7200
        html = self.render_status({
            "jobs": [{
                "id": "daily",
                "status": "failed",
                "action": "restart",
                "execute": True,
                "target": "all",
                "targetLabel": "All services",
                "backup": True,
                "executedAt": executed_at,
            }]
        })

        self.assertIn("Since maintenance", html)
        self.assertIn("<strong>Status</strong> failed", html)
        self.assertIn("<strong>Backup</strong> requested", html)

    def test_stale_maintenance_marks_schedule_stale(self):
        executed_at = time.time() - (48 * 3600)
        html = self.render_status({
            "jobs": [{
                "id": "daily",
                "status": "executed",
                "action": "restart",
                "execute": True,
                "target": "all",
                "targetLabel": "All services",
                "backup": True,
                "executedAt": executed_at,
            }]
        })

        self.assertIn("Since maintenance", html)
        self.assertIn("<strong>Schedule</strong> stale", html)
        self.assertIn("status-dot status-warn", html)

    def test_missing_maintenance_job_falls_back_to_restart_label(self):
        html = self.render_status({"jobs": []})

        self.assertIn("Since restart", html)
        self.assertIn("<strong>Most recent restart</strong>", html)


if __name__ == "__main__":
    unittest.main()
