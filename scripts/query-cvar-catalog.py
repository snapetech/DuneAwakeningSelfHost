#!/usr/bin/env python3
"""Search the build-pinned DASH console-variable catalogue."""
import argparse,json,pathlib,re

parser=argparse.ArgumentParser()
parser.add_argument('query',nargs='?',default='')
parser.add_argument('--catalog',type=pathlib.Path,default=pathlib.Path('config/cvar-catalog.json'))
parser.add_argument('--namespace')
parser.add_argument('--server-only',action='store_true')
parser.add_argument('--flag',choices=['CHEAT','READONLY','SCALABILITY','SCALABILITY_GROUP'])
parser.add_argument('--limit',type=int,default=100)
parser.add_argument('--json',action='store_true')
args=parser.parse_args()
if not 1 <= args.limit <= 1000: parser.error('--limit must be 1..1000')
data=json.loads(args.catalog.read_text(encoding='utf-8'))
if data.get('schemaVersion') != 1 or data.get('entryCount') != len(data.get('entries',[])): raise SystemExit('invalid catalogue')
needle=args.query.casefold(); rows=[]
for item in data['entries']:
 if needle and needle not in (item['name']+' '+item['help']).casefold(): continue
 if args.namespace and item['namespace'].casefold()!=args.namespace.casefold(): continue
 if args.server_only and not item['serverRelevant']: continue
 if args.flag and args.flag not in item['flags']: continue
 rows.append(item)
rows=rows[:args.limit]
if args.json:
 print(json.dumps({'buildTag':data['buildTag'],'binarySha256':data['binarySha256'],'count':len(rows),'entries':rows},indent=2))
else:
 print(f"catalog build={data['buildTag']} binarySha256={data['binarySha256']} matches={len(rows)}")
 for item in rows:
  flags=','.join(item['flags']) or '-'; help_text=' '.join(item['help'].split())[:160]
  print(f"{item['name']}\ttype={item['type']}\tdefault={item['default'] or '-'}\tflags={flags}\tserver={str(item['serverRelevant']).lower()}\t{help_text}")
