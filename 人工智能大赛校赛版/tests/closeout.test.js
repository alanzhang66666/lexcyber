import test from "node:test";
import assert from "node:assert/strict";
import {initialState,apply} from "../data.js";
import {listTransfers} from "../risk-transfer.js";
const doAction=(s,caseId,type,rest={})=>apply(s,{caseId,type,...rest});
test("F2 handoff is idempotent and never confirms F4 facts",()=>{
 const s=initialState();doAction(s,"F2","confirm");doAction(s,"F2","run");
 const signal=s.cases[1].artifacts[0].riskSignals[0];
 doAction(s,"F2","transfer",{signalId:signal.id,note:"合成移交"});
 doAction(s,"F2","transfer",{signalId:signal.id,note:"重放"});
 assert.equal(s.transfers.length,1);
 assert.equal(s.transfers[0].legalConclusion,null);
 assert.equal(s.cases[2].draft.knowledge,false);
 assert.equal(listTransfers(s)[0].sourceStatus,"current");
});
test("F2 source change invalidates handoff without deleting history",()=>{
 const s=initialState();doAction(s,"F2","confirm");doAction(s,"F2","run");
 const signal=s.cases[1].artifacts[0].riskSignals[0];
 doAction(s,"F2","transfer",{signalId:signal.id,note:"合成线索"});
 doAction(s,"F2","edit",{field:"transaction_frequency_24h",value:2});
 doAction(s,"F2","confirm");
 assert.equal(listTransfers(s)[0].sourceStatus,"stale");
 assert.throws(()=>doAction(s,"F2","transfer",{signalId:signal.id,note:"过期"}),/失效/);
 assert.equal(s.transfers.length,1);
});
test("F4 frozen proof is not changed by later candidate verification",()=>{
 const s=initialState();
 doAction(s,"F4","evidence",{description:"合成通信材料"});
 doAction(s,"F4","candidate",{field:"knowledge",value:true,evidenceRefs:["F4-EV-1"]});
 doAction(s,"F4","verify",{candidateId:"F4-CF-1",decision:"confirmed"});
 doAction(s,"F4","confirm");doAction(s,"F4","run");
 const old=structuredClone(s.cases[2].artifacts[0].legalPaths);
 doAction(s,"F4","evidence",{description:"另一条合成记录"});
 doAction(s,"F4","candidate",{field:"help_activity",value:true,evidenceRefs:["F4-EV-2"]});
 doAction(s,"F4","verify",{candidateId:"F4-CF-2",decision:"confirmed"});
 assert.deepEqual(s.cases[2].artifacts[0].legalPaths,old);
 assert.equal(s.cases[2].versions[0].proofs.help_activity,undefined);
});
test("review and archive replay are idempotent, conflicting review fails",()=>{
 const s=initialState();doAction(s,"F2","confirm");doAction(s,"F2","run");
 doAction(s,"F2","review",{decision:"approved",comment:"同意演示结果"});
 doAction(s,"F2","review",{decision:"approved",comment:"同意演示结果"});
 assert.equal(s.cases[1].reviews.length,1);
 assert.throws(()=>doAction(s,"F2","review",{decision:"rejected",comment:"不同意见"}),/不能覆盖/);
 doAction(s,"F2","archive");doAction(s,"F2","archive");
 assert.equal(s.cases[1].archives.length,1);
});
