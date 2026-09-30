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
  const history=fresh ? [] : Array.from({length:12},(_,i)=>({ts:new Date(2026,8,30,9,i).toISOString(),text:'Please send the project notes.',app:i%2?'firefox':'telegram',words:5,seconds:2,lang:'en'}));
  return {S,calls,api:{
    settings:async()=>clone(S),memory:async()=>({terms:[],fixes:[],scanned:null}),stamp:async()=>1,history:async()=>clone(history),
    insights:async()=>({words:60,minutes_saved:1,wpm:150,apps:[['telegram',6],['firefox',6]],known:0,sessions:history.length,last_used:history[0]?.ts}),
    save_settings:async patch=>Object.assign(S,clone(patch)),
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
  assert(ctx.d.querySelector('#tourStage').textContent.includes(platform==='linux'?'Super':'Win'));
  await ctx.clock.tickAsync(4400);
  assert.equal(ctx.d.querySelector('#tourStage').dataset.phase,'2');
  button(ctx,"Let's go").click(); await ctx.clock.tickAsync(20);
  assert(f.S.tutorial_seen);assert.equal(ctx.d.querySelector('#tutorial').hidden,true);
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
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));
  ctx.close();checks+=14;console.log(platform+' UI: tutorial, branding, logos, greetings, shortcuts, model/API selection PASS');
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
  assert.equal(ctx.d.querySelector('#pause').textContent,'Pause');
  assert.equal(ctx.d.querySelector('.bar span').textContent,'Telegram');
  assert(!ctx.d.querySelector('#tag').textContent.includes('dictation demo'));
  if(platform==='Linux x86_64') {assert.equal(ctx.d.querySelector('.cta a').id,'downloadLinux');assert.equal(ctx.d.querySelector('#osKey').textContent,'Super');}
  if(platform==='Win32') assert(ctx.d.querySelector('#osHint').textContent.includes('Windows detected'));
  if(platform==='MacIntel') assert(ctx.d.querySelector('#osHint').textContent.includes('supported computer'));
  const seen=new Set();
  const catalog=JSON.parse(read('assets/apps.json'));
  assert.equal(ctx.d.querySelectorAll('#appPicker option').length,catalog.length);
  assert(catalog.length>=50);
  // Advance enough simulated time to see every app without clicking the picker.
  for(let i=0;i<650;i++){await advance(1200);seen.add(ctx.d.querySelector('.bar span').textContent);}
  assert.deepEqual([...seen].sort(),catalog.map(a=>a.name).sort());
  const docs=catalog.findIndex(a=>a.id==='googledocs');
  change(ctx,'appPicker',String(docs));await advance(200);
  assert.equal(ctx.d.querySelector('.bar span').textContent,'Google Docs');
  assert(ctx.d.querySelector('.doc-page'));
  assert.equal(ctx.d.querySelector('.app-logo').getAttribute('src'),'assets/logos/'+catalog[docs].logo);
  for(const img of ctx.d.querySelectorAll('img')) assert(fs.existsSync(root+'/site/'+img.getAttribute('src')));
  button(ctx,'Pause').click();const current=ctx.d.querySelector('.bar span').textContent;await advance(20000);
  assert.equal(ctx.d.querySelector('.bar span').textContent,current);
  button(ctx,'Play').click();await advance(12000);assert.equal(ctx.d.querySelector('#pause').textContent,'Pause');
  assert.equal(ctx.errors.length,0,ctx.errors.map(e=>e.message).join('\n'));ctx.close();checks+=9;
  console.log(platform+' website: OS routing, automatic '+catalog.length+'-app cycle, picker, pause/resume PASS');
}
(async()=>{await ui('windows');await ui('linux');await setup('windows');await setup('linux');await website('Win32');await website('Linux x86_64');await website('MacIntel');console.log(checks+' interface assertions passed');})().catch(e=>{console.error(e);process.exitCode=1;});
