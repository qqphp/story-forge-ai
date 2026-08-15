/* global chrome */
const apiBaseInput=document.querySelector("#apiBase");
const tokenInput=document.querySelector("#token");
const statusNode=document.querySelector("#status");
const taskNode=document.querySelector("#task");
const taskTitle=document.querySelector("#taskTitle");
const taskBook=document.querySelector("#taskBook");

function normalizeBase(value){return value.trim().replace(/\/$/,"")||"http://127.0.0.1:8000"}
function setStatus(message,type=""){statusNode.textContent=message;statusNode.className=`status ${type}`.trim()}

async function checkConnection(){
  const apiBase=normalizeBase(apiBaseInput.value);const token=tokenInput.value.trim();
  if(!token){setStatus("请填写发布中心显示的配对码","error");return}
  setStatus("正在连接本地服务…");
  try{
    const response=await fetch(`${apiBase}/api/publish/extension/tasks/next?platform=douyin`,{headers:{"X-StoryForge-Token":token}});
    if(!response.ok)throw new Error(response.status===401?"配对码无效":"本地服务不可用");
    await chrome.storage.local.set({apiBase,storyForgeToken:token});
    const data=await response.json();setStatus("已连接 StoryForge","ok");
    if(data.task){taskNode.hidden=false;taskTitle.textContent=data.task.title;taskBook.textContent=`《${data.task.book_title}》 · ${data.task.status}`}else{taskNode.hidden=true}
  }catch(error){taskNode.hidden=true;setStatus(error instanceof Error?error.message:"连接失败","error")}
}

document.querySelector("#save").addEventListener("click",checkConnection);
document.querySelector("#open").addEventListener("click",async()=>{
  const {apiBase,storyForgeToken}=await chrome.storage.local.get(["apiBase","storyForgeToken"]);
  if(!storyForgeToken){setStatus("请先保存并检测连接","error");return}
  try{
    const response=await fetch(`${normalizeBase(apiBase)}/api/publish/extension/tasks/next?platform=douyin`,{headers:{"X-StoryForge-Token":storyForgeToken}});const data=await response.json();
    const suffix=data.task?`?storyforge_task=${encodeURIComponent(data.task.id)}`:"";
    await chrome.tabs.create({url:`https://creator.douyin.com/creator-micro/content/upload${suffix}`});
  }catch{setStatus("无法读取待发布任务","error")}
});

chrome.storage.local.get(["apiBase","storyForgeToken"]).then(values=>{apiBaseInput.value=values.apiBase||"http://127.0.0.1:8000";tokenInput.value=values.storyForgeToken||"";if(values.storyForgeToken)void checkConnection()});
