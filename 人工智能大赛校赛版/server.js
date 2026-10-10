import http from "node:http";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
import {initStore,readState,changeState} from "./store.js";
import {explain,ruleDefs} from "./data.js";
const base=path.dirname(fileURLToPath(import.meta.url));
const port=Number(process.env.PORT||8080);
const json=(res,status,obj)=>{res.writeHead(status,{"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff"});res.end(JSON.stringify(obj))};
async function body(req){let s="";for await(const chunk of req){s+=chunk;if(s.length>20000)throw Object.assign(new Error("请求过大"),{status:413})}try{return JSON.parse(s)}catch{throw Object.assign(new Error("无效 JSON"),{status:400})}}
export function handler(req,res){
 (async()=>{
  const url=new URL(req.url,"http://localhost");const route=url.pathname;
  if(req.method==="GET"&&route==="/healthz")return json(res,200,{ok:true,storage:process.env.DATABASE_URL?"mysql":"demo-memory"});
  if(req.method==="GET"&&route==="/api/state")return json(res,200,{...(await readState()),rules:ruleDefs});
  if(req.method==="POST"&&route==="/api/action"){
   if(process.env.DEMO_WRITE_TOKEN && req.headers["x-demo-token"]!==process.env.DEMO_WRITE_TOKEN)throw Object.assign(new Error("操作需要演示授权令牌"),{status:401});
   if(!["application/json"].includes((req.headers["content-type"]||"").split(";")[0]))throw Object.assign(new Error("需要 application/json"),{status:415});
   const action=await body(req);if(!action||typeof action!=="object"||Array.isArray(action))throw Object.assign(new Error("无效动作"),{status:400});
   return json(res,200,await changeState(action));
  }
  if(req.method==="GET"&&route.startsWith("/api/cases/")){
   const parts=route.split("/");const c=(await readState()).cases.find(x=>x.id===parts[3]);if(!c)throw Object.assign(new Error("事项不存在"),{status:404});
   if(parts[4]==="risk-signals")return json(res,200,c.artifacts.at(-1)?.stale?[]:c.artifacts.at(-1)?.riskSignals??[]);
   if(parts[4]==="evidence")return json(res,200,c.evidence??[]);
   if(parts[4]==="candidate-facts")return json(res,200,c.candidates??[]);
   if(parts[4]==="legal-paths")return json(res,200,c.artifacts.at(-1)?.stale?[]:c.artifacts.at(-1)?.legalPaths??[]);
   if(parts[4]==="facts-diff"){
     const v=c.versions;if(v.length<2)return json(res,200,[]);const prev=v.at(-2).facts,next=v.at(-1).facts;
     return json(res,200,Object.keys(next).filter(k=>prev[k]!==next[k]).map(k=>({field:k,before:prev[k]??null,after:next[k]})));
   }
  }
  if(req.method==="GET"&&route==="/api/explain"){
   const s=await readState(),c=s.cases.find(x=>x.id===url.searchParams.get("caseId"));
   if(!c)throw Object.assign(new Error("事项不存在"),{status:404});
   return json(res,200,explain(c,url.searchParams.get("question")));
  }
  if(req.method==="GET"&&(route==="/"||route==="/index.html")){
   const html=await readFile(path.join(base,"public/index.html"));res.writeHead(200,{"content-type":"text/html; charset=utf-8","content-security-policy":"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'","x-content-type-options":"nosniff"});return res.end(html);
  }
  json(res,404,{error:"未找到资源"});
 })().catch(e=>json(res,e.status||500,{error:e.status?e.message:"内部服务错误"}));
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 await initStore();http.createServer(handler).listen(port,"0.0.0.0",()=>console.log("LexCyber Campus Lite listening on "+port));
}
