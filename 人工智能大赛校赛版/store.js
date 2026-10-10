import {initialState,apply} from "./data.js";
let pool;let local=initialState();let queue=Promise.resolve();
export async function initStore(){
 if(!process.env.DATABASE_URL){console.warn("DEMO MEMORY MODE: 重启后操作会重置；正式比赛请配置 MySQL DATABASE_URL");return}
 const mysql=(await import("mysql2/promise")).default;
 pool=mysql.createPool({uri:process.env.DATABASE_URL,connectionLimit:4,waitForConnections:true,ssl:process.env.DB_SSL==="true"?{}:undefined});
 await pool.query("CREATE TABLE IF NOT EXISTS campus_lite_state (id INT PRIMARY KEY, body JSON NOT NULL)");
 await pool.query("INSERT IGNORE INTO campus_lite_state(id,body) VALUES (1,?)",[JSON.stringify(initialState())]);
}
export async function readState(){
 if(!pool)return structuredClone(local);
 const [rows]=await pool.query("SELECT body FROM campus_lite_state WHERE id=1");
 return typeof rows[0].body==="string"?JSON.parse(rows[0].body):rows[0].body;
}
export async function changeState(action){
 if(pool){
  const c=await pool.getConnection();
  try{await c.beginTransaction();const [rows]=await c.query("SELECT body FROM campus_lite_state WHERE id=1 FOR UPDATE");const state=typeof rows[0].body==="string"?JSON.parse(rows[0].body):rows[0].body;const next=apply(state,action);await c.query("UPDATE campus_lite_state SET body=? WHERE id=1",[JSON.stringify(next)]);await c.commit();return next}
  catch(e){await c.rollback();throw e}finally{c.release()}
 }
 const pending=queue.then(()=>{local=apply(local,action);return structuredClone(local)});
 queue=pending.then(()=>{},()=>{});return pending;
}
