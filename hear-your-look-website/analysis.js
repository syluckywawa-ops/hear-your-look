'use strict';
/** Analysis boundary. AI sends re-encoded images only to our same-origin server.
 * Credentials never enter the browser. Demo never sends images.
 * image: Blob|null; options: {scenario, recheck, recheckOutcome, previousResult}.
 * The server adapter validates responses and labels mode:'ai'. Never
 * fall back to this demo without an explicit user choice. */
async function analyzeMakeup(image, options = {}) {
  if (options.mode === 'ai') {
    if (!(image instanceof Blob) || !options.consent) throw new Error('真实检查需要照片和本次发送同意。');
    if (!['normal', 'mirrored'].includes(options.orientation)) throw new Error('请先确认照片是否镜像。');
    let config;
    try {
      const response = await fetch('/api/config', { signal: options.signal });
      if (!response.ok) throw new Error();
      config = await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      throw new Error('检查服务暂时无法访问，请刷新或联系团队。本地使用时需要项目服务端，不能只双击网页文件。');
    }
    if (!config.ready) throw new Error(typeof config.message === 'string' && config.message.length <= 300 ? config.message : '服务端尚未配置模型，请联系团队；本地运行请检查密钥配置并重启。');
    const bitmap = await createImageBitmap(image);
    let encoded;
    try {
      const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale)); canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      encoded = canvas.toDataURL('image/jpeg', .9);
    } finally { bitmap.close(); }
    try {
      const response = await fetch('/api/analyze', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Local-Token': config.token },
        body: JSON.stringify({ image: encoded, consent: true, orientation: options.orientation, recheck: !!options.recheck }), signal: options.signal });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || '模型请求失败，请重试。');
      if (value.mode !== 'ai' || typeof value.model !== 'string' || value.model.length > 200) throw new Error('真实检查返回的来源无效，请重试。没有使用演示结果。');
      return validateMakeupResult(value);
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      if (error instanceof TypeError) throw new Error('连接中断，请检查网络后重试；仍失败时请联系团队。');
      throw error;
    }
  }
  if (image !== null && !(image instanceof Blob)) throw new Error('Invalid image');
  await new Promise(resolve => setTimeout(resolve, 900));
  const status = options.recheck
    ? ({ improved: 'clear', unchanged: 'unchanged', uncertain: 'uncertain' }[options.recheckOutcome] || 'unchanged')
    : ({ overflow: 'adjust', clear: 'clear', uncertain: 'uncertain' }[options.scenario] || 'adjust');
  const messages = {
    adjust: ['右侧嘴角，有一处可以调整。', '以你自己的右侧为准。用干净棉签轻轻擦去右侧嘴角唇线外的多余口红。先只处理这一处。'],
    clear: [options.recheck ? '演示复查：这处外溢已改善。' : '演示场景：未见明显外溢。', '无需继续调整。你可以结束这次体验，也可以重新准备照片。'],
    unchanged: ['演示复查：这处仍需确认。', '这个预设分支没有显示改善。不要反复擦拭；先重新准备照片，或选择结束本次体验。'],
    uncertain: ['先重新准备照片。', '这个预设场景无法判断唇线。面向均匀光源，避免背光，重新拍摄后再检查。']
  };
  return {
    mode: 'demo', status,
    quality: status === 'uncertain' ? '不可判断（预设）' : '可观察（预设）',
    smudging: status === 'uncertain' ? '无法判断' : status === 'clear' ? '未见明显外溢（预设）' : '你自己的右侧嘴角（预设）',
    title: messages[status][0], guidance: messages[status][1],
    evidence: '此结果来自预设场景，没有识别照片中的嘴唇或妆容。'
  };
}
function validateMakeupResult(value) {
  if (!value || !['demo', 'ai'].includes(value.mode) || !['adjust', 'clear', 'unchanged', 'uncertain'].includes(value.status)
    || !['title', 'guidance', 'quality', 'smudging', 'evidence'].every(key => typeof value[key] === 'string' && value[key].length <= 1200)) {
    throw new Error('分析响应无效，请重试。');
  }
  if (value.mode === 'ai') {
    const reasons = ['ok', 'occluded', 'blur', 'dark', 'incomplete', 'ambiguous'];
    const quality = value.quality_check;
    if (!reasons.includes(value.reason) || !['normal', 'mirrored'].includes(value.orientation)
      || !['left', 'right', 'center', 'unknown'].includes(value.image_side)
      || !['corner', 'upper', 'lower', 'unknown'].includes(value.region)
      || !quality || !reasons.includes(quality.reason)
      || !['left_corner_visible', 'right_corner_visible', 'upper_border_visible', 'lower_border_visible', 'sharp_enough', 'lit_enough', 'occluded'].every(key => typeof quality[key] === 'boolean')) {
      throw new Error('照片完整性结果无效，请重新检查；没有使用演示结果。');
    }
    if (value.status === 'unchanged' || value.status !== 'uncertain' && (value.reason !== 'ok' || quality.reason !== 'ok' || quality.occluded
      || !['left_corner_visible', 'right_corner_visible', 'upper_border_visible', 'lower_border_visible', 'sharp_enough', 'lit_enough'].every(key => quality[key]))) {
      throw new Error('照片完整性与判断结论冲突，请重新检查。');
    }
  }
  return value;
}
/** Local pixel heuristic only; NOT face/lip detection or validated photo quality.
 * Read a downsampled image, not a persistent copy. No data leaves the browser. */
async function assessPhotoQuality(image) {
  const canvas = document.createElement('canvas');
  canvas.width = 96; canvas.height = 96;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(image, 0, 0, 96, 96);
  const { data } = context.getImageData(0, 0, 96, 96);
  let luminance = 0;
  for (let i = 0; i < data.length; i += 4) {
    // Transparent pixels are displayed on a dark preview; treat as dark.
    luminance += (.2126 * data[i] + .7152 * data[i + 1] + .0722 * data[i + 2]) * data[i + 3] / 255;
  }
  luminance /= 96 * 96;
  const tiny = Math.min(image.naturalWidth, image.naturalHeight) < 240;
  const dark = luminance < 35, bright = luminance > 235;
  return {
    warning: tiny || dark || bright,
    message: tiny ? '照片尺寸较小，建议换一张清晰照片。'
      : dark ? '照片整体较暗，建议面向均匀光源重拍。'
      : bright ? '照片整体很亮，建议避免直射光或过曝。'
      : '未触发整体亮度或尺寸提示。',
    note: '仅本机亮度与尺寸提示；不判断是否有嘴唇、是否模糊或妆容是否正确。'
  };
}
