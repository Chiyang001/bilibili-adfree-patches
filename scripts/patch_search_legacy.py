"""Stage or apply hash-pinned legacy search ad patches.

Default: validate source, write staged smali/report, leave work/decoded unchanged.
Use --apply only when ready to rebuild classes10.dex.
"""
from pathlib import Path
import argparse,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
RELATIVE='smali_classes10/P10/m.smali'
DESCRIPTOR='LP10/m;'
ORIGINAL_SHA256='af36520c6a2021c1ea6c0b7cd880bd81a75b78a83b89f25ccd2aaee7559f957c'
PATCHED_SHA256='07380f39b8d440a5988f202377080430036fcad1f7d321e2c6d4031e5b3affe4'
METHODS=[('getAdViewType(Lcom/bilibili/adcommon/data/model/AdSearchBean;)I', 1, '    sget-object v0, Lcom/bilibili/ad/adview/search/AdSearchViewType;->AD_CARD_TYPE_NONE:Lcom/bilibili/ad/adview/search/AdSearchViewType;\n    invoke-virtual {v0}, Lcom/bilibili/ad/adview/search/AdSearchViewType;->value()I\n    move-result v0\n    return v0'), ('getAdView(Landroid/view/ViewGroup;ILcom/bilibili/gripper/api/ad/biz/search/OGVTheme;)Lcom/bilibili/gripper/api/ad/biz/search/IAdSearchViewEntry;', 1, '    sget-object v0, Lcom/bilibili/ad/adview/search/AdSearchViewType;->AD_CARD_TYPE_NONE:Lcom/bilibili/ad/adview/search/AdSearchViewType;\n    invoke-virtual {v0}, Lcom/bilibili/ad/adview/search/AdSearchViewType;->value()I\n    move-result p2\n    sget-object v0, Lcom/bilibili/ad/adview/search/AdSearchViewFactory;->INSTANCE:Lcom/bilibili/ad/adview/search/AdSearchViewFactory;\n    invoke-virtual {v0, p1, p2, p3}, Lcom/bilibili/ad/adview/search/AdSearchViewFactory;->create(Landroid/view/ViewGroup;ILcom/bilibili/gripper/api/ad/biz/search/OGVTheme;)Lcom/bilibili/ad/adview/search/AbsAdSearchView;\n    move-result-object p1\n    return-object p1')]
MARKER='# chiyang001: legacy search advertisements use native empty holder'

def digest(text):
 return hashlib.sha256(text.encode('utf8')).hexdigest()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 path=ROOT/'work/decoded'/RELATIVE;content=path.read_text(encoding='utf8');before=digest(content)
 assert re.search(r'^\.class[^\n]* '+re.escape(DESCRIPTOR)+r'$',content,re.M),path
 assert before in {ORIGINAL_SHA256,PATCHED_SHA256},('Unknown source version',str(path),before)
 if before==ORIGINAL_SHA256:
  for signature,locals_count,code in METHODS:
   pattern=re.compile(r'(^\.method[^\n]* '+re.escape(signature)+r'\n)(.*?)(^\.end method)',re.M|re.S)
   matches=list(pattern.finditer(content));assert len(matches)==1,(signature,len(matches));m=matches[0];body=m.group(2)
   assert '    .line 1\n' in body,signature
   prefix=body.split('    .line 1\n',1)[0]
   prefix=re.sub(r'    \.locals \d+\n',f'    .locals {locals_count}\n',prefix,count=1)
   content=content[:m.start()]+m.group(1)+prefix+'    '+MARKER+'\n'+code+'\n'+m.group(3)+content[m.end():]
 assert digest(content)==PATCHED_SHA256,'Unexpected patched output'
 stage=ROOT/'analysis/search_legacy_staged/m.smali';stage.parent.mkdir(parents=True,exist_ok=True);stage.write_text(content,encoding='utf8',newline='\n')
 if args.apply and before!=PATCHED_SHA256:path.write_text(content,encoding='utf8',newline='\n')
 result={'class':DESCRIPTOR,'file':RELATIVE,'original_sha256':ORIGINAL_SHA256,'patched_sha256':PATCHED_SHA256,'methods':[x[0] for x in METHODS],'applied':args.apply or before==PATCHED_SHA256,'staged_file':str(stage),'coverage':'Legacy GAdSearch ads only; existing non-null NONE holder on phone/tablet; ordinary search cards unchanged.'}
 (ROOT/'analysis/search_legacy_patch_report.json').write_text(json.dumps([result],ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
