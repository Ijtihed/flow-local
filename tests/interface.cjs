// Isolated DOM tests. No browser, desktop, microphone or real API account is accessed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const FakeTimers = require('@sinonjs/fake-timers');
const root = require('node:path').resolve(__dirname, '..');
const read = p => fs.readFileSync(root + '/' + p, 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const base = {name:'Alex',onboarded:true,tutorial_seen:false,platform:'windows',native_window:false,
  shortcut:'ctrl+win',mood:'auto',styles:{personal:'very casual',work:'casual',email:'formal',ai:'very casual',code:'casual',docs:'formal',other:'casual'},
  languages:['en'],snippets:[],voice_notes:{},ollama:{running:false,model:false},speech_provider:'local',model:'small',
  api_model:'gpt-transcribe',api_base:'https://api.openai.com/v1',api_consent:false,api_key_saved:false,
  speech_models:[{id:'large-v3',gb:3.1,ready:true},{id:'small',gb:.5,ready:true},{id:'large-v3-turbo',gb:1.6,ready:true}]};
let checks=0;
function apiFixture(platform='windows', fresh=false) {
  const S={...clone(base),platform,onboarded:!fresh};
  const calls=[];
  const practice={phase:'ready',ready:true,matched:false,level:0,elapsed:0};
  const recording={ready:true,recording:false,busy:false,phase:'idle',elapsed:0};
  const diagnostic={status:'passed',version:'1.5.0'};
  const history=fresh ? [] : Array.from({length:12},(_,i)=>({ts:new Date(2026,8,30,9,i).toISOString(),text:'Please send the project notes.',app:i%2?'firefox':'telegram',words:5,seconds:2,lang:'en'}));
  return {S,calls,practice,recording,diagnostic,api:{
    diagnostics:async()=>clone(diagnostic),copy_speech_report:async()=>true,export_speech_report:async()=>"/fixture/Reports/check.json",
    settings:async()=>clone(S),memory:async()=>({terms:[],fixes:[],scanned:null}),stamp:async()=>1,history:async()=>clone(history),
    insights:async()=>({words:60,minutes_saved:1,wpm:150,apps:[['telegram',6],['firefox',6]],known:0,sessions:history.length,last_used:history[0]?.ts}),
    save_settings:async patch=>Object.assign(S,clone(patch)),
    practice_open:async()=>({id:'a'.repeat(32),phrase:'I can speak instead of typing.',api:false}),
    practice_status:async()=>clone(practice),
    practice_start:async()=>Object.assign(practice,{phase:'recording',level:.7,elapsed:2,text:undefined}),
    practice_stop:async()=>Object.assign(practice,{phase:'thinking',level:0,elapsed:1}),
    practice_cancel:async()=>Object.assign(practice,{phase:'retry',matched:false,message:'Recording cancelled.'}),
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
  const errors=[],vc=new VirtualConsole(); vc.on('jsdomError',e=>errors.push(e));
  let clock;
  const page=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,url:'http://127.0.0.1:9000/',virtualConsole:vc,
    beforeParse(w){w.matchMedia=()=>({matches:false}); clock=FakeTimers.withGlobal(w).install({now:new Date(2026,8,30,9,35).getTime(),toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval','performance','requestAnimationFrame','cancelAnimationFrame']});
      if(extra.api) w.pywebview={api:extra.api};
      if(extra.platform) {Object.defineProperty(w.navigator,'platform',{value:extra.platform});Object.defineProperty(w.navigator,'userAgent',{value:extra.ua || extra.platform});}
    }});
  return {page,clock,errors,d:page.window.document,w:page.window,close(){clock.uninstall();page.window.close();}};
}
function button(ctx,label){return [...ctx.d.querySelectorAll('button')].find(b=>b.textContent.trim()===label)}
function change(ctx,id,value){const el=ctx.d.getElementById(id);assert(el,id);el.value=value;el.dispatchEvent(new ctx.w.Event('change',{bubbles:true}));}
function input(ctx,id,value){const el=ctx.d.getElementById(id);assert(el,id);el.value=value;el.dispatchEvent(new ctx.w.Event('input',{bubbles:true}));}
async function ui(platform) {
  const f=apiFixture(platform),ctx=dom(read('ui.html'),{api:f.api});
  await ctx.clock.tickAsync(500);
  assert.equal(ctx.d.querySelector('#tutorial').hidden,false);
  assert.equal(ctx.d.querySelectorAll('.brand').length,1);
  assert(!ctx.d.body.textContent.includes('Private, on this PC'));
  assert(ctx.d.querySelector('#platformLabel').textContent.startsWith(platform==='linux'?'Linux':'Windows'));
  assert(!ctx.d.querySelector('#skipTour'));
  assert.equal(ctx.d.querySelector('#practicePhrase').textContent,'I can speak instead of typing.');
  await ctx.clock.tickAsync(4400);
  assert(!f.S.tutorial_seen);
  ctx.d.dispatchEvent(new ctx.w.KeyboardEvent('keydown',{key:'Escape'}));await ctx.clock.tickAsync(20);
  assert(!ctx.d.querySelector('#tutorial').hidden);
  ctx.d.querySelector('#practiceAction').click();await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('#practiceMeter').dataset.state,'recording');
  assert(parseFloat(ctx.d.querySelector('.practice-bars i').style.height)>4);
  button(ctx,'Finish').click();await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('#practiceState').textContent,'Thinking…');
  assert(button(ctx,'Thinking…').disabled);
  Object.assign(f.practice,{phase:'retry',matched:false,text:'This is a different sentence.',message:'Try again.'});await ctx.clock.tickAsync(250);
  assert(!button(ctx,'Start using Flow'));
  button(ctx,'Try again').click();await ctx.clock.tickAsync(250);button(ctx,'Finish').click();await ctx.clock.tickAsync(250);
  Object.assign(f.practice,{phase:'passed',matched:true,text:'I can speak instead of typing.'});await ctx.clock.tickAsync(250);
  assert(ctx.d.querySelector('#tourHint').textContent.includes(platform==='linux'?'Super':'Win'));
  button(ctx,'Start using Flow').click();await ctx.clock.tickAsync(20);
  assert(f.S.tutorial_seen);assert.equal(ctx.d.querySelector('#tutorial').hidden,true);
  ctx.d.querySelector('#recordButton').click();await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('#recordButton').textContent,'Finish');
  ctx.d.querySelector('#recordButton').click();await ctx.clock.tickAsync(250);
  assert(ctx.d.querySelector('#recordCaption').textContent.includes('Thinking'));
  Object.assign(f.recording,{recording:false,busy:false,phase:'idle'});await ctx.clock.tickAsync(250);
  assert.equal(ctx.d.querySelector('.app-name img').getAttribute('src'),'assets/logos/telegram.svg');
  assert.equal(ctx.d.querySelectorAll('.app-name img')[1].getAttribute('src'),'assets/logos/firefox.svg');
  change(ctx,'mood','relaxed');await ctx.clock.tickAsync(20);
  assert.equal(f.S.mood,'relaxed');
  const before=ctx.d.querySelector('#greeting').textContent;
  ctx.clock.setSystemTime(new Date(2026,8,30,20,35));await ctx.clock.tickAsync(60000);
  assert.notEqual(ctx.d.querySelector('#greeting').textContent,before);
  ctx.d.querySelector('[data-view="snippets"]').click();
  assert(ctx.d.querySelector('#view').textContent.includes('Spoken shortcuts'));
  input(ctx,'s-trigger','my email');input(ctx,'s-text','alex@example.com');button(ctx,'Add shortcut').click();await ctx.clock.tickAsync(20);
  assert.deepEqual(f.S.snippets,[{trigger:'my email',text:'alex@example.com'}]);
  ctx.d.querySelector('[data-view="settings"]').click();
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
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));
  ctx.close();checks+=18;console.log(platform+' UI: tutorial, branding, logos, greetings, shortcuts, model/API selection, diagnostic warning PASS');
}
async function setup(platform) {
  const f=apiFixture(platform,true),ctx=dom(read('ui.html'),{api:f.api});await ctx.clock.tickAsync(50);
  button(ctx,'Get started').click();button(ctx,'Continue').click();
  assert.equal(ctx.d.querySelector('#setupSpeech-model').value,'small');
  ctx.d.querySelector('#setupSpeech [data-provider="api"]').click();button(ctx,'Continue').click();await ctx.clock.tickAsync(20);
  assert.equal(f.calls.length,0);assert(!ctx.d.querySelector('#setupSpeech-error').hidden);
  ctx.d.querySelector('#setupSpeech [data-provider="local"]').click();change(ctx,'setupSpeech-model','large-v3-turbo');
  button(ctx,'Continue').click();await ctx.clock.tickAsync(20);button(ctx,'Start using Flow').click();await ctx.clock.tickAsync(20);
  assert(f.S.onboarded);assert.equal(f.calls[0].model,'large-v3-turbo');assert(!ctx.d.querySelector('#tutorial').hidden);
  assert.equal(ctx.errors.length,0);ctx.close();checks+=5;console.log(platform+' first-run setup: model choice and consent PASS');
}
async function website(platform,ua) {
  const ctx=dom(read('site/index.html'),{platform,ua});
  // Synchronous clock steps + microtask drains avoid the host timer latency
  // of tickAsync for every 50 ms polling timer in a full 65-app cycle.
  const advance=async ms=>{for(let elapsed=0;elapsed<ms;elapsed+=50){ctx.clock.tick(50);await Promise.resolve();await Promise.resolve();}};
  assert(!ctx.d.querySelector('#pause'));
  assert(!ctx.d.querySelector('#appPicker'));
  assert.equal(ctx.d.querySelector('.bar span').textContent,'Linear');
  assert.equal(ctx.d.querySelector('footer').textContent.trim(),'Made by Ijtihed');
  assert(ctx.d.querySelector('footer a[aria-label="Flow on GitHub"] img'));
  assert(!ctx.d.querySelector('.caret').getAttribute('style'));
  assert(!ctx.d.querySelector('#tag').textContent.includes('dictation demo'));
  assert(!ctx.d.querySelector('#osHint'));
  assert(!ctx.d.body.textContent.includes('Windows 10 or 11'));
  assert(ctx.d.querySelector('#osIcon').children.length);
  assert.equal(ctx.d.querySelector('.lede').textContent,'Speak naturally. Flow does the typing.');
  if(platform==='Linux x86_64') {assert(ctx.d.querySelector('#download').href.endsWith('Flow-x86_64.AppImage'));assert.equal(ctx.d.querySelector('#osKey').getAttribute('aria-label'),'Super key');}
  if(platform==='Win32') assert(ctx.d.querySelector('#download').href.endsWith('FlowSetup.exe'));
  if(platform==='MacIntel') assert(ctx.d.querySelector('#download').href.endsWith('/releases/latest'));
  const seen=new Set(), order=[];
  let recordingInputHeight,typingInputHeight,sawContinuousTyping=false;
  for(let i=0;i<110;i++) {
    await advance(500);
    const app=ctx.d.querySelector('.bar span').textContent;
    seen.add(app); if(order.at(-1)!==app) order.push(app);
    const typed=ctx.d.querySelector('.typed');
    assert.equal(typed.children.length,0,'Text must be one continuous node');
    if(app==='Linear' && ctx.d.querySelector('.win').classList.contains('is-typing')) {
      sawContinuousTyping=true;typingInputHeight=ctx.w.getComputedStyle(ctx.d.querySelector('.input')).height;
      assert.equal(ctx.w.getComputedStyle(ctx.d.querySelector('.caret')).animationName,'');
    } else if(app==='Linear') recordingInputHeight=ctx.w.getComputedStyle(ctx.d.querySelector('.input')).height;
    for(const img of ctx.d.querySelectorAll('img')) assert(fs.existsSync(root+'/site/'+img.getAttribute('src')));
  }
  assert.deepEqual([...seen].sort(),['ChatGPT','Gmail','Linear']);
  assert.deepEqual(order.slice(0,4),['Linear','Gmail','ChatGPT','Linear']);
  assert(sawContinuousTyping);assert.equal(typingInputHeight,recordingInputHeight);
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));ctx.close();checks+=9;
  console.log(platform+' website: OS routing, Linear-first 3-app cycle, footer, continuous text, no demo controls PASS');
}
(async()=>{await ui('windows');await ui('linux');await setup('windows');await setup('linux');await website('Win32');await website('Linux x86_64');await website('MacIntel');console.log(checks+' interface assertions passed');})().catch(e=>{console.error(e);process.exitCode=1;});
