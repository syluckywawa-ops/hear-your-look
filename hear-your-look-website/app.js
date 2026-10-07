'use strict';
const $ = selector => document.querySelector(selector);
let phase = 0, scenario = 'overflow', paused = false, stream = null;
let selectedImage = null, photoURL = null, busy = false, result = null;
let runVersion = 0, photoVersion = 0, cameraVersion = 0, speechVersion = 0;
let cameraPending = false, capturing = false, countdownTimer = null;
let withoutPhoto = false, previousResult = null;
let startedAt = null, repeats = 0, exportURL = null;
let mode = 'demo', requestController = null, analysisError = '';
const history = [], events = [];
const testRecords = [];

function record(type) {
  events.push({ type, elapsedSeconds: startedAt === null ? 0 : Math.round((performance.now() - startedAt) / 1000) });
}
function content() {
  if (mode === 'ai') {
    if (phase === 0) return ['准备开始', '先做一次口红检查。', '真实检查会在你逐张同意后发送照片给外部模型。判断可能出错；照片方向或唇线不确定时请重拍。', '准备照片', '真实模式 · 能力未经验证'];
    if (phase === 1 || phase === 4) return [phase === 1 ? '照片准备' : '重新准备', phase === 1 ? '准备一张照片。' : '调整后，再准备一张照片。', selectedImage ? '确认照片方向，并同意发送本次照片后继续。复查仅观察新照片，不比较前后效果。' : '请拍摄或上传照片。真实检查必须使用照片。', phase === 1 ? '发送照片并检查' : '发送新照片复查', !selectedImage ? '等待照片' : $('#photo-orientation').value === 'unknown' ? '请确认照片方向' : !$('#send-consent').checked ? '等待本次发送同意' : '准备发送 · 模型可能出错'];
    if (phase === 2 || phase === 5) return [phase === 5 ? '模型复查' : '模型观察', result.title, result.guidance, result.status === 'uncertain' ? '重新准备照片' : result.status === 'clear' ? '结束本次体验' : phase === 5 ? '重新准备照片' : '听取一步指引', '真实模型 · 未经验证' + (phase === 5 ? ' · 未比较前后效果' : '')];
    if (phase === 3) return ['一个动作', result.title, result.guidance, '已调整，准备复查', '以你自己的左右为准；不确定时停止调整'];
    return ['体验结束', '按你的节奏，结束这次体验。', '本机照片和摄像头已释放。此前已发送的照片不能撤回；外部服务处理受其政策约束。结果不能作为准确率证明。', '再体验一次', '体验已结束'];
  }
  if (phase === 0) return ['准备开始', '先做一次口红检查。', '先固定手机并准备照片。这是演示原型：照片不会上传，口红判断仍来自预设场景。', '准备照片', '演示原型，未接入真实 AI'];
  if (phase === 1 || phase === 4) return [phase === 1 ? '照片准备' : '重新准备', phase === 1 ? '准备一张照片。' : '调整后，再准备一张照片。', selectedImage ? '照片已准备好。可运行预设流程；结果不来自这张照片。' : '拍摄或上传照片后再继续。也可以明确选择下方的无照片演示。', phase === 1 ? '运行预设检查' : '运行预设复查', withoutPhoto ? '已选择无照片演示' : selectedImage ? '照片仅在本机，妆容结果为预设' : '等待照片或无照片演示选择'];
  if (phase === 2) return ['预设结果', result.title, result.status === 'adjust' ? '下面可以听取一条调整指引。你也可以暂不调整，直接结束体验。' : result.guidance, result.status === 'uncertain' ? '重新准备照片' : result.status === 'clear' ? '完成本次演示' : '听取一步指引', '预设结果，没有识别照片'];
  if (phase === 3) return ['一个动作', '先只处理右侧嘴角。', result.guidance, '已调整，准备复查', '以你自己的左右为准，可随时结束'];
  if (phase === 5) return ['预设复查', result.title, result.guidance, result.status === 'clear' ? '完成本次演示' : '重新准备照片', '预设复查，不代表实际改善'];
  return ['体验结束', '按你的节奏，完成这次体验。', '你可以导出本次流程记录，或重新开始。演示中的结论不能作为照片分析效果或准确率证明。', '再体验一次', '体验已结束，摄像头和照片已释放'];
}
function stopSpeech() {
  speechVersion++;
  document.body.classList.remove('speaking');
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}
function speakText(text) {
  stopSpeech();
  if (paused) return;
  if (!$('#voice').checked) { $('#voice-status').textContent = '自动语音已关闭，请使用文字或屏幕阅读器。'; return; }
  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) { $('#voice-status').textContent = '浏览器不支持语音，请使用完整文字指引。'; return; }
  const version = speechVersion, utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'zh-CN'; utterance.rate = Number($('#speed').value);
  utterance.onstart = () => { if (version !== speechVersion) return; document.body.classList.add('speaking'); $('#voice-status').textContent = '正在朗读…'; };
  utterance.onend = () => { if (version !== speechVersion) return; document.body.classList.remove('speaking'); $('#voice-status').textContent = '朗读结束，可以重听。'; };
  utterance.onerror = () => { if (version !== speechVersion) return; document.body.classList.remove('speaking'); $('#voice-status').textContent = '语音未能播出，请使用文字或重听。'; };
  try { window.speechSynthesis.speak(utterance); } catch { utterance.onerror(); }
}
function speak() { const c = content(); speakText((mode === 'ai' ? '实验性模型检查。' : '演示原型。') + (analysisError || c[1] + ' ' + c[2])); }
function focusHeading() { $('#instruction-title').tabIndex = -1; $('#instruction-title').focus(); }
function render(announce = false, focus = false) {
  const c = content(), preparing = phase === 1 || phase === 4, canPrepare = [0, 1, 4].includes(phase);
  $('#step-label').textContent = c[0];
  $('#instruction-title').textContent = busy ? (mode === 'ai' ? '模型正在检查照片…' : '正在运行预设流程…') : paused ? '体验已暂停。' : c[1];
  $('#instruction-body').textContent = busy ? (mode === 'ai' ? '照片已开始发送。可结束等待；已发送的照片无法撤回。结果可能出错。' : '这里模拟等待时间，没有识别照片中的妆容。') : paused ? '继续时回到当前步骤。摄像头已关闭，照片仍可保留供你继续准备。' : c[2];
  $('#next').textContent = busy ? '处理中…' : c[3];
  $('#next').disabled = busy || paused || capturing || (preparing && (!selectedImage && !withoutPhoto || mode === 'ai' && (!selectedImage || !$('#send-consent').checked || $('#photo-orientation').value === 'unknown')));
  $('#repeat').disabled = busy;
  $('#pause').disabled = busy || phase === 6;
  $('#pause').textContent = paused ? '继续体验' : '暂停体验';
  $('#pause').setAttribute('aria-pressed', String(paused));
  $('#result-label').textContent = busy ? (mode === 'ai' ? '真实模型' : '演示模式') + ' · 处理中' : c[4];
  $('#source-note').textContent = mode === 'ai' ? (result ? '口红结果来源：OpenRouter / ' + result.model + '。判断可能出错，未经验证。' : '真实检查尚无结果；本机亮度提示不等于妆容识别。') : '口红结果来源：预设演示。' + (selectedImage ? '这张照片未进行妆容识别。' : withoutPhoto ? '本次未使用照片。' : '尚未分析照片。');
  $('#analysis-error').hidden = !analysisError; $('#analysis-error').textContent = analysisError;
  $('#analysis-badge').textContent = mode === 'ai' ? '真实模型 · 实验性' : '预设场景';
  $('#ai-settings').hidden = mode !== 'ai';
  $('#analysis-mode').disabled = ![0, 6].includes(phase) || busy || capturing;
  $('#photo-orientation').disabled = busy || !canPrepare;
  $('#send-consent').disabled = busy || !canPrepare || !selectedImage;
  $('#live').setAttribute('aria-busy', String(busy));
  $('#no-photo').hidden = mode === 'ai' || !preparing || withoutPhoto || !!selectedImage || busy || paused;
  $('#retake').hidden = ![2, 3, 5].includes(phase) || busy || paused || ([2, 5].includes(phase) && result?.status !== 'adjust' && result?.status !== 'clear');
  $('#finish').hidden = phase === 0 || phase === 6;
  $('#finish').textContent = [2, 3].includes(phase) ? '暂不调整，结束体验' : '结束本次体验';
  const stage = phase <= 1 ? 0 : phase === 2 ? 1 : phase === 3 ? 2 : 3;
  document.body.classList.toggle('paused', paused);
  document.body.classList.toggle('processing', busy);
  document.body.dataset.stage = String(stage);
  document.querySelectorAll('[data-stage]').forEach(el => { el.removeAttribute('aria-current'); if (+el.dataset.stage === stage) el.setAttribute('aria-current', 'step'); });
  $('#result-disclosure').hidden = !(result && [2, 3, 5].includes(phase) && !busy);
  $('#result-details').replaceChildren();
  if (result) {
    for (const [label, value] of [['可判断性', result.quality], ['唇线外溢', result.smudging]]) {
      const div = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = value; div.append(dt, dd); $('#result-details').append(div);
    }
    $('#result-evidence').textContent = result.evidence;
  }
  $('#history').replaceChildren();
  (history.length ? history : ['等待开始。尚无本次流程记录。']).forEach(text => { const li = document.createElement('li'); li.textContent = text; $('#history').append(li); });
  $('#export-session').disabled = events.length === 0;
  $('#capture').disabled = !stream || capturing || paused || busy || !canPrepare;
  $('#photo').disabled = busy || capturing || !canPrepare;
  $('#remove-photo').disabled = busy || !canPrepare;
  $('#camera-button').disabled = cameraPending || capturing || busy || paused || !canPrepare;
  if (focus) focusHeading();
  if (announce) speak();
}
function prepareAgain() {
  previousResult = result;
  result = null; phase = 4; withoutPhoto = false;
  removePhoto(); closeCamera(); record('prepare_recheck'); history.push('重新准备照片；上次照片已释放。'); render(true, true);
}
function finish() {
  requestController?.abort(); analysisError = ''; previousResult = null;
  runVersion++; photoVersion++; busy = false; paused = false;
  closeCamera(); removePhoto(); phase = 6; result = null; withoutPhoto = false;
  record('finished'); history.push('用户结束体验；摄像头和照片已释放。'); render(true, true);
}
async function advance() {
  if (busy || paused || capturing) return;
  if (phase === 6) return reset(true);
  if (phase === 0) { startedAt = performance.now(); record('started'); phase = 1; history.push('准备照片。'); render(true, true); return; }
  if (phase === 1 || phase === 4) {
    if (!selectedImage && !withoutPhoto) return;
    if (mode === 'ai' && (!selectedImage || !$('#send-consent').checked || $('#photo-orientation').value === 'unknown')) return;
    const recheck = phase === 4, version = ++runVersion;
    const requestedAt = new Date().toISOString(), requestStart = performance.now(), orientation = $('#photo-orientation').value;
    analysisError = ''; const controller = new AbortController(); requestController = controller;
    const timeout = setTimeout(() => controller.abort(), 65000);
    busy = true; stopSpeech(); record(mode + (recheck ? '_recheck_requested' : '_check_requested')); render();
    if (mode === 'ai') $('#photo-status').textContent = '照片已开始发送至外部模型服务。正在等待检查结果。';
    try {
      const response = validateMakeupResult(await analyzeMakeup(selectedImage, { mode, consent: $('#send-consent').checked, orientation: $('#photo-orientation').value, signal: requestController.signal, scenario, recheck, recheckOutcome: $('#recheck-outcome').value, previousResult }));
      if (version !== runVersion) return;
      result = response; phase = recheck ? 5 : 2;
      if (mode === 'ai') $('#photo-status').textContent = '本次照片已发送，模型结果已返回。重新准备时需要再次同意发送。';
      if (mode === 'ai') testRecords.push({ number: testRecords.length + 1, requestedAt, durationSeconds: Math.round((performance.now() - requestStart) / 100) / 10,
        model: response.model, orientation, recheck, status: response.status, reason: response.reason,
        imageSide: response.image_side, region: response.region, qualityCheck: response.quality_check,
        title: response.title, guidance: response.guidance, evidence: response.evidence,
        preprocessing: { longestEdgeMax: 1600, format: 'image/jpeg', quality: 0.9 }, manualNote: '' });
      $('#result-disclosure').open = false;
      history.push(response.title + (mode === 'ai' ? '（模型观察，未经验证）' : '（预设演示）')); record(mode + '_result_' + response.status);
    } catch (error) {
      if (version !== runVersion) return;
      analysisError = error.name === 'AbortError' ? '等待已超时，请重试；已发送的照片无法撤回。' : error.message;
      if (mode === 'ai') $('#photo-status').textContent = '本次检查未完成。请求已开始，照片可能已发送；请查看错误提示。';
      if (mode === 'ai') testRecords.push({ number: testRecords.length + 1, requestedAt, durationSeconds: Math.round((performance.now() - requestStart) / 100) / 10,
        orientation, recheck, status: 'error', error: analysisError, manualNote: '' });
      record('analysis_error');
    } finally { clearTimeout(timeout); if (version === runVersion) { requestController = null; busy = false; render(true, true); } }
    return;
  }
  if (phase === 2) {
    if (result.status === 'uncertain') { removePhoto(); withoutPhoto = false; result = null; phase = 1; history.push('重新准备首次检查照片。'); }
    else if (result.status === 'clear') return finish();
    else { phase = 3; record('guidance_opened'); history.push(mode === 'ai' ? result.guidance : '听取一个动作：处理你自己的右侧嘴角。'); }
  } else if (phase === 3) return prepareAgain();
  else if (phase === 5) { if (result.status === 'clear') return finish(); return prepareAgain(); }
  render(true, true);
}
function reset(announce = false) {
  requestController?.abort(); requestController = null; analysisError = '';
  runVersion++; photoVersion++; stopSpeech(); closeCamera(); removePhoto();
  phase = 0; busy = false; paused = false; result = null; previousResult = null; withoutPhoto = false;
  history.length = 0; events.length = 0; testRecords.length = 0; startedAt = null; repeats = 0;
  if (exportURL) URL.revokeObjectURL(exportURL); exportURL = null; $('#session-export').hidden = true; $('#session-json').value = ''; $('#download-session').removeAttribute('href');
  render(announce, true);
}
function removePhoto() {
  $('#send-consent').checked = false; $('#photo-orientation').value = 'unknown'; analysisError = '';
  photoVersion++;
  if (photoURL) URL.revokeObjectURL(photoURL);
  photoURL = null; selectedImage = null;
  $('#photo-preview').removeAttribute('src'); $('#photo-preview').hidden = true;
  $('#remove-photo').hidden = true; $('#photo').value = ''; $('#photo-quality').hidden = true;
  $('#camera-empty').hidden = !!stream; $('#video').style.display = stream ? 'block' : 'none';
  $('#photo-status').textContent = '尚未选择照片。';
}
async function setPhoto(blob, orientation = 'unknown') {
  const version = ++photoVersion, url = URL.createObjectURL(blob), image = new Image();
  try {
    await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error('请使用有效的 JPG、PNG 或 WebP 照片。')); image.src = url; });
    if (image.naturalWidth * image.naturalHeight > 40000000) throw new Error('照片分辨率过大，请缩小后再试。');
    const quality = await assessPhotoQuality(image);
    if (version !== photoVersion) { URL.revokeObjectURL(url); return; }
    closeCamera();
    if (photoURL) URL.revokeObjectURL(photoURL);
    photoURL = url; selectedImage = blob; withoutPhoto = false;
    $('#send-consent').checked = false; $('#photo-orientation').value = orientation; analysisError = '';
    $('#photo-preview').src = url; $('#photo-preview').hidden = false;
    $('#camera-empty').hidden = true; $('#remove-photo').hidden = false;
    $('#photo-status').textContent = mode === 'ai' ? '照片已准备好，尚未发送。请确认方向并同意本次发送。' : '照片已准备好，仅保留在当前浏览器。口红结果仍为预设。';
    $('#photo-quality').hidden = false; $('#photo-quality').classList.toggle('quality-warning', quality.warning);
    $('#quality-message').textContent = quality.message; $('#quality-note').textContent = quality.note;
    record('photo_prepared'); render();
  } catch (error) { URL.revokeObjectURL(url); if (version === photoVersion) throw error; }
}
function cancelCountdown() {
  if (countdownTimer !== null) clearTimeout(countdownTimer);
  countdownTimer = null; capturing = false; $('#capture').textContent = '3 秒后拍摄';
}
function closeCamera() {
  cameraVersion++; cameraPending = false; cancelCountdown();
  stream?.getTracks().forEach(track => track.stop()); stream = null;
  $('#video').srcObject = null; $('#video').style.display = 'none';
  $('#camera-empty').hidden = !!selectedImage;
  $('#camera-state').textContent = '摄像头已关闭'; $('#camera-button').textContent = '开启摄像头预览';
  $('#camera-button').disabled = false; $('#capture').disabled = true;
  $('#camera-message').textContent = '摄像头已关闭，可上传已有照片。';
}
$('#camera-button').addEventListener('click', async () => {
  if (stream) { closeCamera(); render(); return; }
  if (cameraPending) return;
  if (!navigator.mediaDevices?.getUserMedia) { $('#camera-message').textContent = '当前环境不支持摄像头，请上传已有照片。'; return; }
  const version = ++cameraVersion;
  cameraPending = true; render(); $('#camera-message').textContent = '等待摄像头许可；也可直接上传照片。';
  try {
    const opened = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    if (version !== cameraVersion) { opened.getTracks().forEach(track => track.stop()); return; }
    stream = opened; $('#video').srcObject = opened; await $('#video').play();
    if (version !== cameraVersion) return;
    removePhoto(); $('#camera-empty').hidden = true; $('#video').style.display = 'block';
    $('#camera-state').textContent = '本机预览，无实时定位'; $('#camera-button').textContent = '关闭摄像头';
    $('#camera-message').textContent = '手机放稳后可倒计时拍摄。预览为镜像，拍摄保留原始方向。'; record('camera_opened');
  } catch (error) {
    if (version !== cameraVersion) return;
    closeCamera(); $('#camera-message').textContent = error.name === 'NotAllowedError' ? '摄像头权限未开启，请上传照片或明确选择无照片演示。' : '摄像头未能打开，请上传照片或选择无照片演示。';
  } finally { if (version === cameraVersion) { cameraPending = false; render(); } }
});
$('#capture').addEventListener('click', () => {
  const video = $('#video');
  if (!stream || capturing || !video.videoWidth) { $('#camera-message').textContent = '画面尚未准备好，请稍后重试。'; return; }
  capturing = true; const version = cameraVersion; let seconds = 3; render();
  const tick = () => {
    if (version !== cameraVersion || !stream) return;
    if (seconds > 0) {
      $('#capture').textContent = seconds + ' 秒后拍摄'; $('#camera-message').textContent = seconds + ' 秒后拍摄，请保持手机稳定。';
      speakText(String(seconds)); seconds--; countdownTimer = setTimeout(tick, 1000); return;
    }
    countdownTimer = null;
    const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(async blob => {
      if (version !== cameraVersion) return;
      capturing = false; $('#capture').textContent = '3 秒后拍摄';
      if (!blob) { $('#camera-message').textContent = '拍摄失败，请重试或上传照片。'; render(); return; }
      try { await setPhoto(blob, 'normal'); speakText(mode === 'ai' ? '照片已准备好。请同意发送本次照片后检查。' : '照片已准备好。口红结果仍为预设演示。'); }
      catch (error) { $('#photo-status').textContent = error.message; render(); }
    }, 'image/jpeg', .9);
  };
  tick();
});
$('#photo').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
    $('#photo-status').textContent = '请选择不超过 10 MB 的 JPG、PNG 或 WebP 照片。'; event.target.value = ''; return;
  }
  try { await setPhoto(file); }
  catch (error) { $('#photo-status').textContent = '照片无法读取：' + error.message; event.target.value = ''; }
});
$('#remove-photo').addEventListener('click', () => { removePhoto(); withoutPhoto = false; record('photo_removed'); render(); $('#photo').focus(); });
$('#framing-guide').addEventListener('click', () => { speakText($('#framing-text').textContent); record('framing_guide'); });
$('#next').addEventListener('click', advance);
$('#analysis-mode').addEventListener('change', () => { mode = $('#analysis-mode').value; reset(true); });
$('#send-consent').addEventListener('change', () => render());
$('#photo-orientation').addEventListener('change', () => render());
$('#no-photo').addEventListener('click', () => { withoutPhoto = true; closeCamera(); removePhoto(); record('explicit_no_photo_demo'); render(true, true); });
$('#finish').addEventListener('click', finish);
$('#retake').addEventListener('click', () => { if (phase === 5 || phase === 3) prepareAgain(); else { result = null; phase = 1; withoutPhoto = false; removePhoto(); closeCamera(); record('retake_first'); render(true, true); } });
$('#repeat').addEventListener('click', () => { repeats++; record('repeat_guidance'); speak(); });
$('#restart').addEventListener('click', () => reset(true));
$('#clear-session').addEventListener('click', () => { reset(false); $('#voice-status').textContent = '记录与照片已清除，摄像头已关闭。'; });
$('#pause').addEventListener('click', () => { paused = !paused; stopSpeech(); if (paused) closeCamera(); record(paused ? 'paused' : 'resumed'); render(!paused, true); });
$('#voice').addEventListener('change', () => { savePreferences(); if ($('#voice').checked) speak(); else { stopSpeech(); $('#voice-status').textContent = '自动语音已关闭，请使用文字或屏幕阅读器。'; } });
$('#large').addEventListener('click', () => { const active = document.documentElement.classList.toggle('large'); $('#large').setAttribute('aria-pressed', String(active)); $('#large').textContent = active ? '标准字号' : '大字模式'; savePreferences(); });
document.querySelectorAll('[name=scenario]').forEach(el => el.addEventListener('change', () => { scenario = el.value; if (mode === 'demo') reset(false); }));
$('#recheck-outcome').addEventListener('change', () => { $('#voice-status').textContent = mode === 'ai' ? '真实模式不使用预设复查设置。' : '下一次复查将使用所选预设分支。'; });
$('#export-session').addEventListener('click', () => {
  const data = { schemaVersion: 2, mode, note: '用户主动导出的流程与测试记录，不含照片或密钥；不是用户研究或准确率证据。manualNote 可在导出文件中补充人工观察。', elapsedSeconds: phase === 6 ? (events.at(-1)?.elapsedSeconds || 0) : startedAt === null ? 0 : Math.round((performance.now() - startedAt) / 1000), repeatCount: repeats, events, checks: testRecords };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  if (exportURL) URL.revokeObjectURL(exportURL);
  exportURL = URL.createObjectURL(blob); $('#download-session').href = exportURL;
  $('#download-session').download = mode === 'ai' ? 'hear-your-look-test-session.json' : 'hear-your-look-demo-session.json';
  $('#session-json').value = JSON.stringify(data, null, 2); $('#session-export').hidden = false;
  $('#export-status').textContent = '可保存文件；若浏览器不支持下载，也可复制上方文本。'; $('#session-json').focus();
});
$('#copy-session').addEventListener('click', async () => {
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Unavailable');
    await navigator.clipboard.writeText($('#session-json').value); $('#export-status').textContent = '记录已复制。';
  } catch { $('#session-json').focus(); $('#session-json').select(); $('#export-status').textContent = '请按 Command+C 或 Ctrl+C 复制选中的记录。'; }
});
function savePreferences() {
  try { localStorage.setItem('hear-your-look-preferences', JSON.stringify({ voice: $('#voice').checked, speed: $('#speed').value, large: document.documentElement.classList.contains('large'), contrast: document.documentElement.classList.contains('high-contrast') })); } catch { /* Storage may be disabled; settings still work for this page. */ }
}
function restorePreferences() {
  try {
    const prefs = JSON.parse(localStorage.getItem('hear-your-look-preferences') || 'null'); if (!prefs) return;
    if (typeof prefs.voice === 'boolean') $('#voice').checked = prefs.voice;
    if (['0.7', '0.9', '1.1'].includes(prefs.speed)) $('#speed').value = prefs.speed;
    if (prefs.large) { document.documentElement.classList.add('large'); $('#large').textContent = '标准字号'; $('#large').setAttribute('aria-pressed', 'true'); }
    if (prefs.contrast) { document.documentElement.classList.add('high-contrast'); $('#contrast').textContent = '标准对比度'; $('#contrast').setAttribute('aria-pressed', 'true'); }
  } catch { /* Invalid or unavailable storage is ignored. */ }
}
document.addEventListener('visibilitychange', () => { if (document.hidden) { stopSpeech(); closeCamera(); render(); } });
window.addEventListener('pagehide', () => { runVersion++; requestController?.abort(); stopSpeech(); closeCamera(); removePhoto(); if (exportURL) URL.revokeObjectURL(exportURL); });
restorePreferences(); render();
