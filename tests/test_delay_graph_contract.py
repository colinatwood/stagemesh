import sys
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from runtime import StageMeshRuntime
from plugin_latency import latency_compensation_plan

class DelayGraphContractTests(unittest.TestCase):
    def runtime(self):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime)
        runtime._mutation_lock=RLock()
        runtime._has_authority=Mock(return_value=True)
        runtime.state=Mock()
        runtime.state.snapshot.return_value={"transport":{"seconds":0.25}}
        runtime.native=Mock(available=True)
        runtime.native.plugin_delay_graph_status.return_value={"activeGeneration":"2","preparedGeneration":"0","prepared":"0","paths":"2","processedFrames":"256","transactionConnected":"1","audioGraphConnected":"1","pathBinding":"output-slot-index"}
        return runtime

    def test_status_is_typed_and_does_not_claim_live_execution(self):
        status=self.runtime().plugin_delay_graph_status()
        self.assertEqual(status["activeGeneration"],2)
        self.assertIs(status["prepared"],False)
        self.assertIs(status["audioGraphConnected"],True)
        self.assertIs(status["transactionConnected"],True)
        self.assertIs(status["liveAlignmentVerified"],True)
        self.assertEqual(status["pathBinding"],"output-slot-index")

    def test_authority_denial_precedes_native_calls(self):
        runtime=self.runtime();runtime._has_authority.return_value=False
        with self.assertRaises(RuntimeError):runtime.plugin_delay_graph_control({"action":"activate"})
        runtime.native.plugin_delay_graph_activate.assert_not_called()

    def test_activation_ignores_fabricated_client_time(self):
        runtime=self.runtime()
        runtime.plugin_delay_graph_control({"action":"activate","showNs":999999999999})
        runtime.native.plugin_delay_graph_activate.assert_called_once_with(250000000)

    def test_pending_generation_cannot_be_overwritten(self):
        runtime=self.runtime();runtime.native.plugin_delay_graph_status.return_value["preparedGeneration"]="3"
        with self.assertRaises(RuntimeError):runtime.plugin_delay_graph_control({"action":"prepare","paths":[{"pathId":"dry","latencyFrames":0}]})
        runtime.native.plugin_delay_graph_prepare.assert_not_called()

    def test_native_capacity_rejected_before_prepare(self):
        runtime=self.runtime()
        with self.assertRaises(ValueError):runtime.plugin_delay_graph_control({"action":"prepare","paths":[{"pathId":str(i)} for i in range(17)]})
        runtime.native.plugin_delay_graph_prepare.assert_not_called()

    def test_output_slot_binding_is_sorted_and_must_be_contiguous(self):
        runtime=self.runtime();runtime.plugin_delay_graph_control({"action":"prepare","paths":[{"pathId":"monitor","latencyFrames":7,"outputSlot":1},{"pathId":"foh","latencyFrames":2,"outputSlot":0}]})
        self.assertEqual(runtime.native.plugin_delay_graph_prepare.call_args.args[2],[2,7])
        with self.assertRaisesRegex(ValueError,"contiguous"):
            self.runtime().plugin_delay_graph_control({"action":"prepare","paths":[{"pathId":"monitor","latencyFrames":7,"outputSlot":1}]})

    def test_ambiguous_path_data_rejected(self):
        for paths in ([{"pathId":"x"},{"pathId":"x"}],[{"pathId":" "}],[{"pathId":"x","latencyFrames":1.5}],[{"pathId":"x","latencyFrames":True}]):
            with self.subTest(paths=paths),self.assertRaises(ValueError):latency_compensation_plan(paths)

    def test_atomic_transaction_requires_safe_classification(self):
        runtime=self.runtime();paths=[{"pathId":"foh","latencyFrames":3,"outputSlot":0}]
        change={"effectId":7,"outputSlot":0,"bypassed":True,"safetyClass":"optional","bypassMode":"latency-preserving"}
        runtime.plugin_delay_graph_control({"action":"prepareTransaction","activationShowNs":100,"paths":paths,"changes":[change]})
        runtime.native.effect_delay_transaction_prepare.assert_called_once_with(3,100,[3],[{"effectId":7,"outputSlot":0,"bypassed":True}])
        unsafe={**change,"safetyClass":"essential"}
        with self.assertRaisesRegex(ValueError,"optional latency-preserving"):
            self.runtime().plugin_delay_graph_control({"action":"prepareTransaction","paths":paths,"changes":[unsafe]})

    def test_rollback_is_a_new_generation(self):
        runtime=self.runtime();runtime.plugin_delay_graph_control({"action":"rollback","activationShowNs":500})
        runtime.native.effect_delay_transaction_rollback.assert_called_once_with(3,500)

    def test_operator_confirmed_overload_plan_prepares_but_does_not_activate(self):
        runtime=self.runtime();effect={"effectId":7,"outputSlot":0,"safetyClass":"optional","bypassMode":"latency-preserving","shedPriority":10,"latencyFrames":12,"bypassLatencyFrames":12}
        result=runtime.overload_transaction_prepare({"outputs":[{"overloadLevel":1}],"effects":[effect],"paths":[{"pathId":"foh","outputSlot":0,"latencyFrames":12}],"reviewedAction":"shed","reviewedEffectIds":[7],"acknowledgeReviewedPlan":True,"activationShowNs":900})
        self.assertTrue(result["operatorConfirmed"]);self.assertTrue(result["activationRequired"]);self.assertFalse(result["physicalOutputsArmed"])
        runtime.native.effect_delay_transaction_prepare.assert_called_once_with(3,900,[12],[{"effectId":7,"outputSlot":0,"bypassed":True}])
        runtime.native.plugin_delay_graph_activate.assert_not_called()

    def test_overload_prepare_rejects_stale_review_and_latency_change(self):
        base={"outputs":[{"overloadLevel":1}],"effects":[{"effectId":7,"outputSlot":0,"safetyClass":"optional","bypassMode":"latency-preserving","shedPriority":10,"latencyFrames":12,"bypassLatencyFrames":12}],"paths":[{"pathId":"foh","outputSlot":0,"latencyFrames":12}],"reviewedAction":"shed","reviewedEffectIds":[7],"acknowledgeReviewedPlan":True}
        with self.assertRaisesRegex(RuntimeError,"no longer matches"):
            self.runtime().overload_transaction_prepare({**base,"reviewedEffectIds":[8]})
        unsafe={**base,"effects":[{**base["effects"][0],"bypassLatencyFrames":0}]}
        with self.assertRaisesRegex(ValueError,"exact active latency"):
            self.runtime().overload_transaction_prepare(unsafe)

    def test_overload_prepare_authority_denial_precedes_planning_and_native_calls(self):
        runtime=self.runtime();runtime._has_authority.return_value=False
        with self.assertRaisesRegex(RuntimeError,"primary authority"):
            runtime.overload_transaction_prepare({"acknowledgeReviewedPlan":True})
        runtime.native.effect_delay_transaction_prepare.assert_not_called()
