(function exposeCoverUploadHelpers(root){
  function imageFormatFromBytes(bytes){
    if(bytes[0]===0x89&&bytes[1]===0x50&&bytes[2]===0x4e&&bytes[3]===0x47&&bytes[4]===0x0d&&bytes[5]===0x0a&&bytes[6]===0x1a&&bytes[7]===0x0a)return {mimeType:"image/png",extension:".png"};
    if(bytes[0]===0xff&&bytes[1]===0xd8&&bytes[2]===0xff)return {mimeType:"image/jpeg",extension:".jpg"};
    return null;
  }

  function pickImageInput({allInputs,triggerInputs,previousInputs}){
    const primaryInput=triggerInputs.find(input=>!String(input.className||"").includes("replace"));
    return primaryInput||triggerInputs[0]||allInputs.find(input=>!previousInputs.has(input))||null;
  }

  root.StoryForgeCoverUpload={imageFormatFromBytes,pickImageInput};
})(globalThis);
