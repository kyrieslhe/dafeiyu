import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const root=resolve(process.argv[2]||'integrations/runtime');
const require=createRequire(root+'/package.json');
const {minimatch}=require('minimatch');
assert.equal(minimatch('workspace/project/main.py','workspace/**/*.py'),true);
assert.equal(minimatch('workspace/project/.env','workspace/**'),false);
assert.equal(minimatch('var/private.sqlite','workspace/**'),false);
assert.equal(minimatch('README.md','*.md'),true);
const z=require('zod');
assert.equal(z.object({id:z.string()}).safeParse({id:'owner'}).success,true);
assert.equal(z.array(z.string()).max(2).safeParse(['a','b','c']).success,false);
const plugin=await import(root+'/node_modules/@tencent-weixin/openclaw-weixin/dist/index.js');
assert.equal(plugin.default.id,'openclaw-weixin');
console.log('Runtime imports and glob/schema compatibility passed.');

const npmPackage=require.resolve('npm/package.json');
const npmRequire=createRequire(npmPackage);
assert.equal(npmRequire('./package.json').version,'12.2.2+dafeiyu.1');
assert.deepEqual(npmRequire('./package.json').bundleDependencies,[]);
assert.equal(npmRequire('glob/package.json').version,'14.0.3');
assert.equal(npmRequire('minimatch/package.json').version,'11.0.4');
const {glob}=npmRequire('glob');
await assert.rejects(glob('**/*',{signal:AbortSignal.abort()}));
console.log('Actual npm dependency resolution uses fixed glob/minimatch.');

const {mkdtempSync,mkdirSync,writeFileSync,existsSync,rmSync}=await import('node:fs');
const {tmpdir}=await import('node:os');
const {join}=await import('node:path');
const {execFileSync}=await import('node:child_process');
const scratch=mkdtempSync(join(tmpdir(),'fish-npm-compat-'));
try {
 const source=join(scratch,'source'),packed=join(scratch,'packed'),project=join(scratch,'project');
 for(const path of [source,packed,project])mkdirSync(path);
 const userconfig=join(scratch,'npmrc');writeFileSync(userconfig,'');
 writeFileSync(join(source,'package.json'),JSON.stringify({name:'fish-security-fixture',version:'1.0.0',main:'index.cjs',scripts:{prepack:'node -e "require(\'node:fs\').writeFileSync(\'SHOULD_NOT_RUN\',\'bad\')"'}}));
 writeFileSync(join(source,'index.cjs'),'module.exports=42;\n');
 writeFileSync(join(project,'package.json'),JSON.stringify({name:'fish-install-fixture',version:'1.0.0',private:true}));
 const cli=npmRequire.resolve('./bin/npm-cli.js');
 const options=['--userconfig',userconfig,'--cache',join(scratch,'cache')];
 const packageInfo=JSON.parse(execFileSync(process.execPath,[cli,...options,'pack',source,'--ignore-scripts','--json','--pack-destination',packed],{encoding:'utf8',timeout:20000}));
 assert.equal(existsSync(join(source,'SHOULD_NOT_RUN')),false);
 execFileSync(process.execPath,[cli,...options,'install',join(packed,Object.values(packageInfo)[0].filename),'--prefix',project,'--offline','--ignore-scripts','--no-audit','--no-fund'],{stdio:'pipe',timeout:20000});
 assert.equal(createRequire(join(project,'package.json'))('fish-security-fixture'),42);
 console.log('Patched npm packs and installs an offline fixture with lifecycle scripts disabled.');
}finally{rmSync(scratch,{recursive:true,force:true});}
