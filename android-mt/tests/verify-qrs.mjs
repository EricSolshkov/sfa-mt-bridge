import assert from 'node:assert/strict';
import fs from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { createDecoder, binaryToBlock, readFileHeaderMetaFromBuffer } from 'luby-transform';

const fixture = JSON.parse(fs.readFileSync(new URL('../test-output/qrs-fixture.json',import.meta.url),'utf8'));
const decoder = createDecoder();
const read = frame => binaryToBlock(Uint8Array.from(Buffer.from(frame.split('#')[1], 'base64')));
// Out-of-order, duplicate and dropped frames. Later cycles recover missing blocks.
for (let i=fixture.frames.length-1; i>=0; i--) if (i%3 !== 0) {
  decoder.addBlock(read(fixture.frames[i])); decoder.addBlock(read(fixture.frames[i]));
}
assert.ok(decoder.decodedCount < decoder.meta.k);
for (const frame of fixture.frames) decoder.addBlock(read(frame));
const restored = decoder.getDecoded();
const [profile, meta] = readFileHeaderMetaFromBuffer(restored);
assert.equal(meta.filename, 'MT.bpf');
assert.equal(profile[0],3); assert.equal(profile[1],1);
const content = gunzipSync(profile.slice(2));
let offset = 0;
function readString() {
  let length=0, shift=0, byte;
  do { byte=content[offset++]; length+=(byte&127)*2**shift; shift+=7; } while(byte&128);
  const text=content.subarray(offset,offset+length).toString('utf8'); offset+=length; return text;
}
assert.equal(readString(),fixture.name);
assert.equal(content.readInt32BE(offset),0); offset+=4;
assert.equal(readString(),fixture.config); assert.equal(offset,content.length);
console.log(`PASS: upstream luby-transform decoded ${fixture.frames.length} frames with loss/reordering/duplicates; BPF name/type/config exact.`);
