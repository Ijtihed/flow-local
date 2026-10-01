// Isolated DOM tests. No browser, desktop, microphone or real API account is accessed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const FakeTimers = require('@sinonjs/fake-timers');
const root = require('node:path').resolve(__dirname, '..');
const read = p => fs.readFileSync(root + '/' + p, 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const base = {name:'Alex',onboarded:true,tutorial_seen:false,platform:'windows',native_window:false,version:'1.5.1',auto_update:true,
  shortcut:'ctrl+win',mood:'auto',styles:{personal:'very casual',work:'casual',email:'formal',ai:'very casual',code:'casual',docs:'formal',other:'casual'},
  languages:['en'],snippets:[],voice_notes:{},ollama:{running:false,model:false},speech_provider:'local',model:'small',
  api_model:'gpt-transcribe',api_base:'https://api.openai.com/v1',api_consent:false,api_key_saved:false,
  speech_models:[{id:'large-v3',gb:3.1,ready:true},{id:'small',gb:.5,ready:true},{id:'large-v3-turbo',gb:1.6,ready:true}]};
let checks=0;
function apiFixture(platform='windows', fresh=false) {
  const S={...clone(base),platform,onboarded:!fresh,name:fresh?'':base.name};
  const calls=[];
  const practice={phase:'ready',ready:true,matched:false,level:0,elapsed:0};
  const recording={ready:true,recording:false,busy:false,phase:'idle',elapsed:0};
  const diagnostic={status:'passed',version:'1.5.0'};
  const updates={phase:'idle',current:base.version,publisher:false};
  const history=fresh ? [] : Array.from({length:12},(_,i)=>({ts:new Date(2026,8,30,9,i).toISOString(),text:'Please send the project notes.',app:i%2?'firefox':'telegram',words:5,seconds:2,lang:'en'}));
  return {S,calls,practice,recording,diagnostic,updates,api:{
    update_status:async()=>clone(updates),
    check_updates:async()=>{Object.assign(updates,{phase:'checking',message:''});return true},
    install_update:async()=>{calls.push({action:'update'});Object.assign(updates,{phase:'downloading',progress:0});return true},
    save_update_access:async token=>{calls.push({action:'access',token});Object.assign(updates,{phase:'checking',message:''});return true},
    forget_update_access:async()=>true,publish_update:async()=>{calls.push({action:'publish'});return true},
    diagnostics:async()=>clone(diagnostic),copy_speech_report:async()=>true,export_speech_report:async()=>"/fixture/Reports/check.json",
    settings:async()=>clone(S),memory:async()=>({terms:[],fixes:[],scanned:null}),stamp:async()=>1,history:async()=>clone(history),
    insights:async()=>({words:60,minutes_saved:1,wpm:150,apps:[['telegram',6],['firefox',6]],known:0,sessions:history.length,last_used:history[0]?.ts}),
    save_settings:async patch=>Object.assign(S,clone(patch)),
    practice_open:async()=>({id:'a'.repeat(32),phrase:'I can speak instead of typing.',api:false}),
    practice_status:async()=>clone(practice),
    practice_start:async()=>Object.assign(practice,{phase:'recording',level:.7,elapsed:2,text:undefined}),
    practice_stop:async()=>Object.assign(practice,{phase:'thinking',level:0,elapsed:1}),
    practice_cancel:async()=>Object.assign(practice,{phase:'retry',matched:false,message:'Recording cancelled.'}),
    practice_close:async()=>true,practice_focus:async()=>true,
    practice_complete:async()=>{if(!practice.matched)throw new Error('Say the phrase first');Object.assign(S,{tutorial_seen:true,tutorial_version:2});return true},
    recording_status:async()=>clone(recording),
    record_start:async()=>Object.assign(recording,{recording:true,phase:'listening',elapsed:2}),
    record_stop:async()=>Object.assign(recording,{recording:false,busy:true,phase:'transcribing',elapsed:1}),
    record_cancel:async()=>{},
    system:async()=>({platform,gpu:null,cuda:false,recommended_model:'small',models:S.speech_models,vaults:[],name:'Alex'}),
    configure_speech:async config=>{calls.push(clone(config));S.speech_provider=config.provider;if(config.provider==='local')S.model=config.model;else S.api_model=config.model;S.api_consent=config.consent;S.api_key_saved=!!config.key},
    setup_run:async()=>{throw new Error('Unexpected download in interface test')},setup_status:async()=>({task:null,finished:[],error:null}),
    finish_onboarding:async(name,languages)=>{Object.assign(S,{name,languages,onboarded:true});return true},
  }};
}
function dom(html, extra={}) {
  html=html.replace('<script src="assets/apps.js"></script>',()=>'<script>'+read('assets/apps.js')+'</script>');
  html=html.replace('<script src="assets/demo-levels.js"></script>',()=>'<script>'+read('site/assets/demo-levels.js')+'</script>');
  const errors=[],vc=new VirtualConsole(); vc.on('jsdomError',e=>errors.push(e));
  let clock;
  const page=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,url:'http://127.0.0.1:9000/',virtualConsole:vc,
    beforeParse(w){w.matchMedia=()=>({matches:!!extra.reducedMotion}); clock=FakeTimers.withGlobal(w).install({now:new Date(2026,8,30,9,35).getTime(),toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval','performance','requestAnimationFrame','cancelAnimationFrame']});
      if(extra.api) w.pywebview={api:extra.api};
      if(extra.platform) {Object.defineProperty(w.navigator,'platform',{value:extra.platform});Object.defineProperty(w.navigator,'userAgent',{value:extra.ua || extra.platform});}
      if(extra.touches) Object.defineProperty(w.navigator,'maxTouchPoints',{value:extra.touches});
    }});
  return {page,clock,errors,d:page.window.document,w:page.window,close(){clock.uninstall();page.window.close();}};
}
function button(ctx,label){return [...ctx.d.querySelectorAll('button')].find(b=>b.textContent.trim()===label)}
function change(ctx,id,value){const el=ctx.d.getElementById(id);assert(el,id);el.value=value;el.dispatchEvent(new ctx.w.Event('change',{bubbles:true}));}
function input(ctx,id,value){const el=ctx.d.getElementById(id);assert(el,id);el.value=value;el.dispatchEvent(new ctx.w.Event('input',{bubbles:true}));}
async function ui(platform) {
  const f=apiFixture(platform);
  f.S.gpu='Limited GPU'; f.S.recommended_model='small';
  const ctx=dom(read('ui.html'),{api:f.api});
  await ctx.clock.tickAsync(500);
  assert.equal(ctx.d.querySelector('#tutorial').hidden,false);
  assert.equal(ctx.d.querySelectorAll('.brand').length,1);
  assert(!ctx.d.body.textContent.includes('Private, on this PC'));
  assert.equal(ctx.d.querySelector('#platformLabel').textContent,'v1.5.1');
  assert(!ctx.d.querySelector('#skipTour'));
  assert.equal(ctx.d.querySelector('#practicePhrase').textContent,'I can speak instead of typing.');
  assert(ctx.d.querySelector('#tourHint').textContent.includes(platform==='linux'?'Super':'Win'));
  assert(ctx.d.querySelector('#tourHint').textContent.includes('let go'));
  await ctx.clock.tickAsync(4400);
  assert(!f.S.tutorial_seen);
  ctx.d.dispatchEvent(new ctx.w.KeyboardEvent('keydown',{key:'Escape'}));await ctx.clock.tickAsync(20);
  assert(!ctx.d.querySelector('#tutorial').hidden);
  const output=ctx.d.querySelector('#practiceOutput'),next=ctx.d.querySelector('#practiceAction');
  assert.equal(output.tagName,'TEXTAREA');assert(output.readOnly);assert.equal(output.value,'');
  assert.equal(ctx.d.activeElement,output);assert(next.hidden&&next.disabled);
  assert(!ctx.d.querySelector('.practice-steps'));assert(ctx.d.querySelector('#practiceOptions').hidden);assert(!button(ctx,'Record'));
  Object.assign(f.practice,{phase:'error',ready:false,message:'The speech engine could not start.'});await ctx.clock.tickAsync(250);
  assert(!ctx.d.querySelector('#practiceOptions').hidden,'A failed engine must remain recoverable');
  button(ctx,'Speech settings').click();assert(!ctx.d.querySelector('#practiceOptionsPanel').hidden);
  Object.assign(f.practice,{phase:'ready',ready:true,message:''});
  button(ctx,'Use this engine').click();await ctx.clock.tickAsync(250);
  assert.equal(f.calls.at(-1).model,'small');f.calls.length=0;
  assert(ctx.d.querySelector('#practiceOptionsPanel').hidden);assert.equal(ctx.d.activeElement,output);
  output.value='I can speak instead of typing.';await ctx.clock.tickAsync(250);
  assert(next.hidden&&next.disabled,'Typed text must not pass the speech check');
  Object.assign(f.practice,{phase:'recording',level:.7,elapsed:2,text:undefined});await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('#tutorial').dataset.state,'recording');assert.equal(output.value,'');
  Object.assign(f.practice,{phase:'thinking',level:0,elapsed:1});await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('#practiceState').textContent,'Thinking…');
  assert.equal(output.value,'');assert(next.hidden&&next.disabled);
  Object.assign(f.practice,{phase:'retry',matched:false,text:'This is a different sentence.',message:'Try again.'});await ctx.clock.tickAsync(250);
  assert.equal(output.value,'This is a different sentence.');assert(next.hidden&&next.disabled);
  Object.assign(f.practice,{phase:'recording',text:undefined,message:''});await ctx.clock.tickAsync(250);
  assert.equal(output.value,'','A new attempt starts with an empty box');
  Object.assign(f.practice,{phase:'thinking'});await ctx.clock.tickAsync(250);
  Object.assign(f.practice,{phase:'passed',matched:true,text:'I can speak instead of typing.'});await ctx.clock.tickAsync(250);
  assert(ctx.d.querySelector('#tourHint').textContent.includes(platform==='linux'?'Super':'Win'));
  assert.equal(output.value,'I can speak instead of typing.');assert(!next.hidden&&!next.disabled);
  output.focus();ctx.d.dispatchEvent(new ctx.w.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,cancelable:true}));
  assert.equal(ctx.d.activeElement,next,'Tab stays inside the tutorial');
  next.click();await ctx.clock.tickAsync(20);
  assert(!ctx.d.querySelector('#tutorial').hidden);assert(ctx.d.querySelector('#scroll').inert);
  await ctx.clock.tickAsync(300);
  assert(f.S.tutorial_seen);assert.equal(ctx.d.querySelector('#tutorial').hidden,true);
  assert.equal(ctx.d.querySelector('#scroll').inert,false);
  assert(!button(ctx,'Record'),'Home uses the global dictation shortcut');
  assert(ctx.d.querySelector('.lede').textContent.includes('Hold'));
  assert(ctx.d.querySelector('#healthNotice').hidden,'Successful checks remain silent');
  assert.equal(ctx.d.querySelector('.app-name img').getAttribute('src'),'assets/logos/telegram.svg');
  assert.equal(ctx.d.querySelectorAll('.app-name img')[1].getAttribute('src'),'assets/logos/firefox.svg');
  assert(!ctx.d.querySelector('#mood'));
  assert(!ctx.d.querySelector('#greetingHint'));
  assert(!ctx.d.body.textContent.includes("Say what's on your mind."));
  const before=ctx.d.querySelector('#greeting').textContent;
  ctx.clock.setSystemTime(new Date(2026,8,30,20,35));await ctx.clock.tickAsync(60000);
  assert.notEqual(ctx.d.querySelector('#greeting').textContent,before);
  ctx.d.querySelector('[data-view="snippets"]').click();
  assert(ctx.d.querySelector('#view').textContent.includes('Spoken shortcuts'));
  input(ctx,'s-trigger','my email');input(ctx,'s-text','alex@example.com');button(ctx,'Add shortcut').click();await ctx.clock.tickAsync(20);
  assert.deepEqual(f.S.snippets,[{trigger:'my email',text:'alex@example.com'}]);
  ctx.d.querySelector('[data-view="settings"]').click();
  assert(ctx.d.querySelector('#settingsSpeech-model option[value="small"]').textContent.includes('recommended'));
  assert(!ctx.d.querySelector('#settingsSpeech-model option[value="large-v3"]').textContent.includes('recommended'));
  const auto=ctx.d.querySelector('[data-toggle="auto_update"]');
  assert(auto.classList.contains('on')); auto.click(); await ctx.clock.tickAsync(240);
  assert.equal(f.S.auto_update,false);
  assert(!button(ctx,'View report'));
  assert(!ctx.d.querySelector('#view').textContent.includes('Known audio is checked'));
  change(ctx,'settingsSpeech-model','large-v3-turbo');button(ctx,'Use this engine').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.at(-1).model,'large-v3-turbo');
  ctx.d.querySelector('[data-provider="api"]').click();button(ctx,'Use this engine').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.length,1);assert(!ctx.d.querySelector('#settingsSpeech-error').hidden);
  input(ctx,'settingsSpeech-key','dummy-local-test-key');
  const consent=ctx.d.querySelector('#settingsSpeech-consent');consent.checked=true;consent.dispatchEvent(new ctx.w.Event('change'));
  button(ctx,'Use this engine').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.at(-1).provider,'api');assert.equal(f.calls.at(-1).consent,true);
  assert(!ctx.d.body.textContent.includes('dummy-local-test-key'));
  Object.assign(f.diagnostic,{status:'failed',reason:'Fixture model failed'});await ctx.clock.tickAsync(2600);
  assert(!ctx.d.querySelector('#healthNotice').hidden);
  button(ctx,'Review report').click();await ctx.clock.tickAsync(20);
  assert(!ctx.d.querySelector('#reportDialog').hidden);
  assert.equal(JSON.parse(ctx.d.querySelector('#reportText').value).status,'failed');
  button(ctx,'Close').click();assert(ctx.d.querySelector('#reportDialog').hidden);
  button(ctx,'Check for updates').click();await ctx.clock.tickAsync(20);
  assert(button(ctx,'Checking…').disabled);
  Object.assign(f.updates,{phase:'available',latest:'1.6.0',publisher:true});await ctx.clock.tickAsync(500);
  assert(ctx.d.querySelector('#updateMessage').textContent.includes('1.6.0'));
  assert(!ctx.d.querySelector('#publishUpdates').hidden);
  button(ctx,'Publish update on GitHub').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.at(-1).action,'publish');
  button(ctx,'Update').click();await ctx.clock.tickAsync(20);assert.equal(f.calls.at(-1).action,'update');
  assert(button(ctx,'Downloading…').disabled);
  Object.assign(f.updates,{phase:'downloading',progress:63});await ctx.clock.tickAsync(500);
  assert.equal(ctx.d.querySelector('#updateProgress').value,63);
  Object.assign(f.updates,{phase:'error',message:'GitHub access required.'});await ctx.clock.tickAsync(500);
  assert(ctx.d.querySelector('#updateAccess').open);assert(!button(ctx,'Check for updates').disabled);
  input(ctx,'updateToken','private-test-token');button(ctx,'Connect').click();await ctx.clock.tickAsync(20);
  assert.equal(ctx.d.querySelector('#updateToken').value,'');
  assert(!ctx.d.body.textContent.includes('private-test-token'));
  Object.assign(f.updates,{phase:'current'});await ctx.clock.tickAsync(500);
  assert.equal(ctx.d.querySelector('#updateMessage').textContent,"You're up to date.");
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));
  ctx.close();checks+=29;console.log(platform+' UI: tutorial, branding, logos, greetings, shortcuts, model/API selection, diagnostic warning, updates PASS');
}
async function setup(platform,reducedMotion=false) {
  const f=apiFixture(platform,true),ctx=dom(read('ui.html'),{api:f.api,reducedMotion});await ctx.clock.tickAsync(50);
  button(ctx,'Get started').click();
  assert.equal(ctx.d.querySelector('#obName').value,'','Do not guess the name from the OS account');
  assert(button(ctx,'Continue').disabled);
  input(ctx,'obName','   ');assert(button(ctx,'Continue').disabled);
  input(ctx,'obName','Alex');assert(!button(ctx,'Continue').disabled);button(ctx,'Continue').click();
  assert.equal(ctx.d.querySelector('#setupSpeech-model').value,'small');
  ctx.d.querySelector('#setupSpeech [data-provider="api"]').click();button(ctx,'Continue').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.length,0);assert(!ctx.d.querySelector('#setupSpeech-error').hidden);
  ctx.d.querySelector('#setupSpeech [data-provider="local"]').click();change(ctx,'setupSpeech-model','large-v3-turbo');
  button(ctx,'Continue').click();await ctx.clock.tickAsync(20);button(ctx,'Start using Flow').click();await ctx.clock.tickAsync(20);
  if(!reducedMotion){assert(ctx.d.querySelector('#ob').classList.contains('leaving'));assert(!ctx.d.querySelector('#ob').hidden);assert(ctx.d.querySelector('#tutorial').hidden);assert(ctx.d.querySelector('#scroll').inert);await ctx.clock.tickAsync(300);}
  assert(ctx.d.querySelector('#ob').hidden);assert(!ctx.d.querySelector('#ob').classList.contains('leaving'));
  assert(f.S.onboarded);assert.equal(f.S.name,'Alex');assert.equal(f.calls[0].model,'large-v3-turbo');assert(!ctx.d.querySelector('#tutorial').hidden);
  assert.equal(ctx.errors.length,0);ctx.close();checks+=7;console.log(platform+' first-run setup: required name, model choice and consent PASS');
}
async function website(platform,ua,reducedMotion=false,touches=0) {
  const ctx=dom(read('site/index.html'),{platform,ua,reducedMotion,touches});
  const mobile=/Android|iPhone|iPad|iPod/i.test(platform+' '+ua) || (/Mac/i.test(platform) && touches>1);
  // Synchronous clock steps + microtask drains avoid the host timer latency
  // of tickAsync for every 50 ms polling timer in a full 65-app cycle.
  const advance=async ms=>{for(let elapsed=0;elapsed<ms;elapsed+=50){ctx.clock.tick(50);await Promise.resolve();await Promise.resolve();}};
  assert(!ctx.d.querySelector('#pause'));
  assert(!ctx.d.querySelector('#appPicker'));
  assert.equal(ctx.d.querySelector('.bar span').textContent,'Linear');
  assert.equal(ctx.d.querySelector('footer').textContent.trim(),'Made by Ijtihed');
  assert(ctx.d.querySelector('footer a[aria-label="Flow on GitHub"] img'));
  assert(!ctx.d.querySelector('.caret'));
  assert(!ctx.d.querySelector('#tag').textContent.includes('dictation demo'));
  assert(!ctx.d.querySelector('#osHint'));
  assert(!ctx.d.body.textContent.includes('Windows 10 or 11'));
  if(mobile) {
    assert.equal(ctx.d.querySelector('#download').textContent.trim(),'GitHub');
    assert.equal(ctx.d.querySelector('#download').href,'https://github.com/Ijtihed/flow-local');
    assert(ctx.d.querySelector('#download img'));
  } else assert(ctx.d.querySelector('#osIcon').children.length);
  assert.equal(ctx.d.querySelector('.lede').textContent,'Speak naturally. Flow does the typing.');
  if(platform==='Linux x86_64') {assert(ctx.d.querySelector('#download').href.endsWith('Flow-x86_64.AppImage'));assert.equal(ctx.d.querySelector('#osKey').getAttribute('aria-label'),'Super key');}
  if(platform==='Win32') assert(ctx.d.querySelector('#download').href.endsWith('FlowSetup.exe'));
  if(platform==='MacIntel' && !mobile) assert(ctx.d.querySelector('#download').href.endsWith('/releases/latest'));
  const seen=new Set(), order=[];
  let recordingInputHeight,resultInputHeight,firstResultAt;
  const visibleResults = new Map();
  const meterHeights=new Set();
  for(let i=0;i<110;i++) {
    await advance(500);
    const app=ctx.d.querySelector('.bar span').textContent;
    seen.add(app); if(order.at(-1)!==app) order.push(app);
    const typed=ctx.d.querySelector('.typed');
    if(ctx.d.querySelector('.pill.listen')) meterHeights.add(ctx.d.querySelector('.pill i').style.height);
    assert.equal(typed.children.length,0,'Text must be one continuous node');
    if(typed.textContent) {
      if(!visibleResults.has(app)) visibleResults.set(app,new Set());
      visibleResults.get(app).add(typed.textContent);
      if(app==='Linear') { firstResultAt ??= (i+1)*500; resultInputHeight=ctx.w.getComputedStyle(ctx.d.querySelector('.input')).height; }
    } else if(app==='Linear') recordingInputHeight=ctx.w.getComputedStyle(ctx.d.querySelector('.input')).height;
    for(const img of ctx.d.querySelectorAll('img')) assert(fs.existsSync(root+'/site/'+img.getAttribute('src')));
  }
  assert.deepEqual([...seen].sort(),['ChatGPT','Gmail','Linear']);
  assert.deepEqual(order.slice(0,4),['Linear','Gmail','ChatGPT','Linear']);
  assert(firstResultAt<=3000,'The complete first result should appear within three seconds');
  assert.equal(resultInputHeight,recordingInputHeight);
  assert.equal(visibleResults.size,3);
  for(const [app,results] of visibleResults) assert.equal(results.size,1,app+' must paste one complete result without intermediate text');
  assert(meterHeights.size>4,'Recording meter must respond to the reference voice, including reduced motion');
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));ctx.close();checks+=9;
  console.log(platform+' website: OS routing, Linear-first 3-app cycle, footer, continuous text, no demo controls PASS');
}
async function modelSetup() {
  const f=apiFixture('windows',true);
  f.S.speech_models=[{id:'small',gb:.5,ready:false,supported:true,gpu_ok:false,ram_gb:2},
                    {id:'large-v3',gb:3.1,ready:false,supported:false,gpu_ok:false,ram_gb:6}];
  let downloaded;
  f.api.setup_run=async(task,name)=>{downloaded={task,name};return true;};
  f.api.setup_status=async()=>{f.S.speech_models[0].ready=true;return {task:null,error:null};};
  const ctx=dom(read('ui.html'),{api:f.api});await ctx.clock.tickAsync(50);
  button(ctx,'Get started').click();input(ctx,'obName','Alex');button(ctx,'Continue').click();
  assert(ctx.d.querySelector('#setupSpeech-model option[value="large-v3"]').disabled);
  assert.equal(ctx.d.querySelector('#setupSpeech-model').value,'small');
  button(ctx,'Continue').click();await ctx.clock.tickAsync(450);
  assert.deepEqual(downloaded,{task:'model',name:'small'});
  assert.equal(f.calls[0].model,'small');
  assert(button(ctx,'Start using Flow'));
  assert.equal(ctx.errors.length,0);ctx.close();checks+=6;
}
(async()=>{await ui('windows');await ui('linux');await setup('windows');await setup('linux');await setup('windows',true);await modelSetup();await website('Win32');await website('Linux x86_64');await website('MacIntel');await website('Win32',undefined,true);await website('Linux armv8l','Mozilla/5.0 Android');await website('iPhone','Mozilla/5.0 iPhone');await website('MacIntel','Mozilla/5.0 Macintosh Safari',false,5);console.log(checks+' grouped interface checks passed');})().catch(e=>{console.error(e);process.exitCode=1;});
