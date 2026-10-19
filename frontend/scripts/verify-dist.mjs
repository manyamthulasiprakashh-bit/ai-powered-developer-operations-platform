// Verifies a built frontend bundle (frontend/dist) for the public-demo
// deployment guarantees. Uses only Node built-ins so it runs without any
// additional dependencies.
//
// Checks:
//   1. Requests are relative (/api/analyses, /api/statistics present).
//   2. No absolute localhost/loopback backend API URL is baked into the assets.
//   3. The frontend never references the X-API-Key header.
//   4. No configured secret (API_KEY, DEMO_BASIC_AUTH_PASSWORD) leaked into
//      the assets.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const distDir = join(frontendRoot, 'dist');

if (!existsSync(distDir)) {
  console.error('verify-dist: dist/ not found. Run `npm run build` first.');
  process.exit(1);
}

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

const forbidden = [
  { pattern: /X-API-Key/i, label: 'X-API-Key header reference (frontend must never send it)' },
  { pattern: /localhost:8000\/api/i, label: 'absolute localhost API URL' },
  { pattern: /127\.0\.0\.1:8000\/api/i, label: 'absolute loopback API URL' },
];

const secretValues = ['API_KEY', 'DEMO_BASIC_AUTH_PASSWORD']
  .map((name) => process.env[name])
  .filter((value) => typeof value === 'string' && value.length >= 6);

const files = walk(distDir);
const failures = [];

for (const file of files) {
  const content = readFileSync(file, 'utf8');
  for (const rule of forbidden) {
    if (rule.pattern.test(content)) {
      failures.push(`${file}: contains ${rule.label}`);
    }
  }
  for (const secret of secretValues) {
    if (content.includes(secret)) {
      failures.push(`${file}: contains a configured secret value`);
    }
  }
}

const combined = files.map((file) => readFileSync(file, 'utf8')).join('\n');
for (const relativePath of ['/api/analyses', '/api/statistics']) {
  if (!combined.includes(relativePath)) {
    failures.push(`built assets are missing the relative request path ${relativePath}`);
  }
}

if (failures.length > 0) {
  console.error('verify-dist: FAILED');
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log(`verify-dist: OK (${files.length} files checked)`);
