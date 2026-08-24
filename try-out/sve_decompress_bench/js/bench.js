const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const bz2 = require('unbzip2-stream');
const pako = require('pako');
const { Readable } = require('stream');

const GZIP_IMPL = process.env.GZIP_IMPL || 'native'; // 'native' | 'pako'

const saveDir = path.join(__dirname, '../../../refs/save');

function detectFormat(buf) {
  if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) return 'Gzip';
  if (buf.length >= 3 && buf.toString('latin1', 0, 3) === 'BZh') return 'Bzip2';
  return 'Raw';
}

function versionLine(buf) {
  let end = buf.length;
  for (let i = 0; i < buf.length; i++) {
    if (buf[i] < 32) { end = i; break; }
  }
  return buf.toString('utf8', 0, Math.min(end, 64));
}

function decompressGzip(buf) {
  if (GZIP_IMPL === 'pako') {
    return Promise.resolve(Buffer.from(pako.ungzip(buf)));
  }
  return new Promise((resolve, reject) => {
    zlib.gunzip(buf, (err, out) => (err ? reject(err) : resolve(out)));
  });
}

function decompressBzip2(buf) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    Readable.from(buf)
      .pipe(bz2())
      .on('data', (c) => chunks.push(c))
      .on('end', () => resolve(Buffer.concat(chunks)))
      .on('error', reject);
  });
}

async function main() {
  const files = fs
    .readdirSync(saveDir)
    .filter((f) => f.endsWith('.sve'))
    .sort();

  console.log(
    ['file', 'format', 'raw_kb', 'decomp_kb', 'read_ms', 'decomp_ms'].join('\t')
  );

  let totalRead = 0;
  let totalDecomp = 0;
  let totalRawBytes = 0;
  let totalDecompBytes = 0;

  for (const name of files) {
    const filePath = path.join(saveDir, name);

    const t0 = process.hrtime.bigint();
    const raw = fs.readFileSync(filePath);
    const t1 = process.hrtime.bigint();
    const readMs = Number(t1 - t0) / 1e6;

    const format = detectFormat(raw);

    const t2 = process.hrtime.bigint();
    let decompressed;
    if (format === 'Gzip') {
      decompressed = await decompressGzip(raw);
    } else if (format === 'Bzip2') {
      decompressed = await decompressBzip2(raw);
    } else {
      decompressed = raw;
    }
    const t3 = process.hrtime.bigint();
    const decompMs = Number(t3 - t2) / 1e6;

    console.log(
      [
        name,
        format,
        Math.floor(raw.length / 1024),
        Math.floor(decompressed.length / 1024),
        readMs.toFixed(2),
        decompMs.toFixed(2),
        versionLine(decompressed),
      ].join('\t')
    );

    totalRead += readMs;
    totalDecomp += decompMs;
    totalRawBytes += raw.length;
    totalDecompBytes += decompressed.length;
  }

  console.log('');
  console.log(
    `TOTAL raw=${Math.floor(totalRawBytes / 1024)}KB decomp=${Math.floor(
      totalDecompBytes / 1024
    )}KB read=${totalRead.toFixed(2)}ms decomp=${totalDecomp.toFixed(2)}ms`
  );
}

main();
