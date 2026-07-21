// 앱의 findFenced / openSong 정규화 / rebuild 를 그대로 복제해 실제 가사 파일로 검증
import fs from 'node:fs';

function findFenced(text, marker){
  const mi = text.indexOf(marker); if(mi<0) return null;
  const open = text.indexOf('```',mi); if(open<0) return null;
  const nl = text.indexOf('\n',open); if(nl<0) return null;
  const close = text.indexOf('\n```',nl); if(close<0) return null;
  return {start:nl+1, end:close, text:text.slice(nl+1,close)};
}

// rebuild() — index.html 과 동일
function rebuild(raw, eol, styleRange, lyricsRange, styleVal, lyricsVal){
  const EOL = eol || '\n';
  const norm = s => s.replace(/\r\n/g,'\n').replace(/\s+$/,'').split('\n').join(EOL);
  let out = raw;
  const edits = [];
  if(styleRange) edits.push({r:styleRange, v:norm(styleVal)});
  edits.push({r:lyricsRange, v:norm(lyricsVal)});
  edits.sort((a,b)=>b.r.start-a.r.start);
  edits.forEach(e=>{ out = out.slice(0,e.r.start) + e.v + EOL + out.slice(e.r.end+1); });
  return out;
}

let pass = 0, fail = 0;
for(const f of process.argv.slice(2)){
  const raw = fs.readFileSync(f,'utf8');
  const name = f.split(/[\\/]/).pop();
  const eol = raw.includes('\r\n') ? '\r\n' : '\n';
  const st = findFenced(raw,'**Style of Music:**');
  const ly = findFenced(raw,'## 가사');

  if(!ly){ console.log(`[FAIL] ${name}: 가사 블록 못 찾음`); fail++; continue; }

  // openSong 이 하는 정규화 (textarea 로 들어가는 값)
  const styleTA = st ? st.text.replace(/\r\n/g,'\n') : '';
  const lyricTA = ly.text.replace(/\r\n/g,'\n');

  // 1) 무편집 재조립 == 원본
  const noop = rebuild(raw, eol, st, ly, styleTA, lyricTA);
  const same = noop === raw;

  // 2) 가사만 수정 시 나머지 보존
  const edited = rebuild(raw, eol, st, ly, styleTA, '[Verse 1]\n테스트 가사 줄');
  const notesKept   = !raw.includes('## 설계 노트') || edited.includes('## 설계 노트');
  const lyricApplied= edited.includes('테스트 가사 줄');
  const styleKept   = !st || edited.includes(st.text.split(/\r?\n/)[0]);
  const fenceRaw = (raw.match(/```/g)||[]).length;
  const fenceEd  = (edited.match(/```/g)||[]).length;
  const eolClean = eol==='\r\n' ? !/(?<!\r)\n/.test(edited) : !edited.includes('\r');

  const ok = same && notesKept && lyricApplied && styleKept && fenceRaw===fenceEd && eolClean;
  console.log(`${ok?'[PASS]':'[FAIL]'} ${name.padEnd(22)} EOL=${eol==='\r\n'?'CRLF':'LF '} 무편집동일=${same} 노트보존=${notesKept} 가사반영=${lyricApplied} 스타일보존=${styleKept} 펜스=${fenceRaw}→${fenceEd} 줄바꿈일관=${eolClean}`);
  ok ? pass++ : fail++;
}
console.log(`\n결과: ${pass} PASS / ${fail} FAIL`);
process.exit(fail?1:0);
