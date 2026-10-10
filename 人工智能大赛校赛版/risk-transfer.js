// 校赛演示线索移交：只传递风险信息，不导出刑事事实。
const fail=(message,status=409)=>{throw Object.assign(new Error(message),{status})};
export function currentTransferStatus(state,transfer){
 const source=state.cases.find(c=>c.id===transfer.sourceCaseId);
 const a=source?.artifacts.find(a=>a.id===transfer.sourceArtifactId);
 if(!source||!a||a.stale||source.versions.at(-1)?.id!==transfer.sourceFactsVersionId)return "stale";
 return "current";
}
export function transferRisk(state,action,at){
 if(action.caseId!=="F2")fail("只能移交 F2 风控线索",400);
 const source=state.cases.find(c=>c.id==="F2"),target=state.cases.find(c=>c.id==="F4");
 const a=source?.artifacts.at(-1);
 if(!a||a.stale||source.versions.at(-1)?.id!==a.factsVersionId)fail("来源未运行或已失效");
 const signal=a.riskSignals.find(x=>x.id===action.signalId);
 if(!signal)fail("线索不存在或已失效",404);
 if(typeof action.note!=="string"||action.note.length>500)fail("移交备注无效",400);
 state.transfers??=[];
 const found=state.transfers.find(t=>t.sourceSignalId===signal.id&&t.sourceArtifactId===a.id&&t.targetCaseId==="F4");
 if(found)return found;
 const record={id:"RT-"+(state.transfers.length+1),sourceCaseId:"F2",targetCaseId:"F4",
  sourceSignalId:signal.id,sourceArtifactId:a.id,sourceFactsVersionId:a.factsVersionId,
  sourceRuleId:signal.ruleId,sourceRuleVersion:signal.ruleVersion,
  frozenTrace:structuredClone(signal.trace),label:signal.label,
  reviewStatus:"pending_verification",note:action.note,createdAt:at,legalConclusion:null};
 state.transfers.push(record);
 target.events.push({at,type:"risk.transfer.received",transferId:record.id});
 return record;
}
export function listTransfers(state){
 return (state.transfers??[]).map(t=>({...t,sourceStatus:currentTransferStatus(state,t)}));
}
