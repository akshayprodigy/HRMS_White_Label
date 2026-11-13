#!/usr/bin/env node
// Generates simple placeholder icon.png, splash.png, adaptive-icon.png (1024x1024) for a tenant
// from its primary colour, using a dependency-free PNG encoder.
// Usage: node scripts/gen-tenant-assets.js <tenant>
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

function crc32(buf) {
  let c, crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function png(size, pixel) {
  const row = size * 4 + 1;
  const raw = Buffer.alloc(size * row);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) raw.set(pixel(x, y), y * row + 1 + x * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0)),
  ]);
}
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

const tenant = process.argv[2];
if (!tenant) { console.error('usage: gen-tenant-assets.js <tenant>'); process.exit(1); }
const dir = path.join(__dirname, '..', 'tenants', tenant);
const { colors } = JSON.parse(fs.readFileSync(path.join(dir, 'tenant.json'), 'utf8'));
const [pr, pg, pb] = hex(colors.primary);
const S = 1024;
const inRing = (x, y, r) => (x - S / 2) ** 2 + (y - S / 2) ** 2 <= r * r;
const disc = (x, y, outside) =>
  inRing(x, y, 300) ? (inRing(x, y, 170) ? [pr, pg, pb, 255] : [255, 255, 255, 255]) : outside;
fs.writeFileSync(path.join(dir, 'icon.png'), png(S, (x, y) => disc(x, y, [pr, pg, pb, 255])));
fs.writeFileSync(path.join(dir, 'splash.png'), png(S, (x, y) => disc(x, y, [0, 0, 0, 0])));
// Android adaptive-icon foreground: transparent canvas, white ring inside the 66% safe zone
fs.writeFileSync(path.join(dir, 'adaptive-icon.png'), png(S, (x, y) =>
  inRing(x, y, 300) ? (inRing(x, y, 170) ? [0, 0, 0, 0] : [255, 255, 255, 255]) : [0, 0, 0, 0]));
console.log(`wrote tenants/${tenant}/icon.png, splash.png, adaptive-icon.png`);
