// Build three self-contained maps from a privately supplied Blizzard demo campaign.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const Mpq = require('mdx-m3-viewer/dist/cjs/parsers/mpq/archive').default;
const Campaign = require('mdx-m3-viewer/dist/cjs/parsers/w3x/w3f/file').default;
const Strings = require('mdx-m3-viewer/dist/cjs/parsers/w3x/wts/file').default;
const Objects = require('mdx-m3-viewer/dist/cjs/parsers/w3x/w3u/file').default;

const [source, local = path.join(__dirname, '../local')] = process.argv.slice(2);
if (!source) throw Error('Usage: node tools/prepare_bonus_campaign.cjs DemoCampaignRUS.w3n [local]');
function archive(bytes) {
  const result = new Mpq();
  result.load(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), true);
  return result;
}
function member(mpq, name) {
  const bytes = mpq.get(name)?.bytes();
  if (!bytes?.length) throw Error('Missing MPQ member: ' + name);
  return Buffer.from(bytes);
}
function listing(mpq) {
  return member(mpq, '(listfile)').toString('utf8').trim().split(/\r?\n/);
}
function table(Type, bytes) {
  const parsed = new Type();
  parsed.load(Type === Strings ? bytes.toString('utf8') : bytes);
  return parsed;
}
function mergeObjects(base, own, strings) {
  const shared = table(Objects, base), result = table(Objects, own);
  assert.equal(shared.version, result.version);
  for (const [name, id] of [['originalTable', 'oldId'], ['customTable', 'newId']]) {
    const merged = new Map();
    for (const object of shared[name].objects) {
      for (const mod of object.modifications) {
        if (typeof mod.value === 'string' && /^TRIGSTR_\d+$/.test(mod.value)) {
          const key = Number(mod.value.slice(8));
          assert(strings.has(key), 'Missing campaign string ' + key);
          mod.value = 'TRIGSTR_' + strings.get(key);
        }
      }
      merged.set(object[id], object);
    }
    for (const object of result[name].objects) {
      const inherited = merged.get(object[id]);
      if (inherited) {
        assert.equal(inherited.oldId, object.oldId);
        // W3U/T fields have no level or variation. A map field wins over its campaign default.
        const overrides = new Set(object.modifications.map(mod => mod.id));
        object.modifications.unshift(...inherited.modifications.filter(mod => !overrides.has(mod.id)));
      }
      merged.set(object[id], object);
    }
    result[name].objects = [...merged.values()];
  }
  return Buffer.from(result.save());
}

const parent = archive(fs.readFileSync(source));
const info = table(Campaign, member(parent, 'war3campaign.w3f'));
const strings = table(Strings, member(parent, 'war3campaign.wts'));
assert.deepEqual(info.mapTitles.map(m => m.path), ['Demo03.w3m', 'Demo04.w3m', 'Demo05.w3m']);
const imports = listing(parent).filter(n => !/^war3campaign\.|\.w3m$/i.test(n));
const target = path.join(local, 'bonus');
const temporary = fs.mkdtempSync(path.join(local, '.bonus-'));
try {
  const data = path.join(temporary,'gamedata');
  fs.mkdirSync(path.join(data,'ui'), {recursive:true});
  const rows = [];
  for (const [index, title] of info.mapTitles.entries()) {
    const name = title.path;
    const original = member(parent, name);
    assert.equal(original.toString('ascii',0,4), 'HM3W');
    const sourceMap = archive(original);
    const contents = new Map(listing(sourceMap).map(n => [n, member(sourceMap, n)]));
    const wts = contents.get('war3map.wts');
    const ownStrings = table(Strings, wts);
    const offset = Math.max(0, ...ownStrings.stringMap.keys()) + 1;
    const extraStrings = new Strings(), stringIds = new Map();
    for (const [key, text] of strings.stringMap) {
      stringIds.set(key, key + offset);
      extraStrings.setString(key + offset, text);
    }
    contents.set('war3map.wts', Buffer.concat([wts, Buffer.from('\r\n' + extraStrings.save())]));
    for (const ext of ['w3u','w3t']) {
      const key = 'war3map.' + ext;
      contents.set(key, mergeObjects(member(parent,'war3campaign.' + ext), contents.get(key), stringIds));
    }
    for (const resource of imports) {
      if (!contents.has(resource)) contents.set(resource, member(parent, resource));
    }
    const generated = new Mpq();
    assert(generated.resizeHashtable((contents.size + 1) * 2));
    for (const [resource, bytes] of contents) assert(generated.set(resource, bytes), resource);
    const headerEnd = original.indexOf(Buffer.from('4d50511a','hex'));
    assert.equal(headerEnd, 512);
    const standalone = Buffer.concat([original.subarray(0,headerEnd), Buffer.from(generated.save())]);
    const check = archive(standalone);
    for (const [resource, bytes] of contents) assert(member(check,resource).equals(bytes), resource);
    fs.writeFileSync(path.join(data,name.toLowerCase()),standalone);
    const fields = [title.chapterTitle,title.mapTitle].map(k => strings.getString(k)).concat(name);
    assert(fields.every(v => v && !/[\r\n"]/.test(v)));
    rows.push('Mission' + (index + 2) + '=' + fields.map(v => '"' + v + '"').join(','));
    console.log(fields.join(' — ') + ' (' + standalone.length + ' bytes)');
  }
  const original = fs.readFileSync(path.join(local,'gamedata/ui/campaignstrings.txt'),'utf8');
  const section = original.match(/\[Tutorial\][\s\S]*?(?=^\[)/m)?.[0];
  assert(section && /^Mission1=[^\r\n]+Prologue02\.w3m"/mi.test(section) && !/^Mission2=/mi.test(section));
  const newline = section.includes('\r\n') ? '\r\n' : '\n';
  const extended = section.replace(/^(Mission1=[^\r\n]*)/m, (_, match) => match + newline + rows.join(newline));
  const patched = Buffer.from(original.replace(section, () => extended));
  const output = path.join(data,'ui/campaignstrings.txt');
  fs.writeFileSync(output,patched);
  fs.writeFileSync(output+'.b64',patched.toString('base64'));
  if (fs.existsSync(target)) {
    // Regeneration is safe for unchanged inputs. A different campaign needs a new private output root.
    for (const name of ['demo03.w3m','demo04.w3m','demo05.w3m','ui/campaignstrings.txt','ui/campaignstrings.txt.b64']) {
      assert(fs.readFileSync(path.join(target,'gamedata',name)).equals(fs.readFileSync(path.join(data,name))),
             'Existing bonus output differs. Move it aside before preparing a different installation.');
    }
  } else fs.renameSync(temporary,target);
} finally {
  fs.rmSync(temporary, {recursive:true,force:true});
}
