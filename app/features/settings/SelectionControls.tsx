"use client";

import { useState } from "react";

export function SearchableVoiceSelect({voices,value,onChange}:{voices:string[];value:string;onChange:(voice:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const filtered=voices.filter(voice=>voice.toLowerCase().includes(query.trim().toLowerCase())).slice(0,40);
  return <div className="voice-select"><button type="button" className="voice-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><span><small>当前音色</small><b>{value||"请选择默认音色"}</b></span><i>{open?"▴":"▾"}</i></button>{open&&<div className="voice-dropdown"><label className="voice-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="voice-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="输入名称模糊搜索，如 Xiaoxiao"/></label><div id="voice-options" role="listbox" className="voice-options">{filtered.map(voice=><button type="button" role="option" aria-selected={voice===value} className={voice===value?"selected":""} key={voice} onClick={()=>{onChange(voice);setOpen(false);setQuery("")}}><span>{voice===value?"✓":"声"}</span><b>{voice}</b></button>)}{!filtered.length&&<p>没有匹配的音色</p>}</div><small className="voice-result">显示 {filtered.length} / {voices.length} 个音色</small></div>}</div>;
}

export function VoiceControl({label,voices,value,onChange}:{label:string;voices:string[];value:string;onChange:(voice:string)=>void}) {
  return <div className="voice-control"><span>{label}</span><SearchableVoiceSelect voices={voices} value={value} onChange={onChange}/></div>;
}

export function ModelSelect({models,value,onChange}:{models:string[];value:string;onChange:(model:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const choices=models.filter(model=>model!=="gpt-image-2"&&model.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="model-select"><button type="button" className="model-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><b>{value||"请选择文案模型"}</b><i>{open?"▴":"▾"}</i></button>{open&&<div className="model-dropdown"><div className="model-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="model-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索模型名称"/></div><div id="model-options" role="listbox" className="model-options">{choices.map(model=><button type="button" role="option" aria-selected={model===value} className={model===value?"selected":""} key={model} onClick={()=>{onChange(model);setOpen(false);setQuery("")}}><span>{model===value?"✓":""}</span><b>{model}</b></button>)}{!choices.length&&<p>没有匹配的模型</p>}</div><small className="model-result">显示 {choices.length} / {models.filter(model=>model!=="gpt-image-2").length} 个模型</small></div>}</div>;
}

export function FormatSelect({formats,value,onChange}:{formats:string[];value:string;onChange:(format:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const choices=formats.filter(format=>format.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="model-select format-select"><button type="button" className="model-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><b>{value}</b><i>{open?"▴":"▾"}</i></button>{open&&<div className="model-dropdown"><div className="model-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="format-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索音频格式"/></div><div id="format-options" role="listbox" className="model-options">{choices.map(format=><button type="button" role="option" aria-selected={format===value} className={format===value?"selected":""} key={format} onClick={()=>{onChange(format);setOpen(false);setQuery("")}}><span>{format===value?"✓":""}</span><b>{format}</b></button>)}{!choices.length&&<p>没有匹配的音频格式</p>}</div><small className="model-result">显示 {choices.length} / {formats.length} 个格式</small></div>}</div>;
}

export function SpeechRateControl({value,onChange}:{value:number;onChange:(rate:number)=>void}) {
  const label=value===0?"正常":`${value>0?"+":""}${value}%`;
  return <label className="rate-control"><span>语速 <b>{label}</b></span><input type="range" min="-50" max="100" step="5" value={value} onChange={e=>onChange(Number(e.target.value))}/><small aria-hidden="true" style={{display:"block",position:"relative",height:14}}><span style={{position:"absolute",left:0,whiteSpace:"nowrap"}}>慢 -50%</span><span style={{position:"absolute",left:"33.333%",transform:"translateX(-50%)",whiteSpace:"nowrap"}}>正常</span><span style={{position:"absolute",right:0,whiteSpace:"nowrap"}}>快 +100%</span></small></label>;
}
