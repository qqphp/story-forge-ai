globalThis.StoryForgeEditorCaret={
  placeAtEnd(element){
    element.focus();
    const selection=getSelection();if(!selection)return;
    const lastTextNode=node=>{
      for(let index=node.childNodes.length-1;index>=0;index-=1){const child=node.childNodes[index];if(child.nodeType===3&&child.nodeValue)return child;const nested=child.childNodes?.length?lastTextNode(child):null;if(nested)return nested;}
      return null;
    };
    const range=document.createRange();const tail=lastTextNode(element);if(tail){range.setStart(tail,tail.nodeValue.length);range.collapse(true)}else{range.selectNodeContents(element);range.collapse(false)}selection.removeAllRanges();selection.addRange(range);
  },
  insertText(element,value){
    this.placeAtEnd(element);document.execCommand("insertText",false,value);element.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:value}));
  },
  insertTopic(element,value){
    this.insertText(element,`#${value}`);return true;
  },
};
