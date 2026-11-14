#!/usr/bin/env python3
"""Build a hierarchical archive reader from an explicit source-owned catalog.

No source discovery, media downloads or invented parentage. Small catalog data is
embedded, so the generated page itself does not need fetch() or a build system.
"""
import argparse
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def validate(catalog, previous=None):
    nodes, items = catalog['nodes'], catalog['items']
    by_id = {}
    for row in nodes + items:
        if not isinstance(row.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+', row['id']) or row['id'] in by_id:
            raise ValueError('Invalid or duplicate stable ID')
        if not isinstance(row.get('title'), str) or not row['title'].strip(): raise ValueError('Source title required')
        by_id[row['id']] = row
    node_ids = {x['id'] for x in nodes}
    for node in nodes:
        if node.get('status') not in ('current', 'historical'): raise ValueError('Explicit current/historical node status required')
        seen = {node['id']};parent = node.get('parent')
        while parent is not None:
            if parent not in node_ids or parent in seen: raise ValueError('Missing parent or hierarchy cycle')
            seen.add(parent);parent = by_id[parent].get('parent')
    for item in items:
        value = item.get('url')
        if value:
            if not isinstance(value, str) or any(ord(c) < 32 for c in value) or '\\' in value: raise ValueError('Invalid asset URL')
            parsed = urlsplit(value)
            if parsed.scheme not in ('', 'http', 'https') or value.startswith('//') or parsed.username or parsed.password: raise ValueError('Unsafe asset URL')
        if not isinstance(item.get('kind'), str): raise ValueError('Explicit asset kind required')
    if previous:
        old_nodes = {x['id'] for x in previous['nodes']}
        if old_nodes - node_ids: raise ValueError('Retain historical nodes instead of deleting them')
        old = {x['id']: x for x in previous['items']}
        removed = set(old) - {x['id'] for x in items}
        resolved = set(catalog.get('resolved_gap_ids', []))
        if removed - resolved or any(old[x].get('kind') != 'gap' for x in removed):
            raise ValueError('Existing material IDs cannot be removed; only explicitly resolved gap stubs may retire')
    return by_id


def build(catalog, previous=None):
    by_id = validate(catalog, previous)
    # Embedded JSON is inert script data, including when a source contains </script>.
    data = json.dumps(catalog, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    title = html.escape(catalog.get('title') or '资料归档')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + title + '''</title><style>
:root{font:15px/1.65 system-ui;color:#242a2e;background:#f5f6f7}body{max-width:1200px;margin:auto;padding:32px}header{position:sticky;top:0;background:#f5f6f7;padding:12px 0;z-index:1}h1{margin:0 0 12px}input{font:inherit;padding:9px;width:min(60vw,600px)}button{font:inherit;padding:9px;margin-left:8px}ul{list-style:none;padding-left:24px}body>main>ul{padding:0}details{margin:12px 0;background:white;border:1px solid #dfe3e6;border-radius:8px;padding:12px}summary{cursor:pointer;font-weight:600}.asset{border-top:1px solid #eee;padding:12px 0}.meta{font-size:13px;color:#667078}a{color:#265c7b}video,audio{display:block;max-width:100%;width:640px;margin-top:8px}small{font-weight:400;color:#667078}[hidden]{display:none!important}mark{background:#fff0b8}</style>
<header><h1>''' + title + '''</h1><label>搜索资料 <input id="query" type="search" placeholder="标题或课程路径"></label><button id="history" type="button" aria-pressed="false">显示历史章节</button><p id="count" class="meta" role="status"></p></header>
<main id="tree"></main><script type="application/json" id="catalog">''' + data + '''</script><script>
'use strict';
const catalog=JSON.parse(document.getElementById('catalog').textContent),nodes=new Map(catalog.nodes.map(n=>[n.id,n]));
const tree=document.getElementById('tree'),query=document.getElementById('query'),history=document.getElementById('history');let showHistory=false;
const el=(tag,text)=>{const x=document.createElement(tag);if(text!=null)x.textContent=text;return x;};
function path(id){const result=[];while(nodes.has(id)){const n=nodes.get(id);result.unshift(n.title);id=n.parent;}return result;}
function historical(id){while(nodes.has(id)){const n=nodes.get(id);if(n.status==='historical')return true;id=n.parent;}return false;}
const itemViews=[];const nodeViews=[];
function itemView(item,list){
 const row=el('li');row.className='asset';row.id=item.id;const crumbs=path(item.node);row.append(el('div',item.title),el('div',crumbs.join(' / ')||'归属未核实'));row.lastChild.className='meta';
 row.append(el('small',item.kind+' · '+(item.status||'状态未提供')));
 if(item.url){const link=el('a',item.kind==='pdf'?'预览 PDF':'打开资料');link.href=item.url;row.append(' · ',link);
  if(['video','audio'].includes(item.kind)){const player=el(item.kind);player.controls=true;player.preload='none';player.src=item.url;row.append(player);}
 }else row.append(el('p','暂无可用取件地址'));
 list.append(row);itemViews.push({row,item,search:[item.title,...crumbs].join(' ').toLocaleLowerCase(),historical:historical(item.node)});
}
function branch(node,list){const row=el('li'),details=el('details'),summary=el('summary',node.title),children=el('ul');row.id=node.id;if(node.status==='historical')summary.append(el('small',' · 历史章节'));details.append(summary,children);row.append(details);list.append(row);nodeViews.push({row,details,node});
 for(const child of catalog.nodes.filter(n=>n.parent===node.id))branch(child,children);
 for(const item of catalog.items.filter(i=>i.node===node.id))itemView(item,children);
}
const list=el('ul');tree.append(list);for(const node of catalog.nodes.filter(n=>n.parent==null))branch(node,list);
const unassigned=catalog.items.filter(i=>!nodes.has(i.node));if(unassigned.length){const row=el('li'),details=el('details'),children=el('ul');details.append(el('summary','归属未核实'),children);row.append(details);list.append(row);nodeViews.push({row,details});for(const item of unassigned)itemView(item,children);}
function filter(){const text=query.value.trim().toLocaleLowerCase();let count=0;for(const v of itemViews){v.row.hidden=(!showHistory&&v.historical)||!v.search.includes(text);if(!v.row.hidden)count++;}
 for(const v of [...nodeViews].reverse()){const self=v.node&&(showHistory||!historical(v.node.id))&&path(v.node.id).join(' ').toLocaleLowerCase().includes(text);v.row.hidden=!self&&![...v.row.querySelectorAll('.asset')].some(x=>!x.hidden);if(text&&!v.row.hidden)v.details.open=true;}
 document.getElementById('count').textContent='当前显示 '+count+' / '+catalog.items.length+' 项资料；搜索包含所属路径。';
}
query.addEventListener('input',filter);history.addEventListener('click',()=>{showHistory=!showHistory;history.setAttribute('aria-pressed',String(showHistory));history.textContent=showHistory?'隐藏历史章节':'显示历史章节';filter();});
function anchor(){let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}const target=document.getElementById(id);if(!target||!tree.contains(target))return;showHistory=true;history.setAttribute('aria-pressed','true');history.textContent='隐藏历史章节';query.value='';filter();for(let n=target.parentElement;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;if(target.firstElementChild?.tagName==='DETAILS')target.firstElementChild.open=true;target.scrollIntoView({block:'start'});}
filter();window.addEventListener('hashchange',anchor);anchor();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): parser.error('Output exists; choose a new output or preserve it explicitly first')
    try:
        result = build(json.loads(args.catalog.read_text()), json.loads(args.previous.read_text()) if args.previous else None)
        args.out.write_text(result, encoding='utf-8')
    except (ValueError, KeyError, OSError) as error: parser.error(str(error))


if __name__ == '__main__': main()
