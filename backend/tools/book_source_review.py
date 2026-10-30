"""Offline source drafting and bounded PDF review sheets. Never calls AI or opens the app DB.

Requires optional PyMuPDF and Pillow in this Python environment.
Drafts stay unreviewed until explicit page decisions are applied and sealed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tutoring.book_companion import Companion,digest


def draft(pdf,role,edition,output,cache=None):
    import pymupdf as fitz
    document=fitz.open(str(pdf))
    sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
    saved=json.loads(cache.read_text(encoding='utf8')) if cache else None
    if saved and (saved['sha256']!=sha or len(saved['pages'])!=len(document)):
        raise ValueError('The extraction cache belongs to a different original PDF')
    pages=[];visual=[]
    for index,page in enumerate(document):
        native=saved['pages'][index]['text'] if saved else page.get_text('text',sort=True)
        data=page.get_text('dict',flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES,sort=True)
        elements=[]
        for i,block in enumerate(data['blocks']):
            if 'lines' not in block:continue
            lines=[]
            for line in block['lines']:
                seen=set();parts=[]
                for span in line['spans']:
                    signature=(span['text'],tuple(round(v,1) for v in span['bbox']))
                    if signature not in seen:parts.append(span['text']);seen.add(signature)
                lines.append(''.join(parts))
            text='\n'.join(lines).strip()
            if not text:continue
            x0,y0,x1,y1=block['bbox'];w,h=page.rect.width,page.rect.height
            box=[max(0,x0/w),max(0,y0/h),min(1,x1/w),min(1,y1/h)]
            if box[0]>=box[2] or box[1]>=box[3]:box=None
            elements.append({'id':f'p{index+1}:text:{i}','kind':'text','text':text,'bbox':box,
                'description':'Original printed text block; its page position preserves columns and spatial relationships.'})
        images=[]
        for i,info in enumerate(page.get_image_info()):
            box=info['bbox'];w,h=page.rect.width,page.rect.height
            bounds=[max(0,box[0]/w),max(0,box[1]/h),min(1,box[2]/w),min(1,box[3]/h)]
            if bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:continue
            eid=f'p{index+1}:image:{i}'
            images.append({'id':eid,'bbox':bounds,'pixels':[info['width'],info['height']]})
            elements.append({'id':eid,'kind':'illustration','bbox':bounds,'description':'Original PDF image; visual interpretation has not yet been checked.',
                'issue':'Inspect this original image before using its meaning in instruction.'})
        if len(elements)>300:raise ValueError(f'Page {index+1} needs smaller text-block grouping before canonical import')
        pages.append({'page':index+1,'width':page.rect.width,'height':page.rect.height,'native_text':native,'text':native,
            'status':'native_draft','issues':['Source text, reading order and visual meaning await source review.'],
            'student_safe':False,'teacher_material':role=='answer_key','elements':elements})
        visual.append({'page':index+1,'images':images,'text_blocks':len(data['blocks']),
            'vector_paths':len(page.get_drawings())})
        if (index+1)%50==0:print(json.dumps({'pdf':pdf.name,'extracted_pages':index+1,'total':len(document)}),flush=True)
    body=Companion.model_validate({'source':{'filename':pdf.name,'sha256':sha,'page_count':len(pages),'role':role,
        'edition':edition,'language':'en','text_extractor':'PyMuPDF sorted text with native geometry'},
        'producer':'Codex offline source draft; page checks remain explicit','pages':pages}).model_dump()
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix(output.suffix+'.tmp')
    temporary.write_text(json.dumps({'content_sha256':digest(body),'contents':body},ensure_ascii=False,indent=2),encoding='utf8');temporary.replace(output)
    output.with_suffix('.visual-index.json').write_text(json.dumps(visual,indent=2),encoding='utf8')
    print(json.dumps({'file':str(output),'pages':len(pages),'checked':0,'images':sum(len(v['images']) for v in visual)}),flush=True)


def checkpoint(source,decisions,output):
    """Apply explicit source-review decisions, never automatic certification."""
    body=json.loads(source.read_text(encoding='utf8'))['contents']
    plan=json.loads(decisions.read_text(encoding='utf8'))
    if plan['source_sha256']!=body['source']['sha256']:raise ValueError('Review decisions belong to a different original PDF')
    allowed={'text','status','review_method','issues','notes','student_safe','teacher_material','headings','reading_blocks','elements','printed_page'}
    seen=set()
    for decision in plan['pages']:
        n=decision['page'];values={k:v for k,v in decision.items() if k!='page'}
        if n in seen or not 1<=n<=len(body['pages']) or set(values)-allowed:raise ValueError('Use unique existing page IDs and review fields; preserve original extraction')
        seen.add(n);body['pages'][n-1].update(values)
    body=Companion.model_validate(body).model_dump()
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=output.with_suffix(output.suffix+'.tmp')
    temp.write_text(json.dumps({'content_sha256':digest(body),'contents':body},ensure_ascii=False,indent=2),encoding='utf8');temp.replace(output)
    print(json.dumps({'file':str(output),'checked_pages':sum(p['status']=='checked' for p in body['pages']),'pending_pages':sum(p['status']!='checked' for p in body['pages'])}),flush=True)


def sheets(pdf,first,last,output,per_sheet=4,width=800):
    import pymupdf as fitz
    from PIL import Image,ImageDraw
    document=fitz.open(str(pdf));output.mkdir(parents=True,exist_ok=True)
    first=max(1,first);last=min(last,len(document))
    records=[];columns=2;rows=(per_sheet+1)//2
    for offset in range(first,last+1,per_sheet):
        group=list(range(offset,min(offset+per_sheet,last+1)))
        height=max(int(document[n-1].rect.height/document[n-1].rect.width*width) for n in group)+32
        canvas=Image.new('RGB',(width*columns,height*rows),'white');draw=ImageDraw.Draw(canvas)
        for i,n in enumerate(group):
            page=document[n-1];pix=page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),alpha=False)
            im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            x=(i%columns)*width;y=(i//columns)*height
            draw.text((x+10,y+7),f'{pdf.stem} | ORIGINAL PDF PAGE {n}',fill='black');canvas.paste(im,(x,y+30))
        target=output/f'pages-{group[0]:04d}-{group[-1]:04d}.png';canvas.save(target)
        records.append({'pages':group,'image':str(target.resolve())})
    inventory=output/f'inventory-{first}-{last}.json';inventory.write_text(json.dumps(records,indent=2),encoding='utf8')
    print(json.dumps({'sheets':len(records),'inventory':str(inventory.resolve())}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('draft');a.add_argument('pdf',type=Path);a.add_argument('--role',required=True);a.add_argument('--edition',default='')
    a.add_argument('--output',required=True,type=Path);a.add_argument('--layout-cache',type=Path)
    a=sub.add_parser('sheets');a.add_argument('pdf',type=Path);a.add_argument('--first',type=int,default=1);a.add_argument('--last',type=int,required=True)
    a.add_argument('--per-sheet',type=int,default=4,choices=[2,4,6,8]);a.add_argument('--width',type=int,default=800);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('checkpoint');a.add_argument('source',type=Path);a.add_argument('decisions',type=Path);a.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='draft':draft(args.pdf,args.role,args.edition,args.output,args.layout_cache)
    elif args.command=='sheets':sheets(args.pdf,args.first,args.last,args.output,args.per_sheet,args.width)
    else:checkpoint(args.source,args.decisions,args.output)
