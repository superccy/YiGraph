"""Run with: python -m unittest discover -s web/tests -v (no engine initialization)."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

path = Path(__file__).resolve().parents[1] / "frontend/route/intent_clarification.py"
spec = importlib.util.spec_from_file_location("web_intent_gate", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def result(query, criterion=None, missing=False):
    return {
        "status": "needs_clarification" if missing else "ready",
        "intent": {"object": "交易图", "goal": query, "criteria": criterion,
                   "criteria_required": missing or criterion is not None,
                   "criteria_explanation": "A business decision needs a rule." if missing or criterion else "An explicit computation needs no extra threshold."},
        "evidence": {"object": "交易图", "goal": query, "criteria": criterion or ""},
        "missing_fields": ["criteria"] if missing else [],
        "question": "请说明异常类型和判断标准。" if missing else "",
    }


class ScriptedReasoner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


class IntentGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gate = module.IntentGate()
        self.owner = ("client-a", "conversation-a")
        self.context = {"dataset": "交易图", "dataset_type": "graph", "model": "paper-model", "mode": "interact", "expert_mode": False}

    def engine(self, *responses):
        reasoner = ScriptedReasoner(*responses)
        return SimpleNamespace(scheduler=SimpleNamespace(reasoner=reasoner,
            dataset_manager=SimpleNamespace(get_dataset_info=lambda *_: [])))

    async def test_explicit_computation_passes_without_an_extra_threshold(self):
        query = "计算交易图的 PageRank"
        engine = self.engine(result(query))
        prepared = await self.gate.prepare(self.owner, query, self.context, engine)
        self.assertEqual(prepared.query, query)
        self.assertIsNone(prepared.clarification)
        self.assertEqual(len(engine.scheduler.reasoner.calls), 1)

    async def test_ambiguous_request_is_stopped_and_partial_reply_asks_again(self):
        query = "检测异常"
        engine = self.engine(result(query, missing=True), result(query, missing=True))
        first = await self.gate.prepare(self.owner, query, self.context, engine)
        self.assertEqual(first.query, "")
        self.assertEqual(first.clarification["missing_fields"], ["criteria"])
        token = first.clarification["clarification_id"]
        second = await self.gate.prepare(self.owner, "账户", self.context, engine, token)
        self.assertEqual(second.query, "")
        self.assertEqual(second.clarification["clarification_id"], token)
        payload = json.loads(engine.scheduler.reasoner.calls[-1][1]["content"])
        self.assertEqual(payload["original_request"], query)
        self.assertEqual(payload["user_replies"], ["账户"])

    async def test_clarified_query_preserves_the_original_and_confirmed_rule(self):
        query = "检测异常"
        rule = "检测账户，交易金额超过 100000 才视为异常，输出账户与交易。"
        engine = self.engine(result(query, missing=True), result(query, criterion=rule))
        first = await self.gate.prepare(self.owner, query, self.context, engine)
        changed_context = {**self.context, "dataset": "another-dataset", "mode": "normal"}
        ready = await self.gate.prepare(self.owner, rule, changed_context, engine, first.clarification["clarification_id"])
        self.assertIn(query, ready.query)
        self.assertIn(rule, ready.query)
        self.assertEqual(ready.context, self.context)
        self.assertIsNone(ready.clarification)
        self.assertFalse(self.gate.has_pending(self.owner))

    async def test_other_clients_and_conversations_cannot_reuse_a_token(self):
        engine = self.engine(result("检测异常", missing=True))
        first = await self.gate.prepare(self.owner, "检测异常", self.context, engine)
        for owner in [("client-b", "conversation-a"), ("client-a", "conversation-b")]:
            with self.assertRaises(module.ClarificationError):
                await self.gate.prepare(owner, "已说明", self.context, engine, first.clarification["clarification_id"])
        self.assertEqual(len(engine.scheduler.reasoner.calls), 1)

    async def test_expired_token_requires_a_new_complete_request(self):
        engine = self.engine(result("检测异常", missing=True))
        first = await self.gate.prepare(self.owner, "检测异常", self.context, engine)
        token = first.clarification["clarification_id"]
        self.gate.pending[token].expires = 0
        with self.assertRaises(module.ClarificationError) as raised:
            await self.gate.prepare(self.owner, "循环交易", self.context, engine, token)
        self.assertTrue(raised.exception.restart_required)

    async def test_failed_check_preserves_the_previous_pending_turn(self):
        engine = self.engine(result("检测异常", missing=True), "not JSON")
        first = await self.gate.prepare(self.owner, "检测异常", self.context, engine)
        token = first.clarification["clarification_id"]
        with self.assertRaises(module.ClarificationError):
            await self.gate.prepare(self.owner, "循环交易", self.context, engine, token)
        self.assertEqual(self.gate.pending[token].replies, [])

    async def test_malformed_incomplete_or_invented_decisions_never_pass(self):
        query = "检测异常"
        incomplete = result(query, missing=True)
        incomplete["status"] = "ready"
        invented = result(query, criterion="PageRank 前 10%")
        invented["evidence"]["criteria"] = query
        for response in ["bad JSON", incomplete, invented, RuntimeError("LLM unavailable")]:
            with self.subTest(response=response):
                with self.assertRaises(module.ClarificationError):
                    await self.gate.prepare(self.owner, query, self.context, self.engine(response))
                self.assertFalse(self.gate.has_pending(self.owner))

    async def test_pending_clarification_blocks_dag_confirmation(self):
        engine = self.engine(result("检测异常", missing=True))
        self.gate.record_plan(self.owner, "old-plan", self.context)
        await self.gate.prepare(self.owner, "检测异常", self.context, engine)
        with self.assertRaises(module.ClarificationError):
            self.gate.require_plan(self.owner, "old-plan")

    async def test_no_new_request_can_silently_replace_pending_intent(self):
        engine = self.engine(result("检测异常", missing=True))
        await self.gate.prepare(self.owner, "检测异常", self.context, engine)
        with self.assertRaises(module.ClarificationError):
            await self.gate.prepare(self.owner, "另外分析", self.context, engine)
        self.assertEqual(len(engine.scheduler.reasoner.calls), 1)

    def test_shared_dag_ownership_and_disconnect_are_respected(self):
        self.gate.record_plan(self.owner, "plan-a", self.context)
        self.assertEqual(self.gate.require_plan(self.owner, "plan-a"), self.context)
        with self.assertRaises(module.ClarificationError):
            self.gate.require_plan(("client-b", "conversation-a"), "plan-a")
        self.gate.clear_client("client-a")
        with self.assertRaises(module.ClarificationError):
            self.gate.require_plan(self.owner, "plan-a")


if __name__ == "__main__":
    unittest.main()
