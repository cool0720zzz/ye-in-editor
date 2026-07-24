// gallery.html 의 pushHistory / normalize / stateOf 를 파일에서 그대로 뽑아 실제 데이터로 검증.
// 사용: node test_decisions.mjs <decisions.json> <manifest.json>
import fs from 'node:fs';

const SRC = fs.readFileSync(new URL('./gallery.html', import.meta.url), 'utf8');

// 중괄호 짝을 세어 함수 원문을 그대로 잘라낸다 (복제가 아니라 실물 검증)
function grab(name){
  const i = SRC.indexOf(`function ${name}(`);
  if(i < 0) throw new Error(`함수 못 찾음: ${name}`);
  let depth = 0, started = false;
  for(let j = SRC.indexOf('{', i); j < SRC.length; j++){
    if(SRC[j] === '{'){ depth++; started = true; }
    else if(SRC[j] === '}'){ depth--; if(started && depth === 0) return SRC.slice(i, j+1); }
  }
  throw new Error(`함수 끝 못 찾음: ${name}`);
}
const LIB = ['pushHistory','normalize','stateOf'].map(grab).join('\n');

const run = (items, choices, wasCommitted) =>
  new Function('items','choices','wasCommitted', `${LIB}\nnormalize(wasCommitted); return {choices, stateOf};`)
    (items, JSON.parse(JSON.stringify(choices)), wasCommitted);

let pass = 0, fail = 0;
const ok  = (c, m) => { if(c){ pass++; console.log('  [OK] '+m); } else { fail++; console.log('  [FAIL] '+m); } };

const decPath = process.argv[2], manPath = process.argv[3];
const dec = JSON.parse(fs.readFileSync(decPath,'utf8'));
const man = JSON.parse(fs.readFileSync(manPath,'utf8'));
const items = man.items.map(({id,title,created}) => ({id,title,created}));

console.log(`\n[1] 실제 decisions.json 승격 — 기존 메모가 기록으로 보존되는가 (${decPath})`);
const r1 = run(items, dec.decisions, dec.draft === false).choices;
for(const [id, c] of Object.entries(dec.decisions)){
  const n = r1[id];
  const old = (c.notes||'').trim();
  ok(Array.isArray(n.history) && n.history.length === 1, `${id}: 기록 1건 생성`);
  ok((n.history[0].notes||'') === old, `${id}: 원문 메모 그대로 보존`);
  ok(n.history[0].choice === c.choice, `${id}: 선택(${c.choice}) 보존`);
  ok(n.notes === c.notes && n.choice === c.choice, `${id}: 현재 입력칸 값은 유지 (같은 버전이므로)`);
  ok(n.committed === (dec.draft === false), `${id}: committed=${dec.draft === false}`);
}

console.log('\n[2] 새 버전 발행 — 이전 피드백이 기록으로 넘어가고 입력칸이 비는가');
const target = 'a05-sinho-redlight';
const bumped = items.map(it => it.id === target ? {...it, created:'2026-07-25 09:00'} : it);
const r2 = run(bumped, r1, true).choices;
const t2 = r2[target];
ok(t2.history.length === 1, '기록은 1건 (같은 내용 중복 안 쌓임)');
ok(t2.history[0].notes.includes('뒷모습'), '지난 피드백 원문이 기록에 남음');
ok(t2.choice === '' && t2.notes === '', '입력칸은 비워짐 — 새 판에 대해 새로 적게');
ok(t2.fresh === true, 'fresh 표시 — "새 버전 올라옴" 안내 노출');
ok(t2.against === '2026-07-25 09:00', 'against 가 새 버전으로 갱신');
ok(t2.confirmed === false && t2.committed === false, '확정 상태 초기화');
ok(r2['a04-beonhwaga-crowd'].notes === r1['a04-beonhwaga-crowd'].notes, '갱신 안 된 항목은 그대로');

console.log('\n[3] 새 판에 새 피드백 → 2건으로 누적');
const r3in = JSON.parse(JSON.stringify(r2));
r3in[target] = {...r3in[target], choice:'rework', notes:'가로등을 더 따뜻하게', against:'2026-07-25 09:00'};
const r3 = run(bumped.map(it => it.id === target ? {...it, created:'2026-07-26 10:00'} : it), r3in, true).choices;
ok(r3[target].history.length === 2, '기록 2건으로 누적');
ok(r3[target].history[0].notes.includes('뒷모습') && r3[target].history[1].notes.includes('가로등'), '시간순 정렬');
ok(r3[target].history[0].against === '2026-07-24 22:04' && r3[target].history[1].against === '2026-07-25 09:00',
   '각 피드백이 어느 버전에 대한 것인지 남음');

console.log('\n[4] 멱등성 — 여러 번 불러도 기록이 부풀지 않는가');
const a = run(items, dec.decisions, true).choices;
const b = run(items, a, true).choices;
const c = run(items, b, true).choices;
ok(JSON.stringify(b) === JSON.stringify(c), 'normalize 반복 적용해도 동일');
for(const id of Object.keys(a)) ok(a[id].history.length === c[id].history.length, `${id}: 기록 개수 불변`);

console.log('\n[5] 카드 상태 표시');
const { stateOf } = run(items, dec.decisions, true);
ok(stateOf({}) === null, '입력 없음 → 배지 없음');
ok(stateOf({choice:'rework'})[0] === 'pending', '고르기만 함 → 확정 안 됨');
ok(stateOf({choice:'rework',confirmed:true})[0] === 'confirmed', '확정 → 확정 저장됨');
ok(stateOf({choice:'rework',confirmed:true,committed:true})[0] === 'committed', '커밋 → 작업 지시됨');

console.log(`\n결과: ${pass} 통과 / ${fail} 실패`);
process.exit(fail ? 1 : 0);
