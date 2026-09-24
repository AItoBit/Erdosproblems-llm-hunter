#!/usr/bin/env node
// Run with a local site server and Chrome --headless --remote-debugging-port=9224.
// node scripts/audit_tex_rendering.mjs --url http://127.0.0.1:8765 --output /tmp/tex-audit.json
// Audits 100 Erdos and 25 MathOverflow pages, all their rendered attempts, and source files.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const option = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const base = option('--url', 'http://127.0.0.1:8765');
const output = option('--output', '/tmp/tex-render-audit.json');
const debuggerURL = option('--debugger', 'http://127.0.0.1:9224');
const context = vm.createContext({ window: {} });
for (const file of ['erdos_data.js', 'mo_data.js']) vm.runInContext(fs.readFileSync(path.join(root, 'docs/data', file), 'utf8'), context);
const available = Object.values(context.erdosProblems).filter(p => p.attacks?.length).sort((a,b) => Number(a.number)-Number(b.number));
const spaced = (list, count) => Array.from({ length: Math.min(count, list.length) }, (_, i) => list[Math.floor(i * (list.length-1) / Math.max(1,count-1))]);
const selected = [...available.slice(0,80), ...spaced(available.slice(80),20)].map(p=>({ type:'erdos', id:p.number, attacks:p.attacks }));
selected.push(...spaced(Object.values(context.moProblems).filter(p=>p.attacks?.length).sort((a,b)=>Number(a.id)-Number(b.id)),25).map(p=>({type:'mo',id:p.id,attacks:p.attacks})));
const requested = option('--ids', '');
const comparisonPath=option('--compare','');
const lookup = key => {
    const [type,id] = key.includes(':') ? key.split(':') : ['erdos',key];
    const problem = (type==='mo' ? context.moProblems : context.erdosProblems)[id];
    if(!problem) throw new Error(`Unknown audit problem ${key}`);
    return {type,id,attacks:problem.attacks};
};
const comparisonCases = comparisonPath ? JSON.parse(fs.readFileSync(comparisonPath,'utf8')).pages.map(p=>lookup(`${p.type}:${p.id}`)) : selected;
const cases = requested ? requested.split(',').map(lookup) : comparisonCases;
for (const key of option('--extra','').split(',').filter(Boolean)) {
    const page=lookup(key);
    if(!cases.some(p=>p.type===page.type&&p.id===page.id)) cases.push(page);
}
const sha = input => crypto.createHash('sha256').update(input).digest('hex');
const sources = {};
for (const page of cases) for (const attack of page.attacks) {
    const source = fs.readFileSync(path.join(root, attack.file_path), 'utf8');
    const body = source.replace(/^\s*%\s*COLLECTION_METADATA:[^\n]*\n/, '');
    sources[attack.file_path] = { sha256:sha(source), bytes:Buffer.byteLength(source), matchesPublishedText:body===attack.raw };
}
const target = await (await fetch(`${debuggerURL}/json/new?about:blank`, {method:'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open',resolve,{once:true}));
let seq=0;
const pending=new Map();
let exceptions=[];
ws.addEventListener('message',event=>{
    const m=JSON.parse(event.data);
    if(m.id){const p=pending.get(m.id);if(!p)return;pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}
    else if(m.method==='Runtime.exceptionThrown') exceptions.push(m.params.exceptionDetails.text);
});
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{
    const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result.value;
};
function inspectPage() {
    const attempts = [...document.querySelectorAll('.attempt-content')];
    const items = [...MathJax.startup.document.math];
    const inputFor = element => items.find(item => item.typesetRoot?.contains(element))?.math;
    const errors = [...document.querySelectorAll('mjx-merror')].map(e=>({message:e.getAttribute('data-mjx-error')||e.getAttribute('title')||e.textContent, input:inputFor(e)}));
    const unknown = [...document.querySelectorAll('mjx-mtext[style*="red"]')].map(e=>({input:inputFor(e), html:e.outerHTML.slice(0,350)}));
    const clone=document.getElementById('attempts-container').cloneNode(true);
    clone.querySelectorAll('mjx-container,pre,code').forEach(e=>e.remove());
    const prose=clone.textContent;
    const commands={};for(const match of prose.matchAll(/\\[a-zA-Z]+\*?/g)) commands[match[0]]=(commands[match[0]]||0)+1;
    const badLinks=[...document.querySelectorAll('.attempt-content a')].filter(a=>!/^https?:\/\//.test(a.href)||/[<>\s\\{}]/.test(a.getAttribute('href')||'')).slice(0,20).map(a=>a.getAttribute('href'));
    const mathItems = [...MathJax.startup.document.math].map(item=>({tex:item.math,display:item.display}));
    return { title:document.title, location:location.href, attempts:attempts.length, mathCount:document.querySelectorAll('mjx-container').length,
        errors,unknown,commands,badLinks,escapedHashes:(prose.match(/\\#/g)||[]).length,
        literalNbsp:(prose.match(/&(?:amp;)?nbsp;/g)||[]).length,texttt:(prose.match(/\\texttt\{/g)||[]).length,
        mathItems, textLength:prose.length, mathjaxVersion:MathJax.version };
}
function inspectContrast() {
    const rgb=css=>(css.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
    const lum=css=>rgb(css).map(n=>{n/=255;return n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4}).reduce((a,n,i)=>a+n*[0.2126,0.7152,0.0722][i],0);
    const issues=[];let checked=0;
    for(const e of document.querySelectorAll('.tex-content blockquote,.tex-content .theorem,.tex-content .lemma,.tex-content .proposition,.tex-content .corollary,.tex-content .remark,.tex-content .definition,.tex-content .proof,.tex-content .latex-fbox,.tex-content .latex-parbox,.tex-content code,.tex-content pre,.tex-content .latex-comment')) {
        let current=e, background='';
        while(current){background=getComputedStyle(current).backgroundColor;if(background!=='rgba(0, 0, 0, 0)'&&background!=='transparent')break;current=current.parentElement;}
        if(!current) background='rgb(255,255,255)';
        const foreground=getComputedStyle(e).color, a=lum(foreground), b=lum(background), ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
        checked++;
        if(ratio<4.5) issues.push({tag:e.tagName,className:e.className,ratio:+ratio.toFixed(2),foreground,background,text:e.textContent.slice(0,100)});
    }
    return {checked,issues};
}
const report={ base,createdAt:new Date().toISOString(),rendererSha256:null,sources,pages:[],summary:{} };
try {
    report.rendererSha256=sha(await(await fetch(`${base}/problem.html`)).text());
    await call('Page.enable');await call('Runtime.enable');await call('Network.enable');
    await call('Network.setBlockedURLs',{urls:['*googletagmanager.com*','*google-analytics.com*','*giscus.app*']});
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    for(const [index,page] of cases.entries()) {
        exceptions=[];
        const route=`problem.html?type=${page.type}&id=${encodeURIComponent(page.id)}`;
        const result={type:page.type,id:page.id,route,sourcePaths:page.attacks.map(a=>a.file_path)};
        try {
            await call('Page.navigate',{url:`${base}/${route}`});
            await evaluate(`new Promise((resolve,reject)=>{const start=Date.now();const poll=()=>{if(location.search===${JSON.stringify('?type='+page.type+'&id='+encodeURIComponent(page.id))}&&document.readyState!=='loading'&&document.querySelectorAll('.attempt-content').length===${page.attacks.length}&&window.MathJax?.startup?.promise)return resolve(true);if(Date.now()-start>45000)return reject(new Error('Renderer or MathJax did not load'));setTimeout(poll,75)};poll()})`);
            await evaluate('MathJax.startup.promise');
            Object.assign(result,await evaluate(`(${inspectPage.toString()})()`));
            result.mathDigest=sha(JSON.stringify(result.mathItems));
            for(const theme of ['light','dark']){
                await evaluate(`document.documentElement.setAttribute('data-theme','${theme}')`);
                result[`${theme}Contrast`]=await evaluate(`(${inspectContrast.toString()})()`);
            }
            result.exceptions=[...exceptions];
        } catch(error) {result.failure=error instanceof Error ? error.message : JSON.stringify(error);}
        report.pages.push(result);
        if((index+1)%10===0||index===cases.length-1) console.log(`${index+1}/${cases.length} pages: ${page.type} ${page.id}; math=${result.mathCount}; errors=${result.errors?.length}; failure=${result.failure||'none'}`);
        fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
    }
    report.summary={pages:report.pages.length,sourceFiles:Object.keys(sources).length,
        stalePublishedSources:Object.values(sources).filter(s=>!s.matchesPublishedText).length,
        failures:report.pages.filter(p=>p.failure).length,mathExpressions:report.pages.reduce((n,p)=>n+(p.mathCount||0),0),
        mathErrors:report.pages.reduce((n,p)=>n+(p.errors?.length||0),0),unknownMacros:report.pages.reduce((n,p)=>n+(p.unknown?.length||0),0),
        escapedHashes:report.pages.reduce((n,p)=>n+(p.escapedHashes||0),0),literalNbsp:report.pages.reduce((n,p)=>n+(p.literalNbsp||0),0),
        texttt:report.pages.reduce((n,p)=>n+(p.texttt||0),0),badLinks:report.pages.reduce((n,p)=>n+(p.badLinks?.length||0),0),
        lightContrastIssues:report.pages.reduce((n,p)=>n+(p.lightContrast?.issues.length||0),0),darkContrastIssues:report.pages.reduce((n,p)=>n+(p.darkContrast?.issues.length||0),0)};
    const finalRenderer=sha(await(await fetch(`${base}/problem.html`)).text());
    report.summary.rendererChangedDuringAudit=finalRenderer!==report.rendererSha256;
    if(comparisonPath) {
        const baseline=JSON.parse(fs.readFileSync(comparisonPath,'utf8'));
        const byID=new Map(baseline.pages.map(p=>[`${p.type}:${p.id}`,p]));
        const normalize=tex=>tex.replace(/\s+/g,'');
        report.comparison={baseline:comparisonPath,pages:[],unchangedMathExpressions:0,priorMathExpressions:0};
        for(const page of report.pages) {
            const prior=byID.get(`${page.type}:${page.id}`);
            if(!prior||page.failure||prior.failure) continue;
            const currentCounts=new Map();
            for(const item of page.mathItems) { const key=normalize(item.tex); currentCounts.set(key,(currentCounts.get(key)||0)+1); }
            let unchanged=0;
            const changed=[];
            for(const item of prior.mathItems) {
                const key=normalize(item.tex), count=currentCounts.get(key)||0;
                if(count) {unchanged++;currentCounts.set(key,count-1);} else changed.push(item.tex);
            }
            report.comparison.unchangedMathExpressions+=unchanged;
            report.comparison.priorMathExpressions+=prior.mathItems.length;
            report.comparison.pages.push({type:page.type,id:page.id,unchangedMath:unchanged,priorMath:prior.mathItems.length,
                changedPriorMath:changed,beforeErrors:prior.errors.length,afterErrors:page.errors.length});
        }
    }
    fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report.summary));
    if(report.summary.failures||report.summary.rendererChangedDuringAudit) process.exitCode=1;
} finally {try{await call('Page.close');}catch{}ws.close();}
