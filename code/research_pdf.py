"""Offline bounded PDF text extractor, run as a separate resource-limited process."""
import json
import resource
import sys

MAX_PAGES=64
MAX_PAGE_CHARS=12000
MAX_TOTAL_CHARS=250000


def extract(path):
    import pdfplumber
    pages=[];total=0
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages)>MAX_PAGES:
            return {'error':'page_limit','max_pages':MAX_PAGES}
        for index,page in enumerate(pdf.pages):
            text=(page.extract_text() or '').replace('\x00','')
            cap=min(MAX_PAGE_CHARS,max(0,MAX_TOTAL_CHARS-total))
            kept=text[:cap];total+=len(kept)
            pages.append({'page':index+1,'text':kept,'truncated':len(kept)<len(text)})
            page.close()
    if not pages:
        return {'error':'empty_pdf'}
    return {'pages':pages,'page_count':len(pages),'characters':total,
            'status':'text_extracted' if total else 'ocr_required',
            'truncated_pages':[p['page'] for p in pages if p['truncated']],
            'extractor':'pdfplumber text extraction; no OCR, no source authentication'}


if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    try:
        output=extract(sys.argv[1])
    except Exception:
        output={'error':'unreadable_or_resource_limited_pdf'}
    print(json.dumps(output,ensure_ascii=False))
