/* global chrome, StoryForgeCoverUpload, StoryForgeEditorCaret */
(async()=>{
  if(document.querySelector("#storyforge-publish-assistant"))return;
  const settings=await chrome.storage.local.get(["apiBase","storyForgeToken"]);
  const apiBase=(settings.apiBase||"http://127.0.0.1:8000").replace(/\/$/,"");
  const token=settings.storyForgeToken||"";
  const requestedTaskId=new URLSearchParams(location.search).get("storyforge_task")||"";
  let task=null;

  const panel=document.createElement("aside");panel.id="storyforge-publish-assistant";
  const header=document.createElement("header");const heading=document.createElement("b");heading.textContent="砚界 · 抖音发布助手";const mode=document.createElement("span");mode.textContent="本地半自动";header.append(heading,mode);
  const body=document.createElement("div");body.className="sf-body";const taskTitle=document.createElement("p");taskTitle.className="sf-task";const meta=document.createElement("p");meta.className="sf-meta";const message=document.createElement("p");message.className="sf-message";
  const actions=document.createElement("div");actions.className="sf-actions";const fillButton=document.createElement("button");fillButton.textContent="上传并填充";const completeButton=document.createElement("button");completeButton.className="secondary";completeButton.textContent="我已手动发布";completeButton.hidden=true;actions.append(fillButton,completeButton);body.append(taskTitle,meta,message,actions);panel.append(header,body);document.body.append(panel);

  function showMessage(text,error=false){message.textContent=text;message.className=`sf-message${error?" error":""}`}
  async function api(path,options={}){const response=await fetch(`${apiBase}${path}`,{...options,headers:{"Content-Type":"application/json","X-StoryForge-Token":token,...(options.headers||{})}});if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||`本地服务返回 ${response.status}`)}return response}
  async function updateStatus(status,error=""){const response=await api(`/api/publish/extension/tasks/${task.id}`,{method:"PUT",body:JSON.stringify({status,error})});task=await response.json()}
  function isUsable(element){if(!element)return false;const style=getComputedStyle(element);return !element.disabled&&style.display!=="none"&&style.visibility!=="hidden"}
  function findVideoInput(){const candidates=[...document.querySelectorAll('input[type="file"]')];return candidates.find(input=>/video|mp4/i.test(input.accept||""))||candidates[0]||null}
  function exactTextElements(text,root=document){return [...root.querySelectorAll("button,div,span,p")].filter(element=>element.id!=="storyforge-publish-assistant"&&!element.closest("#storyforge-publish-assistant")&&element.textContent?.trim()===text&&isUsable(element))}
  function clickExactText(text,root=document){const element=exactTextElements(text,root)[0];if(!element)return false;element.click();return true}
  function imageInputsNear(element,boundary){
    let container=element;
    for(let depth=0;container&&depth<7;depth+=1,container=container.parentElement){const inputs=[...container.querySelectorAll('input[type="file"]')].filter(candidate=>/image|png|jpe?g/i.test(candidate.accept||""));if(inputs.length)return inputs;if(container===boundary)break}
    return [];
  }
  function findCoverTrigger(ratio){
    const labels={"3:4":"竖封面3:4","4:3":"横封面4:3"};const labelText=labels[ratio];if(!labelText)return null;
    for(const label of exactTextElements(labelText)){
      let container=label;
      for(let depth=0;container&&depth<5;depth+=1,container=container.parentElement){
        const images=[...container.querySelectorAll("img")].filter(isUsable);if(images.length===1)return images[0];
      }
    }
    return null;
  }
  function findCoverDialog(ratio){
    const orientation=ratio==="3:4"?"竖":"横";const title=exactTextElements(`设置${orientation}封面`)[0];if(!title)return null;
    let container=title;
    for(let depth=0;container&&depth<10;depth+=1,container=container.parentElement){if(exactTextElements("上传封面",container).length&&exactTextElements("完成",container).length)return container}
    return title.closest('[role="dialog"],[class*="modal"],[class*="Modal"]')||document;
  }
  function findField(kind){
    const selectors=kind==="title"?["input[placeholder*='标题']","textarea[placeholder*='标题']","input[aria-label*='标题']"]:["textarea[placeholder*='简介']","textarea[placeholder*='描述']","textarea[aria-label*='简介']","[contenteditable='true'][data-placeholder*='简介']","[contenteditable='true'][data-placeholder*='描述']","[contenteditable='true'][aria-label*='简介']"];
    for(const selector of selectors){const element=[...document.querySelectorAll(selector)].find(isUsable);if(element)return element}
    return null;
  }
  function setFieldValue(element,value){
    element.focus();
    if(element instanceof HTMLInputElement||element instanceof HTMLTextAreaElement){const prototype=element instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;const setter=Object.getOwnPropertyDescriptor(prototype,"value")?.set;setter?.call(element,value)}else{element.textContent=value}
    element.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:value}));element.dispatchEvent(new Event("change",{bubbles:true}));element.blur();
  }
  async function waitFor(finder,timeout=60000){const started=Date.now();while(Date.now()-started<timeout){const value=finder();if(value)return value;await new Promise(resolve=>setTimeout(resolve,800))}return null}
  async function attachVideo(){
    showMessage("正在读取本机视频并等待抖音上传控件…");
    const input=await waitFor(findVideoInput,60000);if(!input)throw new Error("没有找到抖音视频上传控件，请确认当前位于作品发布页")
    const response=await fetch(`${apiBase}/api/publish/extension/tasks/${task.id}/video`,{headers:{"X-StoryForge-Token":token}});if(!response.ok)throw new Error("无法从 StoryForge 读取视频文件")
    const blob=await response.blob();const filename=decodeURIComponent(task.video_url.split("/").pop()||"storyforge-video.mp4");const file=new File([blob],filename,{type:blob.type||"video/mp4"});const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}));
  }
  async function fillTopics(descriptionField){
    const added=[];const failed=[];
    for(const rawTag of task.topics||[]){
      const tag=String(rawTag).replace(/^#+/,"").trim().replace(/\s+/g,"");if(!tag)continue;
      const existing=new Set(exactTextElements(`#${tag}`));
      if(!StoryForgeEditorCaret.insertTopic(descriptionField,tag)){failed.push(tag);continue}
      const suggestion=await waitFor(()=>exactTextElements(`#${tag}`).find(element=>!existing.has(element)&&!descriptionField.contains(element)),6000);
      if(suggestion){suggestion.click();added.push(tag);await new Promise(resolve=>setTimeout(resolve,350))}else{failed.push(tag)}
    }
    return {added,failed};
  }
  function assignFile(input,file){const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))}
  async function createSupportedImageFile(blob,sourceName){
    const bytes=new Uint8Array(await blob.slice(0,12).arrayBuffer());const format=StoryForgeCoverUpload.imageFormatFromBytes(bytes);if(!format)throw new Error("封面原文件不是抖音支持的 PNG 或 JPEG 格式")
    const stem=decodeURIComponent(sourceName).replace(/\.[^.]+$/g,"")||"storyforge-cover";return new File([blob],`${stem}${format.extension}`,{type:format.mimeType});
  }
  async function assertOriginalRatio(blob,expectedRatio){
    const [expectedWidth,expectedHeight]=expectedRatio.split(":").map(Number);const bitmap=await createImageBitmap(blob);
    try{const actual=bitmap.width/bitmap.height;const expected=expectedWidth/expectedHeight;if(Math.abs(actual-expected)>.01)throw new Error(`勾选的${expectedRatio}封面实际尺寸为${bitmap.width}×${bitmap.height}，为避免裁剪已停止上传`)}finally{bitmap.close()}
  }
  async function uploadCoverAsset(coverIndex,cover){
    showMessage(`正在将${cover.image_ratio}封面原图直传到抖音对应位置…`);
    const response=await fetch(`${apiBase}/api/publish/extension/tasks/${task.id}/covers/${coverIndex}`,{headers:{"X-StoryForge-Token":token}});if(!response.ok)throw new Error(`无法从 StoryForge 读取${cover.image_ratio}封面文件`)
    const blob=await response.blob();await assertOriginalRatio(blob,cover.image_ratio);const file=await createSupportedImageFile(blob,cover.url.split("/").pop()||"storyforge-cover.png");
    const trigger=await waitFor(()=>findCoverTrigger(cover.image_ratio),30000);if(!trigger)throw new Error(`没有找到抖音的${cover.image_ratio}封面图片区域`)
    trigger.click();const dialog=await waitFor(()=>findCoverDialog(cover.image_ratio),15000);if(!dialog)throw new Error(`已点击${cover.image_ratio}封面图片，但没有打开抖音的封面设置弹窗`)
    const uploadButton=exactTextElements("上传封面",dialog).at(-1);if(!uploadButton)throw new Error(`已打开${cover.image_ratio}封面设置弹窗，但没有找到“上传封面”按钮`)
    const previousImageInputs=new Set([...document.querySelectorAll('input[type="file"]')].filter(input=>/image|png|jpe?g/i.test(input.accept||"")));uploadButton.click();
    const input=await waitFor(()=>{const imageInputs=[...document.querySelectorAll('input[type="file"]')].filter(candidate=>/image|png|jpe?g/i.test(candidate.accept||""));const triggerInputs=imageInputsNear(uploadButton,dialog);return StoryForgeCoverUpload.pickImageInput({allInputs:imageInputs,triggerInputs,previousInputs:previousImageInputs})},10000);
    if(!input)throw new Error("已点击“上传封面”，但没有识别到抖音的图片上传控件")
    assignFile(input,file);await new Promise(resolve=>setTimeout(resolve,3000));
    let confirmButton=null;for(const label of ["完成","确定","确认","保存"]){const buttons=exactTextElements(label,dialog);confirmButton=buttons.find(element=>element.tagName==="BUTTON")||buttons[0]||null;if(confirmButton)break}
    if(!confirmButton)throw new Error(`已上传${cover.image_ratio}封面，但没有找到封面弹窗的“完成”按钮`)
    confirmButton.click();const dialogClosed=await waitFor(()=>!document.contains(dialog),15000);if(!dialogClosed)throw new Error(`${cover.image_ratio}封面设置弹窗没有关闭，已停止上传下一张封面`)
  }
  async function attachCovers(){
    const covers=Array.isArray(task.covers)?task.covers:[];if(!covers.length)return {uploaded:[],skipped:[]};
    const uploaded=[];
    const targets=[{ratio:"3:4"},{ratio:"4:3"}];
    for(let targetIndex=0;targetIndex<targets.length;targetIndex+=1){const target=targets[targetIndex];
      const coverIndex=covers.findIndex(cover=>cover.image_ratio===target.ratio);if(coverIndex<0)continue;
      await uploadCoverAsset(coverIndex,covers[coverIndex]);uploaded.push(target.ratio);
    }
    return {uploaded,skipped:covers.filter(cover=>!["3:4","4:3"].includes(cover.image_ratio)).map(cover=>cover.image_ratio||"未知比例")};
  }
  async function fillTask(){
    fillButton.disabled=true;try{
      if(task.status==="prepared"||task.status==="failed")await updateStatus("filling");
      if(!findField("title")&&!findField("description")){await attachVideo();showMessage("视频已交给抖音上传，正在等待发布信息表单…")}
      const field=await waitFor(()=>findField("title")||findField("description"),180000);if(!field)throw new Error("视频已选择，但未识别到标题或描述输入框；请手动填写并检查抖音页面")
      const titleField=findField("title");const descriptionField=findField("description");
      if(titleField)setFieldValue(titleField,task.title);if(descriptionField)setFieldValue(descriptionField,task.description);
      const topics=descriptionField?await fillTopics(descriptionField):{added:[],failed:task.topics||[]};const coverResult=await attachCovers();
      if(task.status==="filling")await updateStatus("ready");completeButton.hidden=false;
      const topicStatus=topics.failed.length?`，${topics.failed.map(tag=>`#${tag}`).join("、")} 未匹配到话题建议，请手动选择`:topics.added.length?`，已添加 ${topics.added.length} 个可识别话题`:"";
      const coverStatus=coverResult.uploaded.length?`，已上传${coverResult.uploaded.join("、")}封面`:coverResult.skipped.length?"，勾选封面没有3:4或4:3比例，未上传封面":"";
      showMessage(`已填充标题和简介${topicStatus}${coverStatus}，封面使用原图直传且未做裁剪。请检查可见范围等设置，然后亲自点击抖音的发布按钮。`,topics.failed.length>0||coverResult.skipped.length>0);
    }catch(error){const text=error instanceof Error?error.message:"填充失败";try{await updateStatus("failed",text)}catch(updateError){message.title=updateError instanceof Error?updateError.message:String(updateError)}showMessage(text,true)}finally{fillButton.disabled=false}
  }
  async function loadTask(){
    if(!token){taskTitle.textContent="尚未配对";meta.textContent="";showMessage("请打开浏览器扩展，填写发布中心提供的本地配对码。",true);fillButton.disabled=true;return}
    try{const query=new URLSearchParams({platform:"douyin"});if(requestedTaskId)query.set("task_id",requestedTaskId);const response=await api(`/api/publish/extension/tasks/next?${query}`);task=(await response.json()).task;if(!task){taskTitle.textContent="没有待发布任务";meta.textContent="";showMessage("请先在 StoryForge 发布中心准备抖音发布任务。 ");fillButton.disabled=true;return}taskTitle.textContent=task.title;meta.textContent=`《${task.book_title}》 · ${(task.topics||[]).map(topic=>`#${topic}`).join(" ")||"无话题"}`;if(task.status==="ready"){fillButton.textContent="补填封面和话题";completeButton.hidden=false;showMessage("标题和简介已填充，可以补填比例匹配的封面和可识别话题；封面将使用原图直传。") }else{showMessage("任务已就绪。点击后会选择视频、原图直传比例匹配的封面并填写可识别字段，不会自动发布。")}}catch(error){taskTitle.textContent="连接失败";meta.textContent="";showMessage(error instanceof Error?error.message:"无法连接 StoryForge",true);fillButton.disabled=true}
  }
  fillButton.addEventListener("click",()=>void fillTask());completeButton.addEventListener("click",async()=>{completeButton.disabled=true;try{await updateStatus("completed");showMessage("已记录为发布完成。你可以关闭这个提示框。 ");fillButton.hidden=true;completeButton.hidden=true}catch(error){showMessage(error instanceof Error?error.message:"状态更新失败",true);completeButton.disabled=false}});
  await loadTask();
})();
