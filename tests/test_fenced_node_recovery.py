import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from witness import WitnessLeaseStore,WitnessQuorumClient,WitnessResult,sign_request,verify_recovery_request
from runtime import StageMeshRuntime

def marker(path:Path)->dict:
 value={"documentType":"org.upp.handoff-acquisition-fence","protocolVersion":1,"clusterId":"show","sourceNodeId":"old","targetNodeId":"new","sourceEpoch":1,"targetEpoch":2,"transactionId":12,"ttlMs":3000}
 path.write_text(json.dumps(value,sort_keys=True,separators=(",",":")));return value

class FencedNodeRecoveryTests(unittest.TestCase):
 def test_recovery_request_is_typed_authenticated_and_node_bound(self):
  payload={"protocolVersion":1,"clusterId":"show","nodeId":"old","sourceNodeId":"old","targetNodeId":"new","sourceEpoch":1,"targetEpoch":2,"transactionId":12,"recoveryId":"repair-1","fenceDigest":"a"*64,"nonce":"n"};request={**payload,"hmacSha256":sign_request(payload,b"key")}
  self.assertTrue(verify_recovery_request(request,b"key")[0])
  self.assertFalse(verify_recovery_request({**request,"nodeId":"other"},b"key")[0])
  self.assertFalse(verify_recovery_request({**request,"transactionId":True},b"key")[0])
 def test_witness_authorizes_only_exact_current_transfer(self):
  store=WitnessLeaseStore();lease=store.acquire("show","old",3000);epoch=lease["epoch"];store.transfer("show","old","new",epoch,epoch+1,12,3000)
  accepted=store.authorize_recovery("show","old","new",epoch,epoch+1,12,"r","a"*64);self.assertTrue(accepted["authorized"])
  self.assertFalse(store.authorize_recovery("show","old","new",epoch,epoch+1,13,"r","a"*64)["authorized"])
 def test_quorum_recovery_persists_receipt_before_removing_fence(self):
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"fence.json";marker(path);client=WitnessQuorumClient(["http://a","http://b","http://c"],"show","old",b"key",fence_path=path)
   def grant(url,payload):
    self.assertEqual(payload["fenceDigest"],hashlib.sha256(path.read_bytes()).hexdigest());return WitnessResult(url,True,2,0,"old")
   with patch.object(client,"_recover_one",side_effect=grant):result=client.recover("repair-1")
   self.assertTrue(result["recovered"]);self.assertFalse(path.exists());receipt=Path(str(path)+".recovery.json");self.assertEqual(json.loads(receipt.read_text())["recoveryId"],"repair-1");self.assertFalse(client.status()["acquisitionSuspended"]);self.assertFalse(client.status()["leaseValid"])
 def test_failed_quorum_keeps_fence_and_suspension(self):
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"fence.json";marker(path);client=WitnessQuorumClient(["http://a","http://b","http://c"],"show","old",b"key",fence_path=path)
   with patch.object(client,"_recover_one",return_value=WitnessResult("x",False,error="denied")):result=client.recover("repair-1")
   self.assertFalse(result["recovered"]);self.assertTrue(path.exists());self.assertTrue(client.status()["acquisitionSuspended"])
 def test_fence_path_swap_after_authorization_is_not_removed(self):
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"fence.json";value=marker(path);client=WitnessQuorumClient(["http://a"],"show","old",b"key",fence_path=path)
   def swap(url,payload):path.unlink();path.write_text(json.dumps(value));return WitnessResult(url,True,2,0,"old")
   with patch.object(client,"_recover_one",side_effect=swap),self.assertRaisesRegex(RuntimeError,"changed before removal"):client.recover("repair-1")
   self.assertTrue(path.exists());self.assertTrue(client.status()["acquisitionSuspended"])
 def test_runtime_recovery_always_fences_and_remains_standby(self):
  class Replication:
   role="primary"
   def set_role(self,role):self.role=role
  runtime=StageMeshRuntime.__new__(StageMeshRuntime);runtime._mutation_lock=RLock();runtime._fence_physical_outputs=Mock();runtime.replication=Replication();runtime._witness=Mock();runtime._witness.recover.return_value={"recovered":True,"recoveryId":"r","grants":2,"quorum":2,"acquisitionSuspended":False}
  result=runtime.recover_fenced_node({"acknowledgeStandbyRecovery":True,"recoveryId":"r"});runtime._fence_physical_outputs.assert_called_once();self.assertEqual(result["nodeRole"],"standby");self.assertFalse(result["physicalAuthority"]);self.assertFalse(result["physicalOutputsArmed"])
 def test_production_witness_handler_authorizes_exact_recovery(self):
  from http.server import ThreadingHTTPServer
  from threading import Thread
  import witness_server
  with tempfile.TemporaryDirectory() as raw,patch.object(witness_server,"SECRET",b"key"),patch.object(witness_server,"STORE",WitnessLeaseStore()):
   server=ThreadingHTTPServer(("127.0.0.1",0),witness_server.Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    path=Path(raw)/"fence.json";client=WitnessQuorumClient([f"http://127.0.0.1:{server.server_port}"],"show","old",b"key",fence_path=path);lease=client.acquire();epoch=lease["leaseEpoch"]
    self.assertTrue(client.transfer(target_node_id="new",source_epoch=epoch,target_epoch=epoch+1,transaction_id=33)["transferred"])
    recovered=client.recover("operator-rejoin-1");self.assertTrue(recovered["recovered"]);self.assertFalse(path.exists())
   finally:server.shutdown();thread.join(timeout=2);server.server_close()

if __name__=="__main__":unittest.main()
