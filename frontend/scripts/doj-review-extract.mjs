// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Conservative review-queue extraction; no candidate here is publication-ready.
export const decodeHtml = (input) => String(input ?? '').replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (whole, entity) => {
  const named = {amp:'&',quot:'"',apos:"'",nbsp:' ',lt:'<',gt:'>',ndash:'–',mdash:'—',rsquo:'’',lsquo:'‘',ldquo:'“',rdquo:'”'};
  if (entity.startsWith('#x')) return String.fromCodePoint(Number.parseInt(entity.slice(2),16));
  if (entity.startsWith('#')) return String.fromCodePoint(Number.parseInt(entity.slice(1),10));
  return named[entity.toLowerCase()] ?? whole;
});
export const plainText = (html) => decodeHtml(String(html ?? '').replace(/<br\s*\/?\s*>/gi,'\n').replace(/<[^>]*>/g,' ')).replace(/[\t ]+/g,' ').replace(/ *\n+ */g,'\n').trim();
const nameToken=String.raw`[A-ZÁÉÍÓÚÑ][\p{L}'’.-]+`;
const namePattern=String.raw`(${nameToken}(?:\s+(?:${nameToken}|de|del|la|De|Del|La)){1,4})`;
const eventPattern=String.raw`(?:,\s*(?:\d{2,3}|[^,.;]{1,70}),)?\s+(was sentenced|were sentenced|has been sentenced|was convicted|was found guilty|pleaded guilty|pled guilty|has pleaded guilty|was indicted|was charged|has been charged|was arrested|has been arrested)`;
const eventRegex=new RegExp(String.raw`\b${namePattern}${eventPattern}\b`,'gu');
const badNameWords=/\b(?:After|Before|When|El|Department|Justice|Attorney|Office|Cartel|District|Court|Judge|United|States|Mexican|Federal|Drug|Trafficking|Police|Authorities|Members|Leader|Defendant|Individual|Today|Yesterday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Angels|Strike|Force)\b/u;
const drugContext=/\b(?:drug|narcotic|cocaine|methamphetamine|meth|fentanyl|heroin|marijuana|cannabis|opioid|controlled substance)\w*\b/iu;
const eventType=(verb)=>{const v=verb.toLowerCase();return v.includes('sentenced')?'sentencing_reported':v.includes('convicted')||v.includes('found guilty')?'conviction_reported':v.includes('guilty')?'guilty_plea_reported':v.includes('indicted')||v.includes('charged')?'charge_reported':'arrest_reported'};
const validName=(name)=>name.length>=5&&name.length<=90&&/^[\p{L}][\p{L} .’'-]+$/u.test(name)&&name.trim().split(/\s+/).length>=2&&name.trim().split(/\s+/).length<=7&&!badNameWords.test(name);
const paragraphs=(html)=>[...String(html??'').matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)].map(x=>plainText(x[1])).filter(Boolean);
export function extractArticle(article) {
  const title=plainText(article.title), body=String(article.body??'');
  const rows=[];
  if (drugContext.test(title+' '+body.slice(0,1000))) {
    for (const tableMatch of body.matchAll(/<table\b[^>]*>[\s\S]*?<\/table>/gi)) {
      const table=tableMatch[0];
      const tableRows=[...table.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)].map((match)=>
        [...match[1].matchAll(/<(?:td|th)\b[^>]*>([\s\S]*?)<\/(?:td|th)>/gi)].map((cell)=>plainText(cell[1])));
      const headings=tableRows[0]?.map((value)=>value.toLowerCase())??[];
      const nameIndex=headings.findIndex((value)=>/^(?:defendant|name)s?$/u.test(value));
      const chargeIndex=headings.findIndex((value)=>/^charges?(?:\(s\))?$/u.test(value));
      if(nameIndex<0||tableRows.length<6)continue;
      const before=plainText(body.slice(Math.max(0,tableMatch.index-700),tableMatch.index));
      if(chargeIndex<0&&!/\bdefendants\b/iu.test(before))continue;
      for(const cells of tableRows.slice(1)) {
        const sourceSpan=(cells[nameIndex]??'').trim().replace(/,\s*\d{2,3}$/u,'');
        const name=sourceSpan.replace(/,\s*(?=[IVX]{1,4}$)/u,' ').trim();
        const allegedOffenseSpan=chargeIndex<0?null:cells[chargeIndex]?.trim()??null;
        if(!validName(name)||(chargeIndex>=0&&!drugContext.test(allegedOffenseSpan??'')))continue;
        rows.push({name,kind:'html_table_roster',tentativeEventType:'charge_roster_review',sourceSpan,
          ...(allegedOffenseSpan?{allegedOffenseSpan}:{}),rosterContext:chargeIndex>=0?headings.join(' | '):before.slice(-300),eventDate:null});
      }
    }
  }
  for(const paragraph of paragraphs(body)) {
    const context=paragraph.match(/\b(?:the\s+)?(?:defendants|individuals)\s+(?:indicted|charged|named|listed)\s+(?:are|include)\s*:/iu);
    if(context && drugContext.test(title+' '+body.slice(0,1000))) {
      const tail=paragraph.slice(context.index+context[0].length);
      const entries=tail.split(/;\s*/u);
      if(entries.length>=5) for(const raw of entries) {
        const sourceSpan=raw.trim().replace(/^(?:and\s+)/iu,'').replace(/[.;]$/u,'');
        const name=sourceSpan.split(/,\s*a\.k\.a\./iu)[0].trim();
        if(validName(name)) rows.push({name,kind:'html_roster',tentativeEventType:'charge_roster_review',sourceSpan,rosterContext:context[0],eventDate:null});
      }
    }
  }
  const text=paragraphs(body).join('\n');
  for(const paragraph of text.split(/\n+/)) for(const sourceSpan of paragraph.split(/(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ“])/u)) {
    if(!drugContext.test(sourceSpan)||sourceSpan.length>600)continue;
    eventRegex.lastIndex=0;
    for(const match of sourceSpan.matchAll(eventRegex)) {
      const name=match[1].trim(),verb=match[2].trim(),preceding=sourceSpan.slice(0,match.index).trimEnd();
      if(!validName(name)||/(?:\bof|\bfrom|\bin|\bto|\bat|\bnear)\s*$/iu.test(preceding)||/[“"‘']\s*$/u.test(preceding))continue;
      rows.push({name,kind:'sentence',tentativeEventType:eventType(verb),matchedVerb:verb,sourceSpan:sourceSpan.trim(),eventDate:null});
    }
  }
  return rows;
}
const upperName=/^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .'’\-]+$/u;
const residence=/^(?:(?<prefix>[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .'’\-]+?)\s+)?(?<place>[A-Z][a-z][a-zA-Z .'-]*,\s*[A-Z]{2})\s+(?<age>\d{2})$/u;
export function extractPdfRoster(raw) {
  if(!/Name\s+Place\s+of\s*Residence\s+Age\s+Charges/iu.test(raw))return [];
  const lines=String(raw).replace(/\f/g,'\n\f\n').split(/\n/).map(x=>x.trim()).filter(Boolean);
  const hits=[];
  for(let i=0;i<lines.length;i++) {
    const m=lines[i].match(residence);if(!m)continue;
    const parts=[];let j=i-1;
    while(j>=0&&i-j<=5&&(upperName.test(lines[j])||/^aka\s*[“"']/iu.test(lines[j]))) {
      if(upperName.test(lines[j]))parts.unshift(lines[j]);j--;
    }
    if(m.groups.prefix)parts.push(m.groups.prefix);
    const name=parts.join(' ').replace(/\s+/g,' ').trim();
    if(!validName(name))continue;
    hits.push({i,start:j+1,name,nameSpan:parts.join('\n')});
  }
  return hits.flatMap((hit,index)=>{
    const end=hits[index+1]?.start??lines.length;
    const row=lines.slice(hit.i+1,end).join('\n');
    const match=row.match(/■\s*(?:Conspiracy to Distribute|Distribution of Controlled|Possession With Intent to|Attempted Possession With)[^\n]*(?:\n[^■\n]{1,70}){0,2}/iu);
    if(!match||!drugContext.test(match[0]))return [];
    const page=lines.slice(0,hit.start).filter(x=>x==='\f').length+1;
    return [{name:hit.name,kind:'pdf_roster',tentativeEventType:'charge_roster_review',sourceSpan:hit.nameSpan,allegedOffenseSpan:match[0].trim(),page,eventDate:null}];
  });
}
