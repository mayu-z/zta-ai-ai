from __future__ import annotations

from pathlib import Path

from app.agentic.registry.migration_generator import MigrationGenerator


def test_migration_generator_detects_fetch_action_approval_steps(tmp_path: Path) -> None:
    source = '''
class FeeReminderAgent:
    async def execute(self, action, ctx, decision, claim_set):
        await self._scope.fetch_scoped(action, ctx, decision)
        await self._compiler.execute_write(action, claim_set)
        await self._approval.evaluate(action, claim_set, ctx)
'''
    py_file = tmp_path / "fee_reminder.py"
    py_file.write_text(source, encoding="utf-8")

    generator = MigrationGenerator()
    definition = generator.generate(
        py_file,
        action_registry_seed_data={
            "fee_reminder_v1": {
                "trigger_type": "user_query",
                "allowed_personas": ["student"],
                "required_data_scope": ["fees.own"],
            }
        },
    )

    assert definition["agent_id"] == "fee_reminder_v1"
    step_types = {step["type"] for step in definition["steps"]}
    assert {"fetch", "action", "approval"}.issubset(step_types)
    assert definition["edges"][0]["from"] == "START"
    assert definition["edges"][-1]["to"] == "END_SUCCESS"


def test_migration_generator_generate_all_skips_base_agent(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    output_dir = tmp_path / "out"
    agents_dir.mkdir()

    (agents_dir / "base_agent.py").write_text("class Base: pass\n", encoding="utf-8")
    (agents_dir / "email_send.py").write_text(
        "class E:\n    async def execute(self):\n        await self._compiler.execute_write()\n",
        encoding="utf-8",
    )

    generator = MigrationGenerator()
    results = generator.generate_all(agents_dir=agents_dir, output_dir=output_dir)

    assert len(results) == 1
    assert results[0]["file"] == "email_send.py"
    assert (output_dir / "email_send_v1.json").exists()
