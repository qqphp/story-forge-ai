(function exposeCoverUploadHelpers(root) {
  function imageFormatFromBytes(bytes) {
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a) return { mimeType: 'image/png', extension: '.png' };
    if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return { mimeType: 'image/jpeg', extension: '.jpg' };
    return null;
  }

  function pickImageInput({ allInputs, triggerInputs, previousInputs }) {
    const primaryInput = triggerInputs.find((input) => !String(input.className || '').includes('replace'));
    return primaryInput || triggerInputs[0] || allInputs.find((input) => !previousInputs.has(input)) || null;
  }

  function activateBilibiliCoverRegion(region) {
    if (!region) return false;
    const target = region.querySelector?.('.upper-canvas') || region;
    const bounds = target.getBoundingClientRect?.() || {
      left: 0,
      top: 0,
      width: 0,
      height: 0
    };
    const options = {
      bubbles: true,
      cancelable: true,
      composed: true,
      button: 0,
      buttons: 1,
      clientX: bounds.left + bounds.width / 2,
      clientY: bounds.top + bounds.height / 2
    };
    const PointerEventType = root.PointerEvent || root.MouseEvent;
    if (PointerEventType)
      target.dispatchEvent(
        new PointerEventType('pointerdown', {
          ...options,
          pointerId: 1,
          pointerType: 'mouse',
          isPrimary: true
        })
      );
    target.dispatchEvent(new root.MouseEvent('mousedown', options));
    if (PointerEventType)
      target.dispatchEvent(
        new PointerEventType('pointerup', {
          ...options,
          buttons: 0,
          pointerId: 1,
          pointerType: 'mouse',
          isPrimary: true
        })
      );
    target.dispatchEvent(new root.MouseEvent('mouseup', { ...options, buttons: 0 }));
    target.dispatchEvent(new root.MouseEvent('click', { ...options, buttons: 0 }));
    return true;
  }

  root.StoryForgeCoverUpload = {
    imageFormatFromBytes,
    pickImageInput,
    activateBilibiliCoverRegion
  };
})(globalThis);
