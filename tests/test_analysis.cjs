const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../hear-your-look-website/analysis.js'), 'utf8'), context);
const quality = {left_corner_visible:true,right_corner_visible:true,upper_border_visible:true,lower_border_visible:true,sharp_enough:true,lit_enough:true,occluded:false,reason:'ok'};
const valid = {mode:'ai',status:'clear',title:'未见明显外溢',guidance:'可以结束',quality:'可观察',smudging:'未见外溢',evidence:'未经验证',reason:'ok',orientation:'normal',image_side:'unknown',region:'unknown',quality_check:quality};
assert.equal(context.validateMakeupResult(valid).status, 'clear');
assert.equal(context.validateMakeupResult({...valid,status:'uncertain',reason:'occluded',quality_check:{...quality,occluded:true,reason:'occluded'}}).status, 'uncertain');
for (const changes of [
  {quality_check:null},
  {quality_check:{...quality,right_corner_visible:false}},
  {quality_check:{...quality,occluded:true}},
  {quality_check:{...quality,sharp_enough:1}},
  {reason:'occluded'},
  {orientation:'unknown'},
  {status:'unchanged'}
]) assert.throws(() => context.validateMakeupResult({...valid,...changes}));
assert.equal(context.validateMakeupResult({mode:'demo',status:'adjust',title:'预设',guidance:'预设',quality:'预设',smudging:'预设',evidence:'预设'}).mode, 'demo');
console.log('前端结果校验：10 项通过。');
